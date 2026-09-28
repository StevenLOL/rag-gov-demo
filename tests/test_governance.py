"""治理测试（v3a 已启用核心三用例）。

覆盖：
1. 高风险动作未经批准必然挂起（interrupt），批准后恢复执行；
2. 白名单外工具必然被拒绝（越权，且不产生 interrupt）；
3. 拒绝后副作用不发生；放行后副作用恰执行一次（恢复≠重放）；
4. 权限白名单 schema 校验（治理即代码的第一条，v1 起进 CI）。
"""

from pathlib import Path

import pytest
import yaml

from agents.graph import build_graph, load_scope, resume as graph_resume
from langgraph.types import Command

SCOPES_PATH = Path(__file__).resolve().parent.parent / "tools" / "scopes.yaml"
VALID_RISKS = {"low", "high"}


def _scopes() -> dict:
    return yaml.safe_load(SCOPES_PATH.read_text(encoding="utf-8"))


def _graph(tmp_path):
    """每用例独立图实例 + 独立审计文件（互不污染）。"""
    return build_graph(audit_log=tmp_path / "audit.jsonl")


def _config(thread: str = "t1") -> dict:
    return {"configurable": {"thread_id": thread}}


# ---------- v1 起进 CI 的 schema 校验 ----------

def test_scopes_file_exists_and_parses():
    scopes = _scopes()
    assert "tools" in scopes and len(scopes["tools"]) >= 4


def test_every_tool_declares_scope_and_risk():
    for name, spec in _scopes()["tools"].items():
        assert spec.get("scope"), f"{name} 缺少 scope 声明"
        assert spec.get("risk") in VALID_RISKS, f"{name} 的 risk 必须是 low/high"
        assert spec.get("data_class"), f"{name} 缺少数据分级"


def test_destructive_tools_are_high_risk():
    for name in ("delete_record", "export_report", "call_cloud_llm"):
        assert _scopes()["tools"][name]["risk"] == "high", f"{name} 必须标记 high"


# ---------- v3a：治理编排行为断言 ----------

def test_high_risk_action_blocks_without_approval(tmp_path):
    """高风险动作未经批准必须挂起；批准后恢复并恰好执行一次。"""
    app = _graph(tmp_path)
    result = app.invoke(
        {"pending_action": {"tool": "export_report", "params": {"file": "report.md"}}},
        _config(),
    )
    assert "__interrupt__" in result, "高风险动作必须在执行前挂起"
    payload = result["__interrupt__"][0].value
    assert payload["tool"] == "export_report"
    assert payload["scope"] == ["docs:read", "export:write"]
    assert result.get("executed", []) == []  # 挂起期间零副作用

    resumed = graph_resume(
        app, "t1", {"type": "approve", "operator": "tester", "note": "ok"}
    )
    assert resumed["result"] == "EXECUTED"
    assert resumed["executed"] == ["export_report"]  # 副作用恰执行一次


def test_unscoped_tool_call_is_denied(tmp_path):
    """白名单外工具直接拒绝：不挂起、不执行。"""
    app = _graph(tmp_path)
    result = app.invoke(
        {"pending_action": {"tool": "drop_database", "params": {}}}, _config()
    )
    assert result["result"] == "UNAUTHORIZED"
    assert "__interrupt__" not in result, "越权不应给人工批准的机会"
    assert result.get("executed", []) == []  # 键缺失 = execute 节点从未到达
    assert load_scope("drop_database") is None


def test_resume_after_reject_no_side_effect(tmp_path):
    """人工拒绝后：状态为 REJECTED_BY_HUMAN，副作用永不发生。"""
    app = _graph(tmp_path)
    app.invoke(
        {"pending_action": {"tool": "delete_record", "params": {"id": 42}}},
        _config("t-reject"),
    )
    resumed = graph_resume(
        app, "t-reject", {"type": "reject", "operator": "tester", "note": "不该删"}
    )
    assert resumed["result"] == "REJECTED_BY_HUMAN"
    assert resumed.get("executed", []) == []  # 副作用永不发生（execute 未到达）


def test_side_effect_executes_exactly_once_after_resume(tmp_path):
    """恢复后 execute 节点只到达一次：interrupt 重跑 risk_gate 不重放副作用；
    低风险动作不经过 interrupt 直接执行。"""
    app = _graph(tmp_path)

    # 高风险：挂起 → 批准 → 恰一次
    app.invoke(
        {"pending_action": {"tool": "export_report", "params": {}}}, _config("t-once")
    )
    resumed = graph_resume(app, "t-once", {"type": "approve", "operator": "tester"})
    assert resumed["executed"] == ["export_report"]

    # 低风险：无 interrupt，直接执行
    low = app.invoke(
        {"pending_action": {"tool": "search_docs", "params": {"q": "x"}}},
        _config("t-low"),
    )
    assert low["result"] == "EXECUTED"
    assert low["executed"] == ["search_docs"]
    assert "__interrupt__" not in low

    # 审计落盘：两次执行各一条事件
    audit_lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(audit_lines) == 2
