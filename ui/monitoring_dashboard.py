"""rag-gov-demo monitoring dashboard — the "how is it behaving?" page.

Launch: streamlit run ui/monitoring_dashboard.py   (or make monitor, see the Makefile)
Data:   GET {API}/audit  +  _out/eval_baseline.json (written by `make eval-json`)

Why this page exists
--------------------
`ui/streamlit_app.py` answers "what did the system say?". This page answers
"how is it behaving, and is the governance actually holding?". A governed
system that cannot show its own guardrails firing is asking to be trusted on
faith; this page is the antidote, and it is read-only by construction.

Read-only by construction: the dashboard only ever GETs the audit endpoint. A
monitoring page that can mutate the system it monitors is an incident waiting to
happen, and for a governance reference implementation that would be self-refuting.

No new dependency: every chart uses Streamlit's built-ins (`st.metric`,
`st.bar_chart`, `st.line_chart`), which accept plain lists and dicts. Pulling in
pandas or plotly to draw five bars would contradict the repo's minimal-dependency
stance — the same stance that makes this demo credible as a governance reference.

Every metric is computed by `ui/monitoring.py` (pure functions, unit-tested);
this file is presentation only.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import streamlit as st

from ui import monitoring

st.set_page_config(page_title="rag-gov-demo · monitoring", page_icon="📈", layout="wide")

# ---------------------------------------------------------------- sidebar

with st.sidebar:
    st.title("Monitoring")
    st.caption("Read-only view over the audit stream")
    api_base = st.text_input("API address", value="http://localhost:8000")
    baseline_path = st.text_input(
        "Evaluation baseline (JSON)",
        value=str(Path(__file__).resolve().parents[1] / "_out" / "eval_baseline.json"),
        help="Written by `make eval-json` (evaluation/run_eval.py --json). "
             "Absent is reported as 'not measured', never as 0%.",
    )

    if st.button("Reload audit stream", type="primary"):
        st.session_state.pop("events", None)

    st.divider()
    st.caption(
        "This page only issues GET requests. Nothing here can change system state — "
        "a monitoring surface that can mutate what it monitors is an incident waiting "
        "to happen."
    )

# ---------------------------------------------------------------- data load

if "events" not in st.session_state:
    try:
        resp = httpx.get(f"{api_base}/audit", timeout=10)
        resp.raise_for_status()
        st.session_state["events"] = resp.json().get("events", [])
    except Exception as exc:  # noqa: BLE001 — surfaced, not swallowed
        st.session_state["events"] = []
        st.session_state["load_error"] = str(exc)

events = st.session_state.get("events", [])
load_error = st.session_state.get("load_error")
baseline = monitoring.load_eval_baseline(baseline_path)

if load_error:
    st.error(f"Audit stream unreachable: {load_error}")
    st.stop()

if not events:
    st.info(
        "No audit events yet. Ask a few questions in the main UI "
        "(`streamlit run ui/streamlit_app.py`) or POST to `/ask`, then reload. "
        "An empty stream is reported as empty — not as a row of zeros."
    )
    st.stop()

# ---------------------------------------------------------------- risk posture (top row)

st.header("Risk posture")
st.caption(
    "The five numbers a duty officer needs before anything else. "
    "`—` means *not measured yet*, which is a different statement from 0."
)

posture = monitoring.risk_posture(events, baseline)
s = monitoring.summarize(events)


def pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


cols = st.columns(5)
cols[0].metric("Refusal rate", pct(posture["refusal_rate"]),
               help="Refusals are the guardrail working, not errors. A spike means "
                    "'the guardrail is firing more', which is a different "
                    "investigation from 'the service is failing'.")
cols[1].metric("Ungrounded answers", pct(posture["ungrounded_share"]),
               help="Share of answered questions carrying zero citations. The single "
                    "most useful number on this page.")
cols[2].metric("ACL-hidden chunks", pct(posture["acl_hidden_ratio"]),
               help="From the authoritative `filtered_out` count, not inferred.")
cols[3].metric("Human rejections", posture["human_rejections"],
               help="Actions a human approver stopped. Zero here with non-zero "
                    "executions means the approval gate is not being exercised.")
cols[4].metric("Retries exhausted", posture["retries_exhausted"],
               help="Calls that burned their whole retry budget.")

if posture["baseline_measured"] and posture["baseline"]:
    b = posture["baseline"]
    r5 = b.get("recall_at_5") or {}
    st.success(
        f"Retrieval baseline (best backend **{b.get('backend')}**): "
        f"recall@5 **{r5.get('hits')}/{r5.get('total')}** "
        f"({pct(r5.get('ratio'))}), top-1 "
        f"{(b.get('top1') or {}).get('hits')}/{(b.get('top1') or {}).get('total')}, "
        f"MRR {b.get('mrr')} — measured {b.get('golden')}"
    )
else:
    st.warning(
        "No retrieval baseline on disk. Run `make eval-json` to write one; until then "
        "this panel deliberately shows *not measured* rather than 0%."
    )

# ---------------------------------------------------------------- volume + funnel

left, right = st.columns(2)

with left:
    st.subheader("Answer-path volume per hour")
    vol = monitoring.volume_by_hour(events)
    if vol:
        st.line_chart(vol, x="hour", y="count")
        st.caption(f"{s['answered']} answered · {s['refused']} refused · "
                   f"{s['events_total']} events total · "
                   f"{s['distinct_principals']} distinct principals")
    else:
        st.caption("No answer-path events yet.")

with right:
    st.subheader("Governance funnel")
    st.caption("In the order a request meets each gate — not sorted by size.")
    funnel = monitoring.gate_funnel(events)
    st.bar_chart(funnel, x="label", y="count", horizontal=True)
    with st.expander("Counts as a table"):
        st.table(funnel)

# ---------------------------------------------------------------- why it refused

st.subheader("Why the guardrail fired")
reasons = monitoring.refusal_reasons(events)
if reasons:
    st.bar_chart([{"reason": r, "count": c} for r, c in reasons], x="reason", y="count",
                 horizontal=True)
    if "(unspecified)" in dict(reasons):
        st.warning(
            "Some refusals carry no reason. \"We refuse and cannot say why\" is itself "
            "a finding — the audit stream should be able to answer *why did the system "
            "refuse at that moment*."
        )
else:
    st.caption("No refusals recorded.")

# ---------------------------------------------------------------- grounding + ACL

left, right = st.columns(2)

with left:
    st.subheader("Citations per answered question")
    dist = monitoring.citation_coverage(events)
    if dist:
        st.bar_chart(dist, x="citations", y="count")
        zero = next((d["count"] for d in dist if d["citations"] == 0), 0)
        if zero:
            st.warning(f"{zero} answered question(s) carried **zero** citations — "
                       "answered without grounding. The average would hide this; the "
                       "zero bucket does not.")
    else:
        st.caption("No answered questions yet.")

with right:
    st.subheader("Who is asking")
    principals = monitoring.principal_distribution(events)
    if principals:
        st.bar_chart(principals, x="principal", y="count", horizontal=True)
    acl = monitoring.acl_filtering(events)
    st.caption(
        f"ACL filtering: **{acl['hidden']}** chunk(s) withheld across "
        f"{acl['retrievals']} retrieval(s) "
        f"({pct(acl['hidden_ratio'])} of what the index surfaced). "
        + (f"**{acl['inferred']} of those are reconstructed** from legacy logs that "
           "predate the `filtered_out` field — treat them as estimates."
           if acl["inferred"] else "All measured from the authoritative `filtered_out` count.")
    )

# ---------------------------------------------------------------- approvals + reliability

left, right = st.columns(2)

with left:
    st.subheader("Approval outcomes")
    st.caption("`simulated` is split out: \"12 executions\" without that flag would "
               "overstate what actually happened.")
    st.bar_chart(monitoring.approval_outcomes(events), x="outcome", y="count",
                 horizontal=True)

with right:
    st.subheader("Reliability")
    rel = monitoring.reliability(events)
    r1, r2, r3 = st.columns(3)
    r1.metric("Retries scheduled", rel["retries_scheduled"])
    r2.metric("Exhausted", rel["retries_exhausted"])
    r3.metric("Max backoff", f"{rel['max_backoff_seconds']}s"
              if rel["max_backoff_seconds"] is not None else "—")
    if rel["by_label"]:
        st.caption("Exhausted by label: " +
                   ", ".join(f"{k} ({v})" for k, v in rel["by_label"]))

# ---------------------------------------------------------------- raw stream

with st.expander("Raw audit events (last 50)"):
    st.caption("The dashboard is a view over this stream, never a replacement for it.")
    st.json(json.dumps(events[-50:], ensure_ascii=False, indent=2))

st.divider()
st.caption(
    f"Window: {s['first_event_at']} → {s['last_event_at']} · "
    "metrics computed by ui/monitoring.py (pure functions, unit-tested)"
)
