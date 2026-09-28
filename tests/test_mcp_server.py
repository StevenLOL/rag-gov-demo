"""受治理 MCP server 的协议与治理行为测试。

协议部分：对齐 C:/src/devinfo/devmap/src/mcp.ts 实证过的 MCP 契约
（initialize / notifications 无响应 / ping / tools/list / tools/call / -32601）。
治理部分：断言「MCP 客户端收到的是治理裁决，而不只是执行结果」——
这是本 server 与普通 MCP server 唯一、也是最重要的区别。
"""

from __future__ import annotations

import json

import pytest

from agents.graph import build_graph
from helpers import make_package  # 复用合成素材包夹具（避免重复代码）
from ragdemo import assets

import mcp_server


# ---------------------------------------------------------------- 夹具

@pytest.fixture
def mcp(monkeypatch, tmp_path):
    """隔离三件事：策略源、审计落盘路径、治理图实例。"""
    info = make_package(tmp_path)
    monkeypatch.setattr(assets, "POLICY_PATH", info["policy"])
    assets.load_policy.cache_clear()
    # 审计写临时文件，避免污染仓库 data/audit/audit.jsonl
    mcp_server._GRAPH = build_graph(audit_log=tmp_path / "audit.jsonl")
    mcp_server._GRAPH_AUDIT = tmp_path / "audit.jsonl"
    yield info
    mcp_server._GRAPH = None
    assets.load_policy.cache_clear()


def payload_of(resp: dict) -> dict:
    """从 tools/call 的 JSON-RPC 响应里取回业务字典。"""
    return json.loads(resp["result"]["content"][0]["text"])


def call(name: str, arguments: dict) -> dict:
    req = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
           "params": {"name": name, "arguments": arguments}}
    return payload_of(mcp_server.handle_request(req))


# ---------------------------------------------------------------- 协议契约

def test_initialize_returns_protocol_and_capabilities():
    resp = mcp_server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    result = resp["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert "tools" in result["capabilities"]  # 只声明 tools：能力边界诚实
    assert result["serverInfo"]["name"] == "ragdemo-governed-mcp"


def test_notification_gets_no_response():
    """notifications/* 不发响应（MCP 规范），否则客户端会一直等。"""
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


# ---------------------------------------------------------------- 治理行为

def test_low_risk_tool_executes_directly(mcp):
    """低风险工具直通：有结果、有审计，但不挂起。"""
    out = call("search_docs", {"query": "高风险动作", "top_k": 2})
    assert out["status"] == "executed"
    assert len(out["output"]["hits"]) <= 2


def test_unauthorized_tool_is_blocked_without_approval(mcp):
    """白名单外工具：直接拒绝，不进入审批流程（越权不给批准机会）。"""
    req = {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
           "params": {"name": "drop_database", "arguments": {}}}
    resp = mcp_server.handle_request(req)
    assert resp["error"]["code"] == -32602  # 未知工具 → 参数错误


def test_policy_gate_blocks_before_approval(mcp, tmp_path):
    """核心用例：授权越界 → 连挂起都不给，磁盘零产出。"""
    out = call("extract_game_assets",
               {"package": "test-pkg", "out_dir": str(tmp_path / "ship"), "use": "ship"})
    assert out["status"] == "blocked_by_policy"
    assert "TEST-ONLY" in out["reason"]
    assert not (tmp_path / "ship").exists()  # 零副作用


def test_high_risk_tool_suspends_then_executes_on_approval(mcp, tmp_path):
    """两阶段提交：挂起 → 批准 → 落盘。"""
    pytest.importorskip("PIL")
    out_dir = tmp_path / "ref"
    args = {"package": "test-pkg", "out_dir": str(out_dir),
            "use": "reference", "categories": ["草地"], "per_category": 3, "size": 16}

    first = call("extract_game_assets", args)
    assert first["status"] == "awaiting_approval"
    assert first["payload"]["tool"] == "extract_game_assets"
    assert not out_dir.exists(), "挂起期间不得有任何写副作用"

    second = call("extract_game_assets", dict(args, _approval={
        "thread_id": first["thread_id"], "type": "approve", "operator": "tester"}))
    assert second["status"] == "executed"
    assert second["output"]["written_count"] == 3
    assert len(list(out_dir.rglob("*.png"))) == 3


def test_rejected_approval_writes_nothing(mcp, tmp_path):
    """人工拒批 → 零副作用（这是 HITL 唯一真正重要的断言）。"""
    pytest.importorskip("PIL")
    out_dir = tmp_path / "never"
    args = {"package": "test-pkg", "out_dir": str(out_dir),
            "use": "reference", "categories": ["沙漠"], "per_category": 2}

    first = call("extract_game_assets", args)
    assert first["status"] == "awaiting_approval"

    second = call("extract_game_assets", dict(args, _approval={
        "thread_id": first["thread_id"], "type": "reject", "operator": "tester"}))
    assert second["status"] == "rejected_by_human"
    assert not out_dir.exists()


def test_every_call_is_audited(mcp):
    """治理的最低要求：每一次调用都留痕，事后能复盘。"""
    call("search_docs", {"query": "审计"})
    call("extract_game_assets", {"package": "test-pkg", "out_dir": "_x", "use": "ship"})
    lines = (mcp_server._GRAPH_AUDIT).read_text(encoding="utf-8").strip().splitlines()
    types = [json.loads(x)["type"] for x in lines]
    assert "tool_executed" in types
    assert "policy_blocked" in types
