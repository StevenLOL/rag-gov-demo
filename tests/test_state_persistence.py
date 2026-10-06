"""Cross-process state persistence: prove that the thread_id cursor, once
persisted by SqliteSaver, survives a process restart.

This is exactly what swapping the checkpointer from InMemorySaver to
SqliteSaver buys — so it must be guarded by a regression test, otherwise
it would silently get reverted.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROBE = Path(__file__).with_name("state_persistence_probe.py")


def _run(phase: str, state_db: Path, thread_id: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(PROBE), phase, str(state_db), thread_id],
        capture_output=True, text=True, timeout=180,
    )


def test_state_survives_process_restart(tmp_path):
    """Process A suspends -> process A exits -> process B (new graph, new
    process) resumes and executes."""
    state_db = tmp_path / "state.db"
    thread_id = "xp-1"

    a = _run("interrupt", state_db, thread_id)
    assert a.returncode == 0, f"phase 1 should suspend but returned {a.returncode}: {a.stdout}{a.stderr}"
    assert "INTERRUPTED" in a.stdout
    assert state_db.exists(), "SqliteSaver should have persisted state.db"

    # The key point: this is a *different process* — an in-memory checkpointer
    # necessarily fails here.
    b = _run("resume", state_db, thread_id)
    assert b.returncode == 0, f"phase 2 resume failed: {b.stdout}{b.stderr}"
    assert "RESUMED executed=export_report" in b.stdout


def test_separate_threads_are_isolated(tmp_path):
    """Different thread_ids are isolated: only the suspended one resumes."""
    state_db = tmp_path / "state.db"

    a = _run("interrupt", state_db, "xp-a")
    assert a.returncode == 0 and "INTERRUPTED" in a.stdout

    b = _run("resume", state_db, "xp-a")
    assert b.returncode == 0 and "executed=export_report" in b.stdout

    # xp-b was never suspended; resuming it must not execute anything.
    c = _run("resume", state_db, "xp-b")
    assert c.returncode != 0, "a never-suspended thread must not resume successfully"
