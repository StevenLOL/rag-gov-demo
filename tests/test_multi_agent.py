"""Multi-agent governance tests (v4b).

The delegation question this file pins down: **when authority is delegated to a
sub-agent, which gate travels with it?**

The answer asserted here is "every gate, evaluated per worker call". The tests
are written so that the rejected alternative — grading risk once at the
supervisor boundary — would fail them:

- `test_worker_denies_tool_not_granted_by_supervisor` — a worker cannot use a
  tool the supervisor never granted, and the denial happens *at the worker*,
  not on a round trip up to the supervisor.
- `test_two_high_risk_subtasks_suspend_sequentially` — if the risk gate only ran
  once at the boundary, the second high-risk subtask would never suspend. It
  does, so the gate is per call.
"""

import json
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver

from agents.graph import resume as graph_resume
from agents.supervisor import build_supervisor_graph


def _graph(tmp_path):
    """Isolated graph + isolated audit file per test (no cross-contamination)."""
    return build_supervisor_graph(
        audit_log=tmp_path / "audit.jsonl", checkpointer=InMemorySaver()
    )


def _config(thread: str = "m1") -> dict:
    return {"configurable": {"thread_id": thread}}


def _principal() -> dict:
    return {"id": "alice@example.com", "groups": ["engineering"]}


def _task(worker: str, tool: str, granted: list[str], params: dict | None = None) -> dict:
    return {
        "worker": worker,
        "tool": tool,
        "params": params or {},
        "granted_scope": granted,
    }


def _plan(*tasks) -> list[dict]:
    return list(tasks)


def _read_audit(tmp_path) -> list[dict]:
    path = tmp_path / "audit.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---------------------------------------------------------------- dispatch / gather

def test_supervisor_dispatches_and_gathers(tmp_path):
    """A two-worker plan runs end to end: each subtask executes, results are gathered."""
    app = _graph(tmp_path)
    result = app.invoke(
        {
            "request": "review the asset register",
            "principal": _principal(),
            "plan": _plan(
                _task("researcher", "search_docs", ["docs:read"], {"query": "数据分级", "top_k": 3}),
                _task("lister", "list_asset_packages", ["asset:read"]),
            ),
        },
        _config(),
    )
    assert result["result"] == "EXECUTED"
    assert [r["tool"] for r in result["results"]] == ["search_docs", "list_asset_packages"]
    assert result["executed"] == ["search_docs", "list_asset_packages"]
    assert {r["worker"] for r in result["results"]} == {"researcher", "lister"}


def test_decompose_defaults_to_a_read_only_plan():
    """An unrecognised request must not default into a destructive plan."""
    from agents.supervisor import decompose

    plan = decompose("something entirely unrecognised")
    assert plan, "a request must always produce a plan"
    for task in plan:
        assert task["tool"] in ("search_docs", "scan_asset_package"), (
            "the fallback plan must stay read-only"
        )


# ---------------------------------------------------------------- delegation does not widen authority

def test_worker_denies_tool_not_granted_by_supervisor(tmp_path):
    """A worker cannot invoke a tool whose scope exceeds what it was granted.

    This is the core v4b assertion: delegation narrows authority, it never widens
    it. The denial happens at the worker and is never offered a human approval.
    """
    app = _graph(tmp_path)
    result = app.invoke(
        {
            "request": "asset_audit",
            "principal": _principal(),
            # supervisor grants read-only, but the subtask asks for an exporting tool
            "plan": _plan(_task("scanner", "export_report", ["asset:read"], {"file": "x.md"})),
        },
        _config("m-deny"),
    )
    assert result["result"] == "UNAUTHORIZED"
    assert result["results"][0]["denied_at"] == "worker", "denial must happen at the worker"
    assert "__interrupt__" not in result, "an ungranted call must not be offered approval"
    assert result["executed"] == [], "no side effect from a call the worker was never granted"


def test_unscoped_tool_is_denied_at_the_worker(tmp_path):
    """A tool absent from scopes.yaml is denied inside the worker, not routed up."""
    app = _graph(tmp_path)
    result = app.invoke(
        {
            "request": "cleanup",
            "principal": _principal(),
            "plan": _plan(_task("janitor", "drop_database", ["db:delete"])),
        },
        _config("m-unscoped"),
    )
    assert result["result"] == "UNAUTHORIZED"
    assert result["results"][0]["denied_at"] == "worker"
    assert "__interrupt__" not in result
    assert result["executed"] == []


# ---------------------------------------------------------------- risk gate per worker call

def test_high_risk_inside_worker_suspends_and_resumes_exactly_once(tmp_path):
    """A high-risk action raised inside a worker still suspends and, once approved,
    still executes exactly once (resume is not a replay)."""
    app = _graph(tmp_path)
    pending = app.invoke(
        {
            "request": "cleanup",
            "principal": _principal(),
            "plan": _plan(_task("janitor", "delete_record", ["db:delete"], {"id": 42})),
        },
        _config("m-risk"),
    )
    assert "__interrupt__" in pending, "high risk must suspend even inside a worker"
    payload = pending["__interrupt__"][0].value
    assert payload["tool"] == "delete_record"
    assert payload["worker"] == "janitor"
    assert payload["principal"]["id"] == "alice@example.com"
    assert pending["executed"] == [], "no side effect while suspended"

    resumed = graph_resume(app, "m-risk", {"type": "approve", "operator": "tester"})
    assert resumed["result"] == "EXECUTED"
    assert resumed["executed"] == ["delete_record"], "side effect runs exactly once"


def test_two_high_risk_subtasks_suspend_sequentially(tmp_path):
    """If the risk gate ran only once at the supervisor boundary, the second
    high-risk subtask would sail through. It does not: the gate is per worker call."""
    app = _graph(tmp_path)
    plan = _plan(
        _task("janitor", "delete_record", ["db:delete"], {"id": 1}),
        _task("janitor", "delete_record", ["db:delete"], {"id": 2}),
    )
    first = app.invoke(
        {"request": "cleanup", "principal": _principal(), "plan": plan}, _config("m-two")
    )
    assert "__interrupt__" in first, "the first high-risk subtask must suspend"

    after_first = graph_resume(app, "m-two", {"type": "approve", "operator": "tester"})
    assert "__interrupt__" in after_first, "the second high-risk subtask must suspend too"

    after_second = graph_resume(app, "m-two", {"type": "approve", "operator": "tester"})
    assert after_second["result"] == "EXECUTED"
    assert after_second["executed"] == ["delete_record", "delete_record"]
    assert len(after_second["results"]) == 2


# ---------------------------------------------------------------- audit attribution

def test_audit_records_principal_and_worker(tmp_path):
    """An auditor must be able to attribute an action to a person, not to 'some node'."""
    app = _graph(tmp_path)
    app.invoke(
        {
            "request": "read-only",
            "principal": _principal(),
            "plan": _plan(_task("lister", "list_asset_packages", ["asset:read"])),
        },
        _config("m-audit"),
    )
    events = _read_audit(tmp_path)
    executed = [e for e in events if e.get("type") == "tool_executed"]
    assert executed, "a completed subtask must leave an audit event"
    assert executed[0]["principal"]["id"] == "alice@example.com"
    assert executed[0]["worker"] == "lister"


def test_delegation_denial_is_audited(tmp_path):
    """A denied delegation is itself an auditable event, not a silent skip."""
    app = _graph(tmp_path)
    app.invoke(
        {
            "request": "asset_audit",
            "principal": _principal(),
            "plan": _plan(_task("scanner", "export_report", ["asset:read"], {"file": "x.md"})),
        },
        _config("m-audit-deny"),
    )
    events = _read_audit(tmp_path)
    denied = [e for e in events if e.get("type") == "delegation_denied"]
    assert denied, "an over-reaching worker call must leave a delegation_denied event"
    assert denied[0]["granted"] == ["asset:read"]
    assert "docs:read" in denied[0]["required"]
