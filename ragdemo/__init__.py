"""ragdemo — a governance-first agentic RAG reference implementation (v1 package).

Layer mapping (see the repo README and singapore/docs/067 for details):
- v1: chunker / retriever / citation / llm / audit (the core of this package)
- v2: containerization, Postgres session store, expanded eval (structure reserved)
- v3: agents/graph.py (LangGraph governance orchestration, standalone placeholder,
  not part of v1 dependencies)
"""

__version__ = "0.1.0"
