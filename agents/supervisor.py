"""Multi-agent orchestration (v4b): a supervisor that decomposes and workers
that own a narrow slice of the work.

The governance question this module answers
-------------------------------------------
When authority is delegated to a sub-agent, **which gate travels with it?**

The answer implemented here — and pinned down by tests — is:

    Every gate travels, and every gate is evaluated **per worker call**.

Concretely, each worker runs the same three gates the single-agent graph runs:

- permission gate (`tools/scopes.yaml`) — is the tool on the whitelist?
- authorization gate (`tools/asset_policy.yaml`) — may it be used this way?
- risk gate (`interrupt()`) — high risk suspends for a human decision

...and on top of those, a fourth gate that only exists because authority is
delegated:

- **delegation gate** — a worker may only invoke a tool whose declared scope is
  a subset of what the supervisor granted for that subtask.

So a worker that reaches for a tool the supervisor never granted is denied
**at the worker**, not routed up for approval. Delegation never widens
authority; it can only narrow it.

Why per-worker-call and not once at the supervisor boundary
-----------------------------------------------------------
The rejected alternative is to grade risk once, at the supervisor, and let the
workers inherit that verdict. It is cheaper and it looks tidier. It is also
wrong: if the gate only runs at the boundary, then any high-risk action a
worker reaches on its own — a tool the supervisor never saw in the plan —
bypasses the gate entirely. That is exactly the path by which least-privilege
gets silently defeated, which is why `test_*_denied_at_worker` below exist.

Audit attribution
-----------------
Every event written from a worker carries both `principal` (who initiated the
request end to end) and `worker` (which node performed the action). Without
`principal`, an approval can only be attributed to "some node in the graph",
which does not satisfy an auditor asking who actually authorised this.

Scope of this module
--------------------
Additive. The single-agent graph in `agents/graph.py` is untouched and still
tested; this module reuses its gate *functions* (not its graph object) so the
two implementations cannot drift apart silently.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from agents.graph import _sqlite_checkpointer, load_scope
from ragdemo import audit, policy
from ragdemo.tools_impl import dispatch as run_tool

TERMINAL_RESULTS = ("UNAUTHORIZED", "BLOCKED_BY_POLICY", "REJECTED_BY_HUMAN")


class SubTask(TypedDict, total=False):
    """One unit of delegated work.

    granted_scope is what the supervisor hands to the worker; it is an upper
    bound, never a floor. A worker may use less than it was granted, never more.
    """

    worker: str
    tool: str
    params: dict
    granted_scope: list[str]


class MultiState(TypedDict, total=False):
    """State for the supervisor graph."""

    request: str                 # the original request text
    principal: dict              # {"id": ..., "groups": [...]} who initiated this
    plan: list[SubTask]          # decomposition produced by the supervisor
    cursor: int                  # index of the subtask being worked on
    current: SubTask | None      # the subtask in flight
    results: list[dict]          # one outcome per completed subtask
    executed: list[str]          # side-effect ledger across all workers
    result: str                  # overall outcome of the last subtask


# ---------------------------------------------------------------- decompose

# Deterministic intent routing: no LLM call, so the graph stays runnable in CI
# and the plan is inspectable. A real deployment would replace this node with a
# model call and keep every gate below unchanged — that is the point of putting
# the gates in the worker rather than in the planner.
_INTENT_PLANS: dict[str, list[SubTask]] = {
    "asset_audit": [
        {
            "worker": "scanner",
            "tool": "scan_asset_package",
            "params": {"package": "tome-1.7.6-gfx", "per_category": 3},
            "granted_scope": ["asset:read"],
        },
        {
            "worker": "reporter",
            "tool": "export_report",
            "params": {"file": "_out/asset_audit.md"},
            "granted_scope": ["docs:read", "export:write"],
        },
    ],
    "cleanup": [
        {
            "worker": "janitor",
            "tool": "delete_record",
            "params": {"id": 42},
            "granted_scope": ["db:delete"],
        },
    ],
}

# Read-only fallback: a request that matches nothing must not default into a
# destructive plan.
_DEFAULT_PLAN: list[SubTask] = [
    {
        "worker": "researcher",
        "tool": "search_docs",
        "params": {"query": "高风险动作执行前需要什么流程", "top_k": 3},
        "granted_scope": ["docs:read"],
    },
    {
        "worker": "scanner",
        "tool": "scan_asset_package",
        "params": {"package": "tome-1.7.6-gfx", "per_category": 2},
        "granted_scope": ["asset:read"],
    },
]


def decompose(request: str) -> list[SubTask]:
    """Map a request onto a plan. Keyword based and deterministic by design."""
    text = request or ""
    for intent, plan in _INTENT_PLANS.items():
        if intent in text:
            return [dict(task) for task in plan]
    return [dict(task) for task in _DEFAULT_PLAN]


def supervisor_node(state: MultiState) -> dict:
    """Supervisor: decompose the request into subtasks.

    The supervisor is deliberately *not* a gate. It chooses work and hands out
    the least scope each subtask needs; it never decides whether an action is
    allowed — that decision belongs to the worker's gates, so that a planner
    bug cannot become a permission bypass.
    """
    plan = state.get("plan") or decompose(state.get("request", ""))
    return {"plan": plan, "cursor": 0, "results": [], "executed": []}


# ---------------------------------------------------------------- dispatch

def dispatch_node(state: MultiState) -> dict:
    """Hand the next subtask to its worker, or finish."""
    plan = state.get("plan", [])
    cursor = state.get("cursor", 0)
    if cursor >= len(plan):
        return {"current": None}
    return {"current": plan[cursor]}


def _route_after_dispatch(state: MultiState) -> str:
    if state.get("current") is None:
        return END
    return "worker"


# ---------------------------------------------------------------- worker

_audit_log_path: Path | None = None


def _emit(event: str, payload: dict) -> None:
    """Write one audit event, always stamped with principal and worker."""
    audit.append_event(event, payload, log_path=_audit_log_path)


def _outcome(task: SubTask, result: str, **extra) -> dict:
    """Shape of one subtask outcome (kept uniform so callers can rely on it)."""
    outcome = {"worker": task.get("worker"), "tool": task.get("tool"), "result": result}
    outcome.update(extra)
    return outcome


def worker_node(state: MultiState) -> dict:
    """A worker: run the full gate chain for the subtask in flight.

    Gate order is the same as the single-agent graph, plus the delegation gate
    first — because asking "was I even granted this?" before anything else keeps
    the other three gates from being consulted on work that was never authorised.
    """
    task = state["current"]
    tool = task["tool"]
    params = task.get("params", {})
    worker = task.get("worker", "worker")
    principal = state.get("principal", {})
    granted = set(task.get("granted_scope", []))

    base = {"tool": tool, "params": params, "worker": worker, "principal": principal}

    # ---- delegation gate: does the worker even hold this authority? ----
    spec = load_scope(tool)
    required = set(spec["scope"]) if spec else set()
    if spec is None:
        _emit("delegation_denied", {**base, "reason": "tool not in permission whitelist"})
        return _finish(state, _outcome(task, "UNAUTHORIZED", denied_at="worker"))
    if not required.issubset(granted):
        _emit(
            "delegation_denied",
            {
                **base,
                "reason": "requested scope exceeds the scope granted by the supervisor",
                "required": sorted(required),
                "granted": sorted(granted),
            },
        )
        return _finish(state, _outcome(task, "UNAUTHORIZED", denied_at="worker"))

    # ---- authorization gate: may this asset/action be used this way? ----
    ok, reason = policy.check_tool_policy(tool, params)
    if not ok:
        _emit("policy_blocked", {**base, "reason": reason})
        return _finish(state, _outcome(task, "BLOCKED_BY_POLICY", reason=reason))

    # ---- risk gate: high risk suspends for a human decision ----
    if spec["risk"] == "low":
        decision = {"type": "approve", "operator": "system", "risk": "low"}
    else:
        decision = interrupt(
            {
                "tool": tool,
                "params": params,
                "scope": spec["scope"],
                "worker": worker,
                "principal": principal,
            }
        )
        if decision.get("type") == "reject":
            _emit("rejected_by_human", {**base, "decision": decision})
            return _finish(state, _outcome(task, "REJECTED_BY_HUMAN", decision=decision))

    # ---- execute: the sole place side effects happen ----
    output = run_tool(tool, params)
    executed = list(state.get("executed", [])) + [tool]
    _emit(
        "tool_executed",
        {**base, "decision": decision, "simulated": bool(output.get("simulated"))},
    )
    return _finish(
        state,
        _outcome(task, "EXECUTED", decision=decision, output=output),
        executed=executed,
        result="EXECUTED",
    )


def _finish(state: MultiState, outcome: dict, executed: list[str] | None = None, result: str | None = None) -> dict:
    """Append the outcome, advance the cursor, and hand control back to dispatch.

    The cursor advances here rather than in dispatch: when a high-risk subtask
    interrupts, the worker re-runs on resume and must complete *the same*
    subtask exactly once. Advancing in dispatch would consume two subtasks for
    one approval.
    """
    return {
        "results": list(state.get("results", [])) + [outcome],
        "cursor": state.get("cursor", 0) + 1,
        "executed": executed if executed is not None else list(state.get("executed", [])),
        "result": result or outcome["result"],
    }


# ---------------------------------------------------------------- graph

def build_supervisor_graph(audit_log: Path | None = None, checkpointer: Any | None = None):
    """Build the supervisor graph.

    audit_log:    override for the audit JSONL path (test injection);
                  None uses ragdemo.config.AUDIT_LOG.
    checkpointer: override for the state cursor; None uses the same on-disk
                  SqliteSaver as the single-agent graph, so a pending approval
                  survives a process restart.
    """
    global _audit_log_path
    _audit_log_path = audit_log

    graph = StateGraph(MultiState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("dispatch", dispatch_node)
    graph.add_node("worker", worker_node)
    graph.set_entry_point("supervisor")
    graph.add_edge("supervisor", "dispatch")
    graph.add_conditional_edges("dispatch", _route_after_dispatch)
    graph.add_edge("worker", "dispatch")

    if checkpointer is None:
        checkpointer = _sqlite_checkpointer()
    return graph.compile(checkpointer=checkpointer)
