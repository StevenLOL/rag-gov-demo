#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ragdemo MCP server —— 零依赖手写的 MCP stdio 服务端（JSON-RPC 2.0）。

【为什么手写、而不用官方 mcp SDK】
与 C:/src/devinfo/devmap/src/mcp.ts（269 行实证）同一取向：MCP 的线上契约就那么薄
——initialize / tools/list / tools/call 三个方法 + JSON-RPC 2.0 分帧。手写能换来
  (1) 依赖为零，可审计每一行协议行为；
  (2) 便于在「工具调用」这一层插入治理闸（见下）；
代价是没有 resources/prompts/sampling 等能力——本 server 只声明 tools，诚实不吹。

【一个受治理的 MCP server 长什么样】
普通 MCP server：tools/call → 直接执行 → 返回结果。
本 server：      tools/call → 三道闸 → 可能返回「待审批」而不是结果。

  第一道 权限闸 scopes.yaml       越权 → blocked(unauthorized)，不给审批机会
  第二道 授权闸 asset_policy.yaml 用途越界 → blocked_by_policy，同样不给审批机会
  第三道 风险闸 risk=high          → awaiting_approval（带 thread_id）

两阶段提交（把 HITL 塞进无状态协议的关键设计）：
  阶段一  tools/call extract_game_assets（无 _approval）
          → {"status": "awaiting_approval", "thread_id": "...", "payload": {...}}
  阶段二  tools/call extract_game_assets（带 _approval={thread_id, type: approve|reject, operator}）
          → {"status": "executed"|"rejected_by_human", ...}
  thread_id 由 InMemorySaver 承载（生产换 PostgresSaver，接口不变）。

【运行】
  python mcp_server.py            # stdio 模式，供 MCP 客户端连接
  python mcp_server.py --selftest # 跑一段脚本化对话自检（不依赖任何客户端）
"""

from __future__ import annotations

import json
import sys
import uuid
from typing import Any

from agents.graph import build_graph, resume as graph_resume
from ragdemo import assets

# 协议版本与 devmap 实证一致（2024-11-05 是当前广泛实现的基线版本）
PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "ragdemo-governed-mcp", "version": "0.3.0"}

# ---------------------------------------------------------------- 工具声明

TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_docs",
        "description": "在本地治理语料中检索，返回带出处的片段（低风险，直接执行）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索问题"},
                "top_k": {"type": "integer", "default": 3},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_asset_packages",
        "description": "列出已登记的游戏美术素材包及其授权用途（低风险，只读）",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "scan_asset_package",
        "description": "只读扫描素材包：总数、分类分布、每类抽样路径（低风险，不写盘）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "package": {"type": "string", "description": "素材包 id，见 list_asset_packages"},
                "per_category": {"type": "integer", "default": 5},
            },
            "required": ["package"],
        },
    },
    {
        "name": "extract_game_assets",
        "description": (
            "批量导出游戏美术素材到磁盘（高风险：真实写副作用）。"
            "首次调用返回 awaiting_approval，需二次调用带 _approval 才能执行；"
            "用途越界（如把仅供参考的素材用于 ship）会被授权闸直接拒绝。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "package": {"type": "string"},
                "out_dir": {"type": "string", "description": "导出目录"},
                "use": {
                    "type": "string",
                    "enum": ["reference", "ship", "commercial"],
                    "default": "reference",
                    "description": "用途；不在授权白名单内将被拒绝",
                },
                "categories": {"type": "array", "items": {"type": "string"}},
                "per_category": {"type": "integer", "default": 3},
                "size": {"type": "integer", "description": "缩略图边长；不填则原尺寸"},
                "_approval": {
                    "type": "object",
                    "description": "第二阶段审批：{thread_id, type: approve|reject, operator}",
                },
            },
            "required": ["package", "out_dir"],
        },
    },
]

TOOL_NAMES = {t["name"] for t in TOOLS}


# ---------------------------------------------------------------- 治理执行

def _graph():
    """进程内单例治理图（InMemorySaver；生产换 PostgresSaver 即可）。"""
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


_GRAPH = None


def invoke_governed(
    tool: str, params: dict[str, Any], thread_id: str | None = None
) -> dict[str, Any]:
    """把一次工具调用交给治理图，并把图状态翻译成 MCP 可理解的状态机。

    这是本 server 的核心：MCP 客户端看到的不是"执行结果"，而是"治理裁决"。

    thread_id 语义：每一次「阶段一」调用都是一个独立的被治理动作，
    因此默认生成新的 thread_id（不复用），避免已结束会话的状态被下一次调用继承。
    阶段二由 _approval.thread_id 指回被挂起的那一局。
    """
    approval = params.pop("_approval", None)
    if approval is not None:
        # 阶段二：thread_id 必须指回阶段一被挂起的那一局
        thread_id = approval.get("thread_id") or uuid.uuid4().hex[:8]
    else:
        thread_id = thread_id or uuid.uuid4().hex[:8]

    if approval is not None:
        # 阶段二：恢复被挂起的会话（必须用阶段一返回的 thread_id）
        result = graph_resume(
            _graph(),
            thread_id,
            {
                "type": approval.get("type", "reject"),
                "operator": approval.get("operator", "mcp-client"),
            },
        )
    else:
        # 阶段一
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
            "hint": "再次调用本工具并传入 _approval={thread_id, type, operator}",
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
    """工具分派：所有工具统一过治理图，保证每一次调用都有审计留痕。"""
    if name == "list_asset_packages":
        # 纯元数据查询，无副作用；仍走图以便留痕（risk=low 直通）
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
    """处理单条 JSON-RPC 请求；通知类（notifications/*）返回 None 表示不发响应。"""
    req_id = req.get("id")
    method = req.get("method", "")

    if method == "initialize":
        return _ok(
            req_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},  # 只声明 tools：诚实声明能力边界
                "serverInfo": SERVER_INFO,
            },
        )

    if method.startswith("notifications/"):
        return None  # 通知无响应（MCP 规范）

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
        except Exception as exc:  # 工具内部异常不应当打死 server
            return _err(req_id, -32603, f"{type(exc).__name__}: {exc}")
        return _ok(req_id, {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]})

    return _err(req_id, -32601, f"method not found: {method}")


def serve(stdin=None, stdout=None) -> None:  # pragma: no cover - 交互式循环
    """stdio 主循环：一行一帧 JSON-RPC。"""
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


# ---------------------------------------------------------------- 自检

def selftest() -> int:  # pragma: no cover - 手工演示入口
    """脚本化对话自检：把四段关键剧情打成可读日志（面试演示用）。

    四段剧情的治理含义：
      A 授权闸拒绝  —— 把仅供 ToME 内使用的素材拿去 ship，连审批机会都不给；
      B 风险闸挂起  —— 用途合规（reference），但批量导出仍属高风险，返回待审批；
      C 人工批准    —— 带 thread_id 二次调用，才真正落盘；
      D 拒批零副作用—— 同一次挂起改判 reject，磁盘上不会多出任何文件。
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
        """从 tools/call 响应里取回业务字典。"""
        return json.loads(resp["result"]["content"][0]["text"])

    call("initialize", {})
    call("tools/list", {})
    call("tools/call", {"name": "search_docs",
                        "arguments": {"query": "高风险动作需要审批吗"}})
    call("tools/call", {"name": "list_asset_packages", "arguments": {}})

    # 剧情 A：授权闸拒绝（use=ship 不在 tome 素材包的允许用途内）
    call(
        "tools/call",
        {"name": "extract_game_assets",
         "arguments": {"package": "tome-1.7.6-gfx", "out_dir": "_out/ship", "use": "ship"}},
        note="A 授权闸：use=ship → 应被 block（不给审批机会）",
    )

    # 剧情 B：用途合规但高风险 → 挂起
    resp_b = call(
        "tools/call",
        {"name": "extract_game_assets",
         "arguments": {"package": "tome-1.7.6-gfx", "out_dir": "_out/ref",
                       "use": "reference", "per_category": 2, "size": 64}},
        note="B 风险闸：use=reference 合规 → 应 awaiting_approval",
    )
    tid = payload(resp_b).get("thread_id")

    # 剧情 C：人工批准 → 真正落盘
    call(
        "tools/call",
        {"name": "extract_game_assets",
         "arguments": {"package": "tome-1.7.6-gfx", "out_dir": "_out/ref",
                       "use": "reference", "per_category": 2, "size": 64,
                       "_approval": {"thread_id": tid, "type": "approve", "operator": "demo"}}},
        note=f"C 人工批准（thread_id={tid}）→ 应 executed",
    )

    # 剧情 D：同型动作改判 reject → 零副作用
    resp_d = call(
        "tools/call",
        {"name": "extract_game_assets",
         "arguments": {"package": "tome-1.7.6-gfx", "out_dir": "_out/never",
                       "use": "reference", "per_category": 2}},
        note="D 再挂起一次",
    )
    tid_d = payload(resp_d).get("thread_id")
    call(
        "tools/call",
        {"name": "extract_game_assets",
         "arguments": {"package": "tome-1.7.6-gfx", "out_dir": "_out/never",
                       "use": "reference", "per_category": 2,
                       "_approval": {"thread_id": tid_d, "type": "reject", "operator": "demo"}}},
        note=f"D 改判 reject（thread_id={tid_d}）→ 磁盘不应出现 _out/never",
    )
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    serve()
