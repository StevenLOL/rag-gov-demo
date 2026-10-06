"""agents package — v3 governance orchestration layer (LangGraph).

Depends on langgraph (enabled in requirements.txt). Design red lines per
singapore/docs/068: the suspend/resume primitives fully reuse LangGraph's
interrupt()/Command; we only do "assembly + a governance shell".
"""
