"""v3 治理编排骨架（占位文件——装 langgraph 后启用，v1/v2 不导入本文件）。

技术骨架（源码级取证见 singapore/docs/067 §2.2、docs/068 §1）：
- 挂起原语：langgraph.types.interrupt —— 抛 GraphInterrupt 暂停图执行；
- 恢复：langgraph.types.Command(resume=...)，与 interrupt 配对；
- 持久游标：config={"configurable": {"thread_id": ...}}；
- 生产状态：PostgresSaver（durable），InMemorySaver 仅限开发；
- 四种人工决策：approve / reject / edit / respond。

设计红线（docs/068）：我们不重造挂起机制，只做"组装 + 治理外壳"。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# v3 依赖启用后取消注释：
# from langgraph.checkpoint.postgres import PostgresSaver
# from langgraph.graph import StateGraph
# from langgraph.types import Command, interrupt


@dataclass
class ToolAction:
    """一次待执行的工具动作（风险分级器的输入）。"""

    tool: str            # 工具名，必须能在 scopes.yaml 中找到
    params: dict         # 参数快照（审计落库用）


@dataclass
class ApprovalDecision:
    """人工决定（interrupt(response_schema=) 的强类型恢复值）。"""

    type: Literal["approve", "reject", "edit", "respond"]
    operator: str        # 操作人（审计问责字段）
    note: str = ""       # 拒绝理由 / 编辑后的参数说明


def risk_gate(state: dict) -> dict:
    """风险分级节点（v3 核心，伪代码——接线时按 LangGraph 节点签名实现）。

    规则（与 tools/scopes.yaml 一致）：
    - risk=low  → 直接执行，事后审计；
    - risk=high → interrupt() 强制挂起，等人工批准后才执行；
    - 工具不在白名单 → 直接拒绝（越权，tests/test_governance.py 断言）。
    """
    action: ToolAction = state["pending_action"]
    spec = load_scope(action.tool)  # TODO(v3): scopes.yaml 加载与缓存
    if spec is None:
        return {"result": "UNAUTHORIZED", "audit": {"tool": action.tool}}
    if spec["risk"] == "high":
        decision = interrupt(  # noqa: F821 —— v3 启用
            {"tool": action.tool, "params": action.params, "scope": spec["scope"]},
            response_schema=ApprovalDecision,
        )
        if decision.type == "reject":
            return {"result": "REJECTED_BY_HUMAN", "audit": vars(decision)}
    return {"result": "EXECUTED", "audit": {"tool": action.tool}}


def load_scope(tool: str) -> dict | None:
    """TODO(v3)：读取 tools/scopes.yaml 并缓存；越权测试依赖此函数。"""
    raise NotImplementedError
