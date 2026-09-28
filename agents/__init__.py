"""agents 包 —— v3 治理编排层（LangGraph）。

依赖 langgraph（requirements.txt 已启用）。设计红线见 singapore/docs/068：
挂起/恢复原语完全复用 LangGraph interrupt()/Command，我们只做"组装 + 治理外壳"。
"""
