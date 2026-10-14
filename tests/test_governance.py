"""Governance tests (v3a: the three core cases are enabled).

Covers:
1. A high-risk action without approval must be suspended (interrupt), and resume
   execution once approved;
2. A tool outside the whitelist is always denied (unauthorized, and no interrupt
   is produced);
3. After a rejection the side effect never happens; after approval it runs exactly
   once (resume != replay);
4. Permission whitelist schema validation (the first "governance-as-code" rule,
   in CI since v1).
"""

import json
from pathlib import Path

import pytest
import yaml

from langgraph.checkpoint.memory import InMemorySaver

from agents.graph import build_graph, load_scope, resume as graph_resume
from langgraph.types import Command

SCOPES_PATH = Path(__file__).resolve().parent.parent / "tools" / "scopes.yaml"
VALID_RISKS = {"low", "high"}


def _scopes() -> dict:
    return yaml.safe_load(SCOPES_PATH.read_text(encoding="utf-8"))


def _graph(tmp_path):
    """Isolated graph instance + isolated audit file per test case (no cross-contamination)."""
    # Inject InMemorySaver for test isolation (the default is an on-disk SqliteSaver)
    return build_graph(audit_log=tmp_path / "audit.jsonl", checkpointer=InMemorySaver())


def _config(thread: str = "t1") -> dict:
    return {"configurable": {"thread_id": thread}}


# ---------- Schema validation in CI since v1 ----------

def test_scopes_file_exists_and_parses():
    scopes = _scopes()
    assert "tools" in scopes and len(scopes["tools"]) >= 4


def test_every_tool_declares_scope_and_risk():
    for name, spec in _scopes()["tools"].items():
        assert spec.get("scope"), f"{name} is missing its scope declaration"
        assert spec.get("risk") in VALID_RISKS, f"{name} risk must be low/high"
        assert spec.get("data_class"), f"{name} is missing its data classification"


def test_destructive_tools_are_high_risk():
    for name in ("delete_record", "export_report", "call_cloud_llm"):
        assert _scopes()["tools"][name]["risk"] == "high", f"{name} must be marked high"


# ---------- v3a: governance orchestration behavior assertions ----------

def test_high_risk_action_blocks_without_approval(tmp_path):
    """High-risk actions must be suspended without approval; after approval they resume and run exactly once."""
    app = _graph(tmp_path)
    result = app.invoke(
        {"pending_action": {"tool": "export_report", "params": {"file": "report.md"}}},
        _config(),
    )
    assert "__interrupt__" in result, "high-risk actions must suspend before execution"
    payload = result["__interrupt__"][0].value
    assert payload["tool"] == "export_report"
    assert payload["scope"] == ["docs:read", "export:write"]
    assert result.get("executed", []) == []  # Zero side effects while suspended

    resumed = graph_resume(
        app, "t1", {"type": "approve", "operator": "tester", "note": "ok"}
    )
    assert resumed["result"] == "EXECUTED"
    assert resumed["executed"] == ["export_report"]  # Side effect runs exactly once


def test_unscoped_tool_call_is_denied(tmp_path):
    """Tools outside the whitelist are rejected outright: no suspension, no execution."""
    app = _graph(tmp_path)
    result = app.invoke(
        {"pending_action": {"tool": "drop_database", "params": {}}}, _config()
    )
    assert result["result"] == "UNAUTHORIZED"
    assert "__interrupt__" not in result, "unauthorized calls must not be offered approval"
    assert result.get("executed", []) == []  # Missing key = the execute node was never reached
    assert load_scope("drop_database") is None


def test_resume_after_reject_no_side_effect(tmp_path):
    """After a human rejection: state is REJECTED_BY_HUMAN, and the side effect never happens."""
    app = _graph(tmp_path)
    app.invoke(
        {"pending_action": {"tool": "delete_record", "params": {"id": 42}}},
        _config("t-reject"),
    )
    resumed = graph_resume(
        app, "t-reject", {"type": "reject", "operator": "tester", "note": "must-not-delete"}
    )
    assert resumed["result"] == "REJECTED_BY_HUMAN"
    assert resumed.get("executed", []) == []  # Side effect never happens (execute was never reached)


def test_side_effect_executes_exactly_once_after_resume(tmp_path):
    """After resume the execute node is reached exactly once: re-running risk_gate on
    interrupt does not replay the side effect; low-risk actions execute directly
    without an interrupt."""
    app = _graph(tmp_path)

    # High risk: suspend -> approve -> exactly once
    app.invoke(
        {"pending_action": {"tool": "export_report", "params": {}}}, _config("t-once")
    )
    resumed = graph_resume(app, "t-once", {"type": "approve", "operator": "tester"})
    assert resumed["executed"] == ["export_report"]

    # Low risk: no interrupt, executes directly
    low = app.invoke(
        {"pending_action": {"tool": "search_docs", "params": {"q": "x"}}},
        _config("t-low"),
    )
    assert low["result"] == "EXECUTED"
    assert low["executed"] == ["search_docs"]
    assert "__interrupt__" not in low

    # Audit on disk: one tool_executed event per execution. The line count is
    # deliberately NOT asserted -- since v4d the retrieval layer writes its own
    # `retrieval` event into the same stream, which is what makes "the denied
    # chunk never appears in the audit log" a checkable statement.
    audit_lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    event_types = [json.loads(line)["type"] for line in audit_lines]
    assert event_types.count("tool_executed") == 2
    assert "retrieval" in event_types
