"""agents package — v3 governance orchestration layer (LangGraph).

Depends on langgraph (enabled in requirements.txt). Design red line: the
suspend/resume primitives reuse LangGraph's interrupt()/Command as they are;
this package only does "assembly plus a governance shell" on top.
"""
