"""Audit sink tests: the write side and the read side must agree on the destination.

Regression guard: append_event() honors the process-level active stream
(set_log_path, used by the governance graph), but read_events() used to ignore
it -- the /audit endpoint would then report one log while events landed in
another.
"""

from ragdemo import audit


def test_read_events_honors_the_active_log_path(tmp_path):
    log = tmp_path / "active.jsonl"
    audit.set_log_path(log)
    try:
        audit.append_event("ask", {"question": "q"})
        events = audit.read_events()  # no explicit path: must follow the active stream
        assert [e["type"] for e in events] == ["ask"]
        assert events[0]["question"] == "q"
    finally:
        audit.set_log_path(None)  # restore the process default for other tests


def test_explicit_path_overrides_the_active_log_path(tmp_path):
    active = tmp_path / "active.jsonl"
    other = tmp_path / "other.jsonl"
    audit.set_log_path(active)
    try:
        audit.append_event("ask", {}, log_path=other)
        assert audit.read_events(other)[0]["type"] == "ask"
        assert audit.read_events(active) == []
    finally:
        audit.set_log_path(None)


def test_restored_default_lands_in_the_configured_log(tmp_path, monkeypatch):
    """After set_log_path(None), events go to config.AUDIT_LOG again.

    Note the patch target: audit.py does `from .config import AUDIT_LOG`, so
    the name append_event actually reads lives in the audit module namespace.
    """
    default_log = tmp_path / "default.jsonl"
    monkeypatch.setattr(audit, "AUDIT_LOG", default_log)
    audit.set_log_path(None)
    audit.append_event("ask", {"question": "q"})
    assert default_log.exists()
    assert audit.read_events(default_log)[0]["question"] == "q"
