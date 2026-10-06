"""Protocol and governance behavior tests for the governed MCP server.

Protocol: the standard MCP wire contract over stdio
(initialize / notifications with no response / ping / tools/list / tools/call / -32601).
Governance: asserts that "the MCP client receives the governance verdict, not just the
execution result" — the single and most important difference between this server and a
plain MCP server.
"""

from __future__ import annotations

import json

import pytest

from langgraph.checkpoint.memory import InMemorySaver

from agents.graph import build_graph
from helpers import make_package  # Reuse the synthetic asset-package fixture (avoid duplicated code)
from ragdemo import assets

import mcp_server


# ---------------------------------------------------------------- Fixtures

@pytest.fixture
def mcp(monkeypatch, tmp_path):
    """Isolate three things: the policy source, the audit sink path, and the governance graph instance."""
    info = make_package(tmp_path)
    monkeypatch.setattr(assets, "POLICY_PATH", info["policy"])
    assets.load_policy.cache_clear()
    # Write audit to a temp file to avoid polluting the repo's data/audit/audit.jsonl
    mcp_server._GRAPH = build_graph(audit_log=tmp_path / "audit.jsonl", checkpointer=InMemorySaver())
    mcp_server._GRAPH_AUDIT = tmp_path / "audit.jsonl"
    yield info
    mcp_server._GRAPH = None
    assets.load_policy.cache_clear()


def payload_of(resp: dict) -> dict:
    """Extract the business dict from a tools/call JSON-RPC response."""
    return json.loads(resp["result"]["content"][0]["text"])


def call(name: str, arguments: dict) -> dict:
    req = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
           "params": {"name": name, "arguments": arguments}}
    return payload_of(mcp_server.handle_request(req))


# ---------------------------------------------------------------- Protocol contract

def test_initialize_returns_protocol_and_capabilities():
    resp = mcp_server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    result = resp["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert "tools" in result["capabilities"]  # Only declares tools: an honest capability boundary
    assert result["serverInfo"]["name"] == "ragdemo-governed-mcp"


def test_notification_gets_no_response():
    """notifications/* gets no response (per the MCP spec), otherwise clients would wait forever."""
    assert mcp_server.handle_request(
        {"jsonrpc": "2.0", "method": "notifications/initialized"}
    ) is None


def test_unknown_method_returns_32601():
    resp = mcp_server.handle_request({"jsonrpc": "2.0", "id": 7, "method": "resources/list"})
    assert resp["error"]["code"] == -32601


def test_tools_list_exposes_governed_tools():
    resp = mcp_server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = [t["name"] for t in resp["result"]["tools"]]
    for expect in ("search_docs", "list_asset_packages", "scan_asset_package",
                   "extract_game_assets"):
        assert expect in names


# ---------------------------------------------------------------- Governance behavior

def test_low_risk_tool_executes_directly(mcp):
    """Low-risk tools pass through: results and audit entries exist, but no suspension."""
    out = call("search_docs", {"query": "高风险动作", "top_k": 2})
    assert out["status"] == "executed"
    assert len(out["output"]["hits"]) <= 2


def test_unauthorized_tool_is_blocked_without_approval(mcp):
    """Tool outside the whitelist: rejected outright, never enters the approval flow
    (unauthorized calls get no approval chance)."""
    req = {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
           "params": {"name": "drop_database", "arguments": {}}}
    resp = mcp_server.handle_request(req)
    assert resp["error"]["code"] == -32602  # Unknown tool -> invalid params


def test_policy_gate_blocks_before_approval(mcp, tmp_path):
    """Core case: authorization boundary exceeded -> not even a suspension, zero disk output."""
    out = call("extract_game_assets",
               {"package": "test-pkg", "out_dir": str(tmp_path / "ship"), "use": "ship"})
    assert out["status"] == "blocked_by_policy"
    assert "TEST-ONLY" in out["reason"]
    assert not (tmp_path / "ship").exists()  # Zero side effects


def test_high_risk_tool_suspends_then_executes_on_approval(mcp, tmp_path):
    """Two-phase commit: suspend -> approve -> write to disk."""
    pytest.importorskip("PIL")
    out_dir = tmp_path / "ref"
    args = {"package": "test-pkg", "out_dir": str(out_dir),
            "use": "reference", "categories": ["grass"], "per_category": 3, "size": 16}

    first = call("extract_game_assets", args)
    assert first["status"] == "awaiting_approval"
    assert first["payload"]["tool"] == "extract_game_assets"
    assert not out_dir.exists(), "no write side effects while suspended"

    second = call("extract_game_assets", dict(args, _approval={
        "thread_id": first["thread_id"], "type": "approve", "operator": "tester"}))
    assert second["status"] == "executed"
    assert second["output"]["written_count"] == 3
    assert len(list(out_dir.rglob("*.png"))) == 3


def test_rejected_approval_writes_nothing(mcp, tmp_path):
    """Human rejection -> zero side effects (the only assertion of HITL that really matters)."""
    pytest.importorskip("PIL")
    out_dir = tmp_path / "never"
    args = {"package": "test-pkg", "out_dir": str(out_dir),
            "use": "reference", "categories": ["desert"], "per_category": 2}

    first = call("extract_game_assets", args)
    assert first["status"] == "awaiting_approval"

    second = call("extract_game_assets", dict(args, _approval={
        "thread_id": first["thread_id"], "type": "reject", "operator": "tester"}))
    assert second["status"] == "rejected_by_human"
    assert not out_dir.exists()


def test_every_call_is_audited(mcp):
    """The minimum requirement of governance: every call leaves a trace, so anything
    can be reconstructed after the fact."""
    call("search_docs", {"query": "审计"})
    call("extract_game_assets", {"package": "test-pkg", "out_dir": "_x", "use": "ship"})
    lines = (mcp_server._GRAPH_AUDIT).read_text(encoding="utf-8").strip().splitlines()
    types = [json.loads(x)["type"] for x in lines]
    assert "tool_executed" in types
    assert "policy_blocked" in types
