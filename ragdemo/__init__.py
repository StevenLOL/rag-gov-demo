"""ragdemo —— 治理优先的 agentic RAG 参考实现（v1 包）。

分层对应关系（详见仓库 README 与 singapore/docs/067）：
- v1: chunker / retriever / citation / llm / audit（本包主体）
- v2: 容器化、Postgres 会话库、eval 扩充（结构已预留）
- v3: agents/graph.py（LangGraph 治理编排，独立占位，不进 v1 依赖）
"""

__version__ = "0.1.0"
