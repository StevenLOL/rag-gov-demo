#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ragdemo MCP server — a zero-dependency, hand-written MCP stdio server
(JSON-RPC 2.0).

[Why hand-written instead of the official mcp SDK]
MCP's wire contract is that thin: the three methods initialize /
tools/list / tools/call plus JSON-RPC 2.0 framing. Hand-writing buys us:
  (1) zero dependencies, so every line of protocol behavior is auditable;
  (2) an easy place to insert the governance gates at the "tool call" layer
      (see below);
The cost is no resources/prompts/sampling capabilities — this server declares
tools only, honestly stated.

[What a governed MCP server looks like]
A plain MCP server: tools/call → execute directly → return the result.
This server:     tools/call → three gates → may return "awaiting approval"
instead of a result.

  Gate 1  permission gate scopes.yaml          out of scope → blocked
                                               (unauthorized), no approval offered
  Gate 2  authorization gate asset_policy.yaml use outside policy →
                                               blocked_by_policy, likewise no
                                               approval offered
  Gate 3  risk gate risk=high                  → awaiting_approval (with thread_id)

Two-phase commit (the key design for fitting HITL into a stateless protocol):
  Phase 1  tools/call extract_game_assets (without _approval)
           → {"status": "awaiting_approval", "thread_id": "...", "payload": {...}}
  Phase 2  tools/call extract_game_assets (with
           _approval={thread_id, type: approve|reject, operator})
           → {"status": "executed"|"rejected_by_human", ...}
  thread_id is carried by InMemorySaver (swap in PostgresSaver in production,
  interface unchanged).

[Run]
  python mcp_server.py            # stdio mode, for MCP clients to connect
  python mcp_server.py --selftest # run a scripted self-check conversation
                                  # (needs no client)
"""

from __future__ import annotations

import json
import sys
import uuid
from typing import Any

from agents.graph import build_graph, resume as graph_resume
from ragdemo import assets

# Protocol version: 2024-11-05 is the baseline revision widely implemented
# across MCP servers today.
PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "ragdemo-governed-mcp", "version": "0.3.0"}

# ---------------------------------------------------------------- Tool declarations

TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_docs",
        "description": (
            "Search the local governance corpus; returns sourced passages (low risk, "
            "runs directly). Results are filtered by the caller's principal before "
            "ranking — passages the principal may not read never enter the candidate set."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search question"},
                "top_k": {"type": "integer", "default": 3},
                "principal": {
                    "type": "object",
                    "description": (
                        "Who is asking: {\"id\": str, \"groups\": [str], "
                        "\"clearance\": public|internal|confidential|restricted}. "
                        "Omitted means the configured least-privileged default."
                    ),
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_asset_packages",
        "description": "List registered game-asset packages and their licensed uses (low risk, read-only)",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "scan_asset_package",
        "description": "Read-only package scan: totals, per-category distribution, sampled paths (low risk, no writes)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "package": {"type": "string", "description": "Package id, see list_asset_packages"},
                "per_category": {"type": "integer", "default": 5},
            },
            "required": ["package"],
        },
    },
    {
        "name": "extract_game_assets",
        "description": (
            "Bulk-export game art assets to disk (HIGH RISK: real write side effects). "
            "The first call returns awaiting_approval; a second call carrying _approval "
            "is required to execute. Uses outside the license allow-list (e.g. shipping "
            "reference-only assets) are rejected outright by the authorization gate."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "package": {"type": "string"},
                "out_dir": {"type": "string", "description": "Export directory"},
                "use": {
                    "type": "string",
                    "enum": ["reference", "ship", "commercial"],
                    "default": "reference",
                    "description": "Intended use; rejected if not in the license allow-list",
                },
                "categories": {"type": "array", "items": {"type": "string"}},
                "per_category": {"type": "integer", "default": 3},
                "size": {"type": "integer", "description": "Thumbnail edge length; omit for full size"},
                "_approval": {
                    "type": "object",
                    "description": "Phase-2 approval: {thread_id, type: approve|reject, operator}",
                },
            },
            "required": ["package", "out_dir"],
        },
    },
]

TOOL_NAMES = {t["name"] for t in TOOLS}


# ---------------------------------------------------------------- Governed execution

def _graph():
    """Process-wide singleton governance graph (InMemorySaver; swap in
    PostgresSaver for production)."""
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


_GRAPH = None


def invoke_governed(
    tool: str, params: dict[str, Any], thread_id: str | None = None
) -> dict[str, Any]:
    """Hand a tool call to the governance graph and translate the graph state
    into an MCP-comprehensible state machine.

    This is the core of this server: what the MCP client sees is not an
    "execution result" but a "governance verdict".

    thread_id semantics: every "phase 1" call is an independent governed
    action, so a fresh thread_id is generated by default (never reused) to
    keep a finished session's state from being inherited by the next call.
    Phase 2 uses _approval.thread_id to point back to the suspended round.
    """
    approval = params.pop("_approval", None)
    if approval is not None:
        # Phase 2: thread_id must point back to the round suspended in phase 1
        thread_id = approval.get("thread_id") or uuid.uuid4().hex[:8]
    else:
        thread_id = thread_id or uuid.uuid4().hex[:8]

    if approval is not None:
        # Phase 2: resume the suspended session (must use the thread_id
        # returned in phase 1)
        result = graph_resume(
            _graph(),
            thread_id,
            {
                "type": approval.get("type", "reject"),
                "operator": approval.get("operator", "mcp-client"),
            },
        )
    else:
        # Phase 1
        result = _graph().invoke(
            {"pending_action": {"tool": tool, "params": params}},
            {"configurable": {"thread_id": thread_id}},
        )

    if "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        return {
            "status": "awaiting_approval",
            "thread_id": thread_id,
            "payload": payload,
            "hint": "Call this tool again with _approval={thread_id, type, operator}",
        }

    status = {
        "EXECUTED": "executed",
        "UNAUTHORIZED": "blocked_unauthorized",
        "BLOCKED_BY_POLICY": "blocked_by_policy",
        "REJECTED_BY_HUMAN": "rejected_by_human",
    }.get(result.get("result"), "unknown")

    out: dict[str, Any] = {"status": status, "thread_id": thread_id}
    if status == "executed":
        out["output"] = result.get("output", {})
    if result.get("output", {}).get("reason"):
        out["reason"] = result["output"]["reason"]
    return out


def call_tool(
    name: str, arguments: dict[str, Any], thread_id: str | None = None
) -> dict[str, Any]:
    """Tool dispatch: every tool goes through the governance graph,
    guaranteeing an audit trail for every call."""
    if name == "list_asset_packages":
        # Pure metadata query, no side effects; still routed through the graph
        # to leave a trail (risk=low passes through)
        return invoke_governed(name, {}, thread_id) | {"packages": assets.list_packages()}

    if name not in TOOL_NAMES:
        raise KeyError(name)
    return invoke_governed(name, dict(arguments or {}), thread_id)


# ---------------------------------------------------------------- JSON-RPC

def _ok(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle_request(
    req: dict[str, Any], thread_id: str | None = None
) -> dict[str, Any] | None:
    """Handle a single JSON-RPC request; notifications/* return None, meaning
    no response is sent."""
    req_id = req.get("id")
    method = req.get("method", "")

    if method == "initialize":
        return _ok(
            req_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},  # declare tools only: honestly state the capability boundary
                "serverInfo": SERVER_INFO,
            },
        )

    if method.startswith("notifications/"):
        return None  # notifications get no response (per the MCP spec)

    if method == "ping":
        return _ok(req_id, {})

    if method == "tools/list":
        return _ok(req_id, {"tools": TOOLS})

    if method == "tools/call":
        params = req.get("params", {})
        name = params.get("name")
        arguments = params.get("arguments", {}) or {}
        try:
            payload = call_tool(name, arguments, thread_id)
        except KeyError:
            return _err(req_id, -32602, f"unknown tool: {name}")
        except Exception as exc:  # a tool's internal exception must not take down the server
            return _err(req_id, -32603, f"{type(exc).__name__}: {exc}")
        return _ok(req_id, {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]})

    return _err(req_id, -32601, f"method not found: {method}")


def serve(stdin=None, stdout=None) -> None:  # pragma: no cover - interactive loop
    """stdio main loop: one JSON-RPC frame per line."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            stdout.write(json.dumps(_err(None, -32700, "parse error")) + "\n")
            stdout.flush()
            continue
        resp = handle_request(req)
        if resp is None:
            continue
        stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        stdout.flush()


# ---------------------------------------------------------------- Self-test

def selftest() -> int:  # pragma: no cover - manual demo entry point
    """Scripted self-check conversation: renders the four key scenarios as
    readable log lines (for scripted demos).

    Governance meaning of the four scenarios:
      A  authorization-gate denial — using reference-only assets for ship is
         denied outright, without even an approval opportunity;
      B  risk-gate suspend — the use is compliant (reference), yet bulk
         export remains high risk, so the response is awaiting approval;
      C  human approval — only a second call carrying thread_id actually
         writes to disk;
      D  rejection with zero side effects — the same suspension re-decided as
         reject leaves no extra files on disk.
    """
    seq_no = 0

    def call(method: str, params: dict, note: str = "") -> dict | None:
        nonlocal seq_no
        seq_no += 1
        req = {"jsonrpc": "2.0", "id": seq_no, "method": method, "params": params}
        resp = handle_request(req)
        head = note or f"{method} {json.dumps(params, ensure_ascii=False)[:90]}"
        print(f"\n--- #{seq_no} {head}")
        print(json.dumps(resp, ensure_ascii=False, indent=2)[:1400])
        return resp

    def payload(resp: dict | None) -> dict:
        """Extract the business dict from a tools/call response."""
        return json.loads(resp["result"]["content"][0]["text"])

    call("initialize", {})
    call("tools/list", {})
    # The search query is Chinese on purpose: the demo corpus is Chinese.
    call("tools/call", {"name": "search_docs",
                        "arguments": {"query": "高风险动作需要审批吗"}})
    call("tools/call", {"name": "list_asset_packages", "arguments": {}})

    # Scenario A: authorization-gate denial (use=ship is not among the tome
    # pack's allowed uses)
    call(
        "tools/call",
        {"name": "extract_game_assets",
         "arguments": {"package": "tome-1.7.6-gfx", "out_dir": "_out/ship", "use": "ship"}},
        note="A authorization gate: use=ship -> expect block (no approval offered)",
    )

    # Scenario B: compliant use but high risk -> suspend
    resp_b = call(
        "tools/call",
        {"name": "extract_game_assets",
         "arguments": {"package": "tome-1.7.6-gfx", "out_dir": "_out/ref",
                       "use": "reference", "per_category": 2, "size": 64}},
        note="B risk gate: use=reference is compliant -> expect awaiting_approval",
    )
    tid = payload(resp_b).get("thread_id")

    # Scenario C: human approval -> actually written to disk
    call(
        "tools/call",
        {"name": "extract_game_assets",
         "arguments": {"package": "tome-1.7.6-gfx", "out_dir": "_out/ref",
                       "use": "reference", "per_category": 2, "size": 64,
                       "_approval": {"thread_id": tid, "type": "approve", "operator": "demo"}}},
        note=f"C human approval (thread_id={tid}) -> expect executed",
    )

    # Scenario D: same-shaped action re-decided as reject -> zero side effects
    resp_d = call(
        "tools/call",
        {"name": "extract_game_assets",
         "arguments": {"package": "tome-1.7.6-gfx", "out_dir": "_out/never",
                       "use": "reference", "per_category": 2}},
        note="D suspend again",
    )
    tid_d = payload(resp_d).get("thread_id")
    call(
        "tools/call",
        {"name": "extract_game_assets",
         "arguments": {"package": "tome-1.7.6-gfx", "out_dir": "_out/never",
                       "use": "reference", "per_category": 2,
                       "_approval": {"thread_id": tid_d, "type": "reject", "operator": "demo"}}},
        note=f"D re-decided as reject (thread_id={tid_d}) -> _out/never must not exist",
    )
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    serve()
