"""Audit log (v1 shape: local JSONL; v3 migrates to a Postgres audit table).

Design intent:
- Establish "leave a trace at every step" from v1 onward: every Q&A turn (including refusals)
  writes one JSON line;
- v3 event types will expand to approval_granted / approval_rejected / unauthorized_blocked;
  see the Manage function mapping in docs/GOVERNANCE.md for the table schema;
- Engineering anchor for the MDDI public-sector rule "use AI at your own responsibility" →
  first you must be able to look up "what the AI actually answered".
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .config import AUDIT_LOG


def append_event(event_type: str, payload: dict, log_path: Path | None = None) -> None:
    """Append one audit event (JSONL, one event per line).

    event_type: ask / refused (v1); v3 adds approval-type events.
    """
    path = log_path or AUDIT_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "type": event_type,
        **payload,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_events(log_path: Path | None = None) -> list[dict]:
    """Read all audit events (shared by the /audit endpoint and future governance reports)."""
    path = log_path or AUDIT_LOG
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
