"""Tests for ui/monitoring.py — synthetic events, no API, no fixture files.

The point of these tests is not coverage for its own sake: every assertion here
corresponds to a way the dashboard could silently lie. A metric computed from a
key no writer emits renders as a permanent zero and trains the reader to ignore
the panel — so each test builds events in the exact shape the real writers emit
(see the taxonomy table in ui/monitoring.py).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui import monitoring  # noqa: E402


def _ask(ts="2026-10-13T11:00:00+0800", n=2, principal="analyst", reason=""):
    return {"ts": ts, "type": "ask", "question": "q", "principal": {"id": principal},
            "mode": "extractive", "n_citations": n, "reason": reason}


def _refused(ts="2026-10-13T11:00:00+0800", principal="analyst", reason="no_coverage"):
    return {"ts": ts, "type": "refused", "question": "q",
            "principal": {"id": principal}, "mode": "extractive", "n_citations": 0,
            "reason": reason}


def _retrieval(top_k=5, returned=3, principal="analyst", filtered_out=None):
    ev = {"ts": "2026-10-13T11:00:00+0800", "type": "retrieval", "tool": "search_docs",
          "principal": {"id": principal}, "query": "x", "top_k": top_k,
          "returned": [f"c{i}" for i in range(returned)]}
    if filtered_out is not None:
        ev["filtered_out"] = filtered_out
    return ev


def _tool_executed(simulated=False):
    return {"ts": "2026-10-13T11:00:00+0800", "type": "tool_executed",
            "tool": "export_report", "decision": {"type": "approve"}, "simulated": simulated}


def _retry_exhausted(waited=1.5, label="llm_call"):
    return {"ts": "2026-10-13T11:00:00+0800", "type": "retry_exhausted", "label": label,
            "attempts": 3, "reason": "max_attempts", "error_class": "TimeoutError",
            "waited": waited}


# ---------------------------------------------------------------- summarize

def test_summarize_counts_refusals_separately_from_answers():
    """A refusal is a successful governance outcome; it must not be an "error"."""
    events = [_ask(), _ask(), _refused(), _refused(reason="low_score")]
    s = monitoring.summarize(events)
    assert s["answered"] == 2
    assert s["refused"] == 2
    assert s["refusal_rate"] == pytest.approx(0.5)
    assert s["events_total"] == 4


def test_summarize_on_empty_stream_reports_none_not_zero():
    """Nothing asked yet must render as "—", not as a 0% rate that looks like a finding."""
    s = monitoring.summarize([])
    assert s["refusal_rate"] is None
    assert s["mean_citations"] is None
    assert s["first_event_at"] is None


def test_summarize_ignores_non_integer_citations():
    """A malformed n_citations must not poison the mean for every other row."""
    events = [_ask(n=2), _ask(n=4), {"ts": "t", "type": "ask", "n_citations": "two"}]
    assert monitoring.summarize(events)["mean_citations"] == pytest.approx(3.0)


# ---------------------------------------------------------------- funnel / reasons

def test_gate_funnel_keeps_declared_order_even_when_counts_differ():
    """Order is the message; sorting by magnitude would put the rarest gate first."""
    events = [_tool_executed(), _tool_executed(), _retry_exhausted()]
    funnel = monitoring.gate_funnel(events)
    keys = [g["key"] for g in funnel]
    assert keys == [k for k, _ in monitoring.GATES]
    assert next(g for g in funnel if g["key"] == "tool_executed")["count"] == 2


def test_refusal_reasons_keeps_unspecified_bucket():
    """"We refuse and don't record why" is itself a finding, not a row to drop."""
    events = [_refused(reason="no_coverage"), _refused(reason=""), _refused(reason="no_coverage")]
    reasons = dict(monitoring.refusal_reasons(events))
    assert reasons["no_coverage"] == 2
    assert reasons["(unspecified)"] == 1


# ---------------------------------------------------------------- volume / citations

def test_volume_by_hour_buckets_and_sorts():
    events = [
        _ask(ts="2026-10-13T11:10:00+0800"),
        _ask(ts="2026-10-13T11:50:00+0800"),
        _ask(ts="2026-10-13T09:05:00+0800"),
    ]
    hours = monitoring.volume_by_hour(events)
    assert [h["hour"] for h in hours] == ["10-13 09:00", "10-13 11:00"]
    assert hours[-1]["count"] == 2


def test_volume_by_hour_skips_unparseable_timestamps():
    """One bad timestamp drops one bucket (visible as a gap), not the whole chart."""
    events = [_ask(ts="not-a-timestamp"), _ask(ts="2026-10-13T11:10:00+0800")]
    assert len(monitoring.volume_by_hour(events)) == 1


def test_citation_coverage_exposes_the_zero_tail():
    """The zero tail is the finding; an average would hide it."""
    events = [_ask(n=0), _ask(n=0), _ask(n=3)]
    dist = monitoring.citation_coverage(events)
    assert dist[0] == {"citations": 0, "count": 2}
    assert monitoring._ungrounded_share(events) == pytest.approx(2 / 3)


# ---------------------------------------------------------------- ACL

def test_acl_filtering_reads_the_authoritative_filtered_out_count():
    """Reads `filtered_out` from tools_impl.py; never infers it from top_k - len(returned)."""
    events = [_retrieval(top_k=5, returned=3, filtered_out=4),
              _retrieval(top_k=5, returned=5, filtered_out=0)]
    acl = monitoring.acl_filtering(events)
    assert acl["retrievals"] == 2
    assert acl["hidden"] == 4
    assert acl["measured"] == 2
    assert acl["inferred"] == 0
    assert acl["hidden_ratio"] == pytest.approx(4 / (4 + 8))


def test_acl_filtering_does_not_confuse_acl_hiding_with_backend_under_returning():
    """The whole reason the field exists: these two cases are indistinguishable by arithmetic.

    Same `top_k - len(returned)` (=4), opposite meanings. Only `filtered_out`
    separates "the ACL hid four restricted chunks" from "the backend found one".
    """
    acl_hid = monitoring.acl_filtering([_retrieval(top_k=5, returned=1, filtered_out=4)])
    backend_short = monitoring.acl_filtering([_retrieval(top_k=5, returned=1, filtered_out=0)])
    assert acl_hid["hidden"] == 4
    assert backend_short["hidden"] == 0


def test_acl_filtering_labels_reconstructed_numbers_as_inferred():
    """Legacy logs without `filtered_out` are reconstructed, and must say so."""
    acl = monitoring.acl_filtering([_retrieval(top_k=5, returned=1)])  # no filtered_out
    assert acl["measured"] == 0
    assert acl["inferred"] == 1
    assert acl["inferred_hidden"] == 4


# ---------------------------------------------------------------- approvals / reliability

def test_approval_outcomes_separates_simulated_from_real_side_effects():
    """"12 executions" without the simulated flag would overstate what happened."""
    events = [_tool_executed(simulated=False), _tool_executed(simulated=True),
              {"ts": "t", "type": "rejected_by_human", "tool": "export_report"}]
    out = {o["outcome"]: o["count"] for o in monitoring.approval_outcomes(events)}
    assert out["Executed (real side effect)"] == 1
    assert out["Executed (simulated)"] == 1
    assert out["Rejected by human approver"] == 1


def test_reliability_reports_backoff_totals_and_labels():
    events = [
        {"ts": "t", "type": "retry_scheduled", "label": "llm_call", "delay": 0.5},
        _retry_exhausted(waited=1.5, label="llm_call"),
        _retry_exhausted(waited=2.5, label="index"),
    ]
    rel = monitoring.reliability(events)
    assert rel["retries_scheduled"] == 1
    assert rel["retries_exhausted"] == 2
    assert rel["total_backoff_seconds"] == pytest.approx(4.0)
    assert rel["max_backoff_seconds"] == pytest.approx(2.5)
    assert dict(rel["by_label"]) == {"llm_call": 1, "index": 1}


# ---------------------------------------------------------------- baseline / posture

def test_load_eval_baseline_returns_none_when_absent(tmp_path):
    assert monitoring.load_eval_baseline(tmp_path / "nope.json") is None


def test_load_eval_baseline_returns_none_on_malformed_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert monitoring.load_eval_baseline(p) is None


def test_load_eval_baseline_rejects_json_without_backends(tmp_path):
    p = tmp_path / "empty.json"
    p.write_text(json.dumps({"generated_at": "x"}), encoding="utf-8")
    assert monitoring.load_eval_baseline(p) is None


def test_load_eval_baseline_reads_run_eval_json_shape(tmp_path):
    """Must match exactly what `run_eval.py --json` writes, key for key."""
    p = tmp_path / "b.json"
    p.write_text(json.dumps({
        "generated_at": "2026-10-13T11:32:01+0800",
        "backends": [
            {"backend": "bm25", "recall_at_5": {"hits": 59, "total": 63, "ratio": 0.936}},
            {"backend": "hybrid", "recall_at_5": {"hits": 31, "total": 31, "ratio": 1.0}},
        ],
    }), encoding="utf-8")
    b = monitoring.load_eval_baseline(p)
    assert b["backends"][1]["backend"] == "hybrid"


def test_risk_posture_flags_unmeasured_baseline_rather_than_zero():
    """baseline_measured=False lets the UI say "not measured yet", not "0% recall"."""
    posture = monitoring.risk_posture([_ask()], baseline=None)
    assert posture["baseline_measured"] is False
    assert posture["baseline"] is None


def test_risk_posture_picks_the_best_backend_from_the_baseline():
    baseline = {"backends": [
        {"backend": "bm25", "recall_at_5": {"ratio": 0.936}},
        {"backend": "hybrid", "recall_at_5": {"ratio": 1.0}},
    ]}
    posture = monitoring.risk_posture([_ask()], baseline=baseline)
    assert posture["baseline_measured"] is True
    assert posture["baseline"]["backend"] == "hybrid"


def test_risk_posture_on_empty_stream_is_all_none():
    posture = monitoring.risk_posture([])
    assert posture["refusal_rate"] is None
    assert posture["ungrounded_share"] is None
    assert posture["acl_hidden_ratio"] is None


# ---------------------------------------------------------------- dashboard contract

def test_dashboard_only_calls_functions_that_exist():
    """Guard the UI -> metrics contract without importing Streamlit.

    Streamlit is deliberately not installed in CI (see requirements.txt), so the
    dashboard module cannot be imported here. Renaming a metrics function would
    otherwise break the page at runtime with no test noticing. This parses the
    dashboard's AST and asserts every `monitoring.<name>` it calls is real.
    """
    import ast

    dash = Path(__file__).resolve().parents[1] / "ui" / "monitoring_dashboard.py"
    tree = ast.parse(dash.read_text(encoding="utf-8"))
    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "monitoring"
    }
    assert called, "dashboard makes no monitoring.* calls — did the import break?"
    missing = [name for name in called if not callable(getattr(monitoring, name, None))]
    assert not missing, f"dashboard calls missing metrics functions: {sorted(missing)}"


def test_dashboard_never_issues_a_write_request():
    """Read-only by construction: a monitoring surface that can mutate is an incident.

    Asserts the dashboard only uses httpx.get. A POST/PUT/DELETE appearing here
    would contradict the stated design and should fail review, not ship.
    """
    import ast

    dash = Path(__file__).resolve().parents[1] / "ui" / "monitoring_dashboard.py"
    tree = ast.parse(dash.read_text(encoding="utf-8"))
    verbs = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "httpx"
    }
    assert verbs <= {"get"}, f"dashboard must only GET; found httpx.{sorted(verbs)}"
