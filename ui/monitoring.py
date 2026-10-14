"""Monitoring metrics for rag-gov-demo — pure functions over the audit stream.

Why this module exists
---------------------
The UI used to answer "what did the system say?" and never "how is it behaving?".
A governed system that cannot show its own guardrails firing is asking to be
trusted on faith. This module is the read-only measurement layer for that:
refusal rate, ungrounded-answer share, ACL filtering ratio, approval outcomes
and retry budget — every number derived from the audit stream the system
already writes, and nothing derived from a field no writer emits.

Design constraints, in priority order:

1. **No new runtime dependency.** Streamlit ships `st.metric` / `st.bar_chart` /
   `st.line_chart`, which accept plain lists and dicts. Importing pandas or plotly
   to draw five bars would contradict the repo's "minimal, auditable" stance —
   the same stance that makes this demo useful as a governance reference.

2. **Pure functions, no I/O beyond one explicit path argument.** `summarize()` and
   friends take `list[dict]` so `tests/test_monitoring.py` can assert on synthetic
   events with no fixture files and no API. Only `load_eval_baseline()` touches the
   filesystem, and it takes the path explicitly.

3. **Every metric is derived from a field some writer actually emits.** The event
   taxonomy below was read off the `audit.append_event` call sites, not invented:
   a metric computed from a key nobody writes would render as a permanent zero and
   quietly train the reader to ignore the panel.

4. **A panel that cannot be populated says so.** `load_eval_baseline()` returns
   `None` when the JSON is absent, and the dashboard renders "run `make eval-json`"
   rather than a fake 0%.

Audit event taxonomy (grep the `append_event` call sites to re-verify):

| type               | writer                        | key payload                              |
|--------------------|-------------------------------|------------------------------------------|
| ask                | api/main.py                   | question, principal, mode, n_citations   |
| refused            | api/main.py                   | + reason (which gate fired)              |
| retrieval          | ragdemo/tools_impl.py         | tool, principal, query, top_k, returned, filtered_out |
| policy_blocked     | agents/graph.py, supervisor   | tool, params, reason                     |
| retry_scheduled    | ragdemo/retry.py              | label, delay                             |
| retry_exhausted    | ragdemo/retry.py              | label, attempts, reason, waited          |
| delegation_denied  | agents/supervisor.py          | worker, tool, reason                     |
| rejected_by_human  | agents/supervisor.py          | tool, decision                           |
| tool_executed      | agents/supervisor.py          | tool, decision, simulated                |
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

# Event types that represent "a request reached the answer path". Refusals are
# counted separately because a refusal is a *successful* governance outcome, not
# a failure — collapsing them into one "requests" number hides the guardrail.
ANSWER_PATH = {"ask", "refused"}

# The governance gates, in the order a request meets them. The funnel is drawn in
# this order so that a reader can see where work stopped.
GATES = [
    ("answered", "Answered with citations"),
    ("refused", "Refused (guardrail fired)"),
    ("policy_blocked", "Blocked by tool policy"),
    ("delegation_denied", "Denied at delegation"),
    ("rejected_by_human", "Rejected by human approver"),
    ("tool_executed", "Executed after approval"),
    ("retry_exhausted", "Retry budget exhausted"),
]


def _principal_key(event: dict) -> str:
    """Stable label for a principal, from the audit-safe projection.

    `principal` is `{"id", "groups", "clearance"}` (see acl.Principal.to_dict).
    Falls back through the keys rather than assuming the writer remembered to
    stamp it: an unstamped event still has to land in *some* bucket, otherwise
    the distribution silently under-counts.
    """
    p = event.get("principal")
    if isinstance(p, dict) and p.get("id"):
        return str(p["id"])
    return "(unstamped)"


def _hour(ts: str) -> str | None:
    """'2026-10-13T11:32:01+0800' -> '10-13 11:00'.

    Returns None on anything unparseable: one malformed timestamp must not take
    down the whole trend chart, and a dropped bucket is visible as a gap.
    """
    if not isinstance(ts, str) or len(ts) < 13:
        return None
    try:
        datetime.fromisoformat(ts)
    except ValueError:
        return None
    return f"{ts[5:10]} {ts[11:13]}:00"


def summarize(events: list[dict]) -> dict[str, Any]:
    """Headline KPIs for the top row of the dashboard.

    `refusal_rate` is deliberately *not* "errors / requests": in a governed RAG
    system a refusal is the system working. It is reported as its own number so a
    spike reads as "the guardrail is firing more", which is a different
    investigation from "the service is erroring".
    """
    types = Counter(str(e.get("type", "?")) for e in events)
    answered = types.get("ask", 0)
    refused = types.get("refused", 0)
    asked_total = answered + refused
    citations = [e.get("n_citations") for e in events if e.get("type") == "ask"]
    citations = [c for c in citations if isinstance(c, int)]
    return {
        "events_total": len(events),
        "answered": answered,
        "refused": refused,
        "refusal_rate": (refused / asked_total) if asked_total else None,
        "mean_citations": (sum(citations) / len(citations)) if citations else None,
        "tool_calls": types.get("tool_executed", 0),
        "blocked": types.get("policy_blocked", 0) + types.get("delegation_denied", 0),
        "human_rejections": types.get("rejected_by_human", 0),
        "retries_exhausted": types.get("retry_exhausted", 0),
        "distinct_principals": len({_principal_key(e) for e in events}),
        "first_event_at": min((e.get("ts") for e in events if e.get("ts")), default=None),
        "last_event_at": max((e.get("ts") for e in events if e.get("ts")), default=None),
    }


def gate_funnel(events: list[dict]) -> list[dict[str, Any]]:
    """Governance funnel, in the order a request meets each gate.

    Ordered by GATES, not by count: the point of the panel is the *shape* of the
    path, and re-sorting by magnitude would put the rarest gate first.
    """
    types = Counter(str(e.get("type", "?")) for e in events)
    return [
        {"key": key, "label": label, "count": types.get(key, 0)}
        for key, label in GATES
    ]


def refusal_reasons(events: list[dict]) -> list[tuple[str, int]]:
    """Why the guardrail fired, most frequent first.

    Only `refused` events carry a `reason` in practice (api/main.py writes
    `result.refusal_reason or ""`). An empty reason is kept as "(unspecified)"
    rather than dropped: "we refuse and don't know why" is itself a finding.
    """
    c = Counter(
        (str(e.get("reason")) or "(unspecified)")
        for e in events if e.get("type") == "refused"
    )
    return c.most_common()


def volume_by_hour(events: list[dict]) -> list[dict[str, Any]]:
    """Answer-path volume per hour, oldest first — the trend line.

    Buckets with no events are omitted rather than zero-filled: a zero-filled
    series over a 30-day window draws 720 mostly-empty buckets and hides the
    shape of actual traffic.
    """
    c = Counter()
    for e in events:
        if e.get("type") not in ANSWER_PATH:
            continue
        h = _hour(e.get("ts", ""))
        if h:
            c[h] += 1
    return [{"hour": h, "count": c[h]} for h in sorted(c)]


def citation_coverage(events: list[dict]) -> list[dict[str, Any]]:
    """Distribution of citations per answered question.

    A long tail at zero means the system is answering ungrounded — the single
    most useful thing this panel can show, and the reason it is not just an
    average (an average hides the zero tail).
    """
    c = Counter(
        int(e["n_citations"])
        for e in events
        if e.get("type") == "ask" and isinstance(e.get("n_citations"), int)
    )
    return [{"citations": n, "count": c[n]} for n in sorted(c)]


def principal_distribution(events: list[dict]) -> list[dict[str, Any]]:
    """Who is asking, by principal id — the ACL enforcement view.

    Paired with `acl_filtering()` this is the answer to "is the access filter
    actually doing anything": a principal who only ever sees a filtered view
    shows up here as traffic with a high hidden ratio below.
    """
    c = Counter(_principal_key(e) for e in events if e.get("type") in ANSWER_PATH)
    return [{"principal": p, "count": c[p]} for p, _ in c.most_common()]


def acl_filtering(events: list[dict]) -> dict[str, Any]:
    """How much the access filter removed, from `retrieval` events.

    Reads `filtered_out` — the authoritative count written by
    `ragdemo/tools_impl.py` straight out of `acl.partition()`.

    Why not infer it as `top_k - len(returned)`: that arithmetic cannot tell
    "the ACL hid four chunks" from "the backend only found one". Both look like
    hidden=4. A monitoring panel that cannot distinguish those two is worse than
    no panel, because the reader acts on it.

    The inference is kept only as a fallback for logs written before the field
    existed, and is reported under a separate `inferred` key so the reader can
    tell measured numbers from reconstructed ones. `returned` is a list of chunk
    ids by design; the identifiers of filtered-out chunks are deliberately never
    written, so a count is the only honest measure available either way.
    """
    measured_hidden = 0
    inferred_hidden = 0
    returned_total = 0
    measured_n = 0
    inferred_n = 0
    for e in events:
        if e.get("type") != "retrieval":
            continue
        returned = e.get("returned")
        if isinstance(returned, list):
            returned_total += len(returned)
        if isinstance(e.get("filtered_out"), int):
            measured_hidden += e["filtered_out"]
            measured_n += 1
        elif isinstance(e.get("top_k"), int) and isinstance(returned, list):
            # Legacy log: reconstruct, and say so.
            inferred_hidden += max(0, e["top_k"] - len(returned))
            inferred_n += 1
    hidden_total = measured_hidden + inferred_hidden
    denom = hidden_total + returned_total
    return {
        "retrievals": measured_n + inferred_n,
        "returned": returned_total,
        "hidden": hidden_total,
        "hidden_ratio": (hidden_total / denom) if denom else None,
        "measured": measured_n,
        "inferred": inferred_n,
        "inferred_hidden": inferred_hidden,
    }


def approval_outcomes(events: list[dict]) -> list[dict[str, Any]]:
    """What happened to actions that needed a human or policy decision.

    `simulated` is surfaced because `tool_executed` events record whether the
    side effect actually ran or was simulated — a dashboard that shows
    "12 executions" without that flag would overstate what happened.
    """
    executed = [e for e in events if e.get("type") == "tool_executed"]
    simulated = sum(1 for e in executed if e.get("simulated"))
    types = Counter(str(e.get("type", "?")) for e in events)
    return [
        {"outcome": "Executed (real side effect)", "count": len(executed) - simulated},
        {"outcome": "Executed (simulated)", "count": simulated},
        {"outcome": "Rejected by human approver", "count": types.get("rejected_by_human", 0)},
        {"outcome": "Blocked by tool policy", "count": types.get("policy_blocked", 0)},
        {"outcome": "Denied at delegation", "count": types.get("delegation_denied", 0)},
    ]


def reliability(events: list[dict]) -> dict[str, Any]:
    """Retry budget usage — the panel that tells you the system is struggling.

    `retry_exhausted` carries `waited` (seconds spent in backoff before giving
    up). Total and max are reported; a percentile over a handful of samples is
    false precision, so it is not attempted.
    """
    scheduled = [e for e in events if e.get("type") == "retry_scheduled"]
    exhausted = [e for e in events if e.get("type") == "retry_exhausted"]
    waited = [float(e["waited"]) for e in exhausted if isinstance(e.get("waited"), (int, float))]
    labels = Counter(str(e.get("label", "(unlabelled)")) for e in exhausted)
    return {
        "retries_scheduled": len(scheduled),
        "retries_exhausted": len(exhausted),
        "exhaustion_rate": (len(exhausted) / len(scheduled)) if scheduled else None,
        "total_backoff_seconds": round(sum(waited), 3),
        "max_backoff_seconds": round(max(waited), 3) if waited else None,
        "by_label": labels.most_common(),
    }


def load_eval_baseline(path: str | Path) -> dict[str, Any] | None:
    """Read the JSON written by `evaluation/run_eval.py --json`.

    Returns None when the file is absent or unreadable. The caller renders
    "not measured yet — run `make eval-json`" instead of a zero: a dashboard that
    shows 0% recall when nobody has measured recall is worse than no panel,
    because it looks like a finding.
    """
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict) or "backends" not in data:
        return None
    return data


def risk_posture(events: list[dict], baseline: dict[str, Any] | None = None) -> dict[str, Any]:
    """One-screen summary: the five numbers a duty officer needs.

    Assembled last because it is the only function that reads both the live
    stream and the offline baseline. `baseline_measured` is a boolean rather
    than a nullable metric so the UI can branch on it without re-checking.
    """
    s = summarize(events)
    acl = acl_filtering(events)
    rel = reliability(events)
    best = None
    if baseline:
        candidates = [b for b in baseline.get("backends", []) if isinstance(b, dict)]
        if candidates:
            best = max(
                candidates,
                key=lambda b: (b.get("recall_at_5") or {}).get("ratio") or 0.0,
            )
    return {
        "refusal_rate": s["refusal_rate"],
        "ungrounded_share": _ungrounded_share(events),
        "acl_hidden_ratio": acl["hidden_ratio"],
        "human_rejections": s["human_rejections"],
        "retries_exhausted": s["retries_exhausted"],
        "baseline_measured": best is not None,
        "baseline": best,
    }


def _ungrounded_share(events: list[dict]) -> float | None:
    """Share of answered questions that carried zero citations.

    The complement of `citation_coverage`'s zero bucket, expressed as a share so
    it can sit in the same row as the other rates. None when nothing has been
    answered yet, so the UI can show "—" rather than 0%.
    """
    answered = [e for e in events if e.get("type") == "ask"]
    if not answered:
        return None
    zero = sum(1 for e in answered if not e.get("n_citations"))
    return zero / len(answered)
