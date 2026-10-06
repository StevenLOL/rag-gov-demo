"""Cross-process state persistence proof (phase 1 = suspend, phase 2 = resume).

Run standalone as `python tests/state_persistence_probe.py <phase> <state_db> <thread_id>`.
Called by tests/test_state_persistence.py in **two real subprocesses** to prove that
the thread_id cursor, once persisted by SqliteSaver, **survives process exit and can
be resumed by a fresh process** (an in-memory checkpointer cannot do this — a process
restart loses the session).

Why subprocesses instead of two graphs in one process: rebuilding a graph inside the
same process only proves "a rebuilt object can read the file"; it cannot prove
"a restarted process can read the file".
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    phase, state_db, thread_id = sys.argv[1], sys.argv[2], sys.argv[3]
    # A standalone process does not inherit pytest's rootdir injection; add the
    # demo root to sys.path ourselves.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    # Must be set before importing ragdemo.config: config reads env at import time.
    os.environ["STATE_DB"] = state_db

    from agents.graph import build_graph, resume as graph_resume

    cfg = {"configurable": {"thread_id": thread_id}}

    if phase == "interrupt":
        app = build_graph()
        # Note: LangGraph's interrupt() does NOT raise under invoke(); it returns
        # __interrupt__ in the result (consistent with tests/test_governance.py).
        out = app.invoke({"pending_action": {"tool": "export_report", "params": {}}}, cfg)
        if "__interrupt__" in out:
            print("INTERRUPTED")
            return 0
        print("NO_INTERRUPT keys=" + ",".join(sorted(out.keys())))
        return 1

    if phase == "resume":
        app = build_graph()  # brand-new graph / brand-new process, cursor read only from state_db
        out = graph_resume(app, thread_id, {"type": "approve", "operator": "probe"})
        executed = out.get("executed") or []
        print("RESUMED executed=" + ",".join(executed))
        return 0 if executed == ["export_report"] else 1

    print("unknown phase")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
