"""v3 governance orchestration (v3a stage: minimal runnable version).

Implemented in this stage:
- Three gates: permission gate (scopes.yaml whitelist) → authorization gate
  (asset_policy.yaml use whitelist) → risk gate (suspend via interrupt when
  risk=high);
  The order is not interchangeable: authorization denial happens before the
  suspend — "approved" does not mean "lawful"; legal terms should not be
  judged ad hoc by the approver (full argument in the ragdemo/policy.py
  header).
- Suspend primitive: LangGraph interrupt() — high-risk actions forcibly pause
  for a human decision (approve/reject);
- Resume: Command(resume=...) + a persistent thread_id cursor (the default
  checkpointer is **SqliteSaver**, persisted to config.STATE_DB, **resumable
  after process restart**; pass checkpointer=InMemorySaver() to fall back to
  the in-memory version);
- Out-of-scope tools: a tool not in the scopes.yaml whitelist → denied
  outright, without producing an interrupt;
- Side effects execute exactly once: execution lives in a dedicated execute
  node, reached via a conditional edge after the approval resume, which
  naturally guarantees "resume ≠ replay of side effects" (asserted in
  tests/test_governance.py);
- From v3b the execute node dispatches to real implementations via
  ragdemo/tools_impl.py (search_docs / scan_asset_package /
  extract_game_assets); unregistered tools still go through the controlled
  simulation.

Known boundaries (honest list):
- Decision types currently support approve/reject; the UI semantics for
  edit/respond are covered by the Streamlit approval card (v3b);
- The checkpointer is already the on-disk version (SqliteSaver, thread
  cursors stored per thread_id in config.STATE_DB); single-node SQLite does
  not solve multi-replica concurrency, so production multi-instance still
  needs PostgresSaver (v3c), with the interface unchanged.
"""

from __future__ import annotations

import json
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any, TypedDict

import yaml
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command, interrupt

from ragdemo import audit, policy
from ragdemo.config import BASE_DIR, STATE_DB
from ragdemo.tools_impl import dispatch

SCOPES_PATH = Path(BASE_DIR) / "tools" / "scopes.yaml"


@lru_cache(maxsize=1)
def load_scopes() -> dict[str, dict[str, Any]]:
    """Load and cache scopes.yaml (the sole data source for out-of-scope
    decisions)."""
    raw = yaml.safe_load(SCOPES_PATH.read_text(encoding="utf-8"))
    return raw.get("tools", {})


def load_scope(tool: str) -> dict[str, Any] | None:
    """Return a tool's permission declaration; undeclared = out of scope
    (returns None)."""
    return load_scopes().get(tool)


class GovState(TypedDict, total=False):
    """Graph state for the governance orchestration."""

    pending_action: dict        # {"tool": str, "params": dict}
    decision: dict | None       # human/automatic decision (persisted to audit)
    result: str                 # EXECUTED / REJECTED_BY_HUMAN / UNAUTHORIZED / BLOCKED_BY_POLICY
    executed: list[str]         # side-effect ledger: tools actually executed (basis for the exactly-once assertion)
    output: dict                # the tool's real return value (from v3b)


def policy_gate(state: GovState) -> dict:
    """Second gate: authorization check (use whitelist).

    Division of labor vs. risk_gate: this gate rejects actions that "should
    not be done at all", so it offers no interrupt — it runs before human
    approval.
    """
    action = state["pending_action"]
    tool = action["tool"]
    params = action.get("params", {})

    ok, reason = policy.check_tool_policy(tool, params)
    if not ok:
        # Authorization denials also leave a trail: the audit must be able to
        # answer "why did the system refuse at that moment"
        audit.append_event(
            "policy_blocked",
            {"tool": tool, "params": params, "reason": reason},
            log_path=_audit_log_path,
        )
        return {"result": "BLOCKED_BY_POLICY", "output": {"reason": reason}}
    return {}


def _route_after_policy(state: GovState) -> str:
    """Conditional edge: authorization denied → END; allowed → risk gate."""
    if state.get("result") == "BLOCKED_BY_POLICY":
        return END
    return "risk_gate"


def risk_gate(state: GovState) -> dict:
    """Risk-grading node (third gate): whitelist check → low risk passes
    straight through / high risk suspends via interrupt."""
    action = state["pending_action"]
    tool = action["tool"]
    spec = load_scope(tool)

    if spec is None:
        # Out of scope: tools outside the whitelist are denied outright, no
        # interrupt offered (the denial must happen before the suspend)
        return {"result": "UNAUTHORIZED", "decision": None}

    if spec["risk"] == "low":
        return {"decision": {"type": "approve", "operator": "system", "risk": "low"}}

    # High risk: suspend via interrupt. First execution raises GraphInterrupt;
    # when resumed with a human Command(resume=...), this node re-runs from the
    # top and interrupt() returns the resume value directly — official
    # LangGraph semantics.
    decision: dict = interrupt(
        {"tool": tool, "params": action.get("params", {}), "scope": spec["scope"]}
    )
    if decision.get("type") == "reject":
        return {"result": "REJECTED_BY_HUMAN", "decision": decision}
    return {"decision": decision}


def execute(state: GovState) -> dict:
    """Execute node: the sole place where side effects happen. Only actions
    cleared by risk_gate reach here."""
    action = state["pending_action"]
    tool = action["tool"]
    params = action.get("params", {})
    # v3b: dispatch to real implementations; unregistered tools
    # (export_report/delete_record, etc.) remain controlled simulations so
    # demos/tests do not produce real destructive side effects.
    output = dispatch(tool, params)
    executed = list(state.get("executed", [])) + [tool]
    audit.append_event(
        "tool_executed",
        {
            "tool": tool,
            "params": params,
            "decision": state.get("decision"),
            "simulated": bool(output.get("simulated")),
        },
        log_path=_audit_log_path,
    )
    return {"result": "EXECUTED", "executed": executed, "output": output}


def _route_after_gate(state: GovState) -> str:
    """Conditional edge: rejection / out of scope → END; cleared → execute
    node."""
    if state.get("result") in ("REJECTED_BY_HUMAN", "UNAUTHORIZED"):
        return END
    return "execute"


# Audit log path is injected by build_graph (temporary path for tests;
# defaults to config.AUDIT_LOG)
_audit_log_path: Path | None = None

# Connection held by SqliteSaver: reused within the process, avoiding repeated
# connections that would open the same database multiple times
_sqlite_conn: "sqlite3.Connection | None" = None


def _sqlite_checkpointer() -> SqliteSaver:
    """On-disk checkpointer: the thread_id cursor is written to
    config.STATE_DB and is resumable after process restart.

    Note: SqliteSaver.from_conn_string() in langgraph-checkpoint 4.x returns
    a context manager (closed on exit) and cannot be handed directly to
    compile(); here we explicitly hold a process-level connection.
    Multi-replica deployments need PostgresSaver (v3c), with the graph
    interface unchanged.
    """
    global _sqlite_conn
    if _sqlite_conn is None:
        STATE_DB.parent.mkdir(parents=True, exist_ok=True)
        _sqlite_conn = sqlite3.connect(str(STATE_DB), check_same_thread=False)
    return SqliteSaver(_sqlite_conn)


def build_graph(audit_log: Path | None = None, checkpointer: Any | None = None):
    """Build the governance orchestration graph.

    audit_log:    override for the audit JSONL path (for test injection);
                  None uses ragdemo.config.AUDIT_LOG.
    checkpointer: override for the state-cursor persister (tests inject an
                  InMemorySaver for isolation); None uses SqliteSaver
                  persisted to ragdemo.config.STATE_DB so the thread_id
                  cursor is **resumable after process restart**.
    """
    global _audit_log_path
    _audit_log_path = audit_log

    graph = StateGraph(GovState)
    graph.add_node("policy_gate", policy_gate)
    graph.add_node("risk_gate", risk_gate)
    graph.add_node("execute", execute)
    # Entry point = authorization gate (the second gate); the permission check
    # lives in risk_gate (the first gate, which needs the scope declaration first)
    graph.set_entry_point("policy_gate")
    graph.add_conditional_edges("policy_gate", _route_after_policy)
    graph.add_conditional_edges("risk_gate", _route_after_gate)
    graph.add_edge("execute", END)

    if checkpointer is None:
        checkpointer = _sqlite_checkpointer()
    return graph.compile(checkpointer=checkpointer)


def resume(graph, thread_id: str, decision: dict) -> dict:
    """Convenience wrapper to resume execution with a human decision (maps to
    the API layer's /approve endpoint, v3b)."""
    return graph.invoke(
        Command(resume=decision), config={"configurable": {"thread_id": thread_id}}
    )


def json_dumps(value: Any) -> str:
    """Safe serialization for audit/debug purposes."""
    return json.dumps(value, ensure_ascii=False, default=str)
