"""v3 治理编排（v3a 阶段：最小可运行版）。

已实现（对齐 singapore/docs/067 §3.3 骨架、docs/068 复用判定）：
- 三道闸：权限闸（scopes.yaml 白名单）→ 授权闸（asset_policy.yaml 用途白名单）
          → 风险闸（risk=high 时 interrupt 挂起）；
  顺序不可换：授权拒绝发生在挂起之前——"批准了"不等于"合法"，
  法务条款不该由审批人临场判断（ragdemo/policy.py 头部有完整论证）。
- 挂起原语：LangGraph interrupt() —— 高风险动作强制暂停等人工决定（approve/reject）；
- 恢复：Command(resume=...) + thread_id 持久游标（checkpointer 用 InMemorySaver；
  生产须换 PostgresSaver，接口不变——见 docs/GOVERNANCE.md Manage 映射）；
- 越权：工具不在 scopes.yaml 白名单 → 直接拒绝，不产生 interrupt；
- 副作用恰执行一次：执行放在独立 execute 节点，审批恢复后经条件边到达，
  天然保证"恢复≠重放副作用"（tests/test_governance.py 断言）；
- v3b 起 execute 节点通过 ragdemo/tools_impl.py 分派到真实实现
  （search_docs / scan_asset_package / extract_game_assets），未注册工具仍走受控模拟。

已知边界（诚实清单）：
- 决策类型当前支持 approve/reject；edit/respond 的 UI 语义在 Streamlit 审批卡（v3b）补；
- checkpointer 为内存版，进程重启丢会话——生产接 Postgres 是 v3c 任务。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, TypedDict

import yaml
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command, interrupt

from ragdemo import audit, policy
from ragdemo.config import BASE_DIR
from ragdemo.tools_impl import dispatch

SCOPES_PATH = Path(BASE_DIR) / "tools" / "scopes.yaml"


@lru_cache(maxsize=1)
def load_scopes() -> dict[str, dict[str, Any]]:
    """加载并缓存 scopes.yaml（越权判定的唯一数据源）。"""
    raw = yaml.safe_load(SCOPES_PATH.read_text(encoding="utf-8"))
    return raw.get("tools", {})


def load_scope(tool: str) -> dict[str, Any] | None:
    """返回工具的权限声明；未声明 = 越权（返回 None）。"""
    return load_scopes().get(tool)


class GovState(TypedDict, total=False):
    """治理编排的图状态。"""

    pending_action: dict        # {"tool": str, "params": dict}
    decision: dict | None       # 人工/自动决定（审计落库用）
    result: str                 # EXECUTED / REJECTED_BY_HUMAN / UNAUTHORIZED / BLOCKED_BY_POLICY
    executed: list[str]         # 副作用清单：实际执行过的工具（恰一次性断言依据）
    output: dict                # 工具真实返回值（v3b 起）


def policy_gate(state: GovState) -> dict:
    """第二道闸：授权校验（用途白名单）。

    与 risk_gate 的分工：本闸拒绝的是「根本不该做」的动作，
    因此不给 interrupt 机会——它发生在人工审批之前。
    """
    action = state["pending_action"]
    tool = action["tool"]
    params = action.get("params", {})

    ok, reason = policy.check_tool_policy(tool, params)
    if not ok:
        # 授权拒绝也留痕：审计要能回答"系统当时为什么不放行"
        audit.append_event(
            "policy_blocked",
            {"tool": tool, "params": params, "reason": reason},
            log_path=_audit_log_path,
        )
        return {"result": "BLOCKED_BY_POLICY", "output": {"reason": reason}}
    return {}


def _route_after_policy(state: GovState) -> str:
    """条件边：授权被拒 → 结束；放行 → 进入风险闸。"""
    if state.get("result") == "BLOCKED_BY_POLICY":
        return END
    return "risk_gate"


def risk_gate(state: GovState) -> dict:
    """风险分级节点（第三道闸）：白名单校验 → 低风险直通 / 高风险 interrupt 挂起。"""
    action = state["pending_action"]
    tool = action["tool"]
    spec = load_scope(tool)

    if spec is None:
        # 越权：白名单外的工具直接拒绝，不给 interrupt 机会（拒绝要发生在挂起之前）
        return {"result": "UNAUTHORIZED", "decision": None}

    if spec["risk"] == "low":
        return {"decision": {"type": "approve", "operator": "system", "risk": "low"}}

    # 高风险：interrupt 挂起。首次执行抛 GraphInterrupt；人工 Command(resume=...)
    # 恢复时本节点从头重跑，interrupt() 直接返回恢复值——LangGraph 官方语义。
    decision: dict = interrupt(
        {"tool": tool, "params": action.get("params", {}), "scope": spec["scope"]}
    )
    if decision.get("type") == "reject":
        return {"result": "REJECTED_BY_HUMAN", "decision": decision}
    return {"decision": decision}


def execute(state: GovState) -> dict:
    """执行节点：副作用唯一发生地。只有 risk_gate 放行的动作才到达这里。"""
    action = state["pending_action"]
    tool = action["tool"]
    params = action.get("params", {})
    # v3b：分派到真实实现；未注册工具（export_report/delete_record 等）仍为受控模拟，
    # 以免演示/测试产生真实破坏性副作用。
    output = dispatch(tool, params)
    executed = list(state.get("executed", [])) + [tool]
    audit.append_event(
        "tool_executed",
        {
            "tool": tool,
            "params": params,
            "decision": state.get("decision"),
            "simulated": bool(output.get("simulated")),
        },
        log_path=_audit_log_path,
    )
    return {"result": "EXECUTED", "executed": executed, "output": output}


def _route_after_gate(state: GovState) -> str:
    """条件边：拒绝/越权 → 结束；放行 → 执行节点。"""
    if state.get("result") in ("REJECTED_BY_HUMAN", "UNAUTHORIZED"):
        return END
    return "execute"


# 审计落盘路径由 build_graph 注入（测试用临时路径；默认走 config.AUDIT_LOG）
_audit_log_path: Path | None = None


def build_graph(audit_log: Path | None = None):
    """构建治理编排图。

    audit_log: 审计 JSONL 路径覆盖（测试注入用）；None 时用 ragdemo.config.AUDIT_LOG。
    """
    global _audit_log_path
    _audit_log_path = audit_log

    graph = StateGraph(GovState)
    graph.add_node("policy_gate", policy_gate)
    graph.add_node("risk_gate", risk_gate)
    graph.add_node("execute", execute)
    # 入口 = 授权闸（第二道）；权限校验在 risk_gate 内（第一道，需先取 scope 声明）
    graph.set_entry_point("policy_gate")
    graph.add_conditional_edges("policy_gate", _route_after_policy)
    graph.add_conditional_edges("risk_gate", _route_after_gate)
    graph.add_edge("execute", END)
    # InMemorySaver：开发/测试用；生产必须 PostgresSaver（thread_id 语义不变）
    return graph.compile(checkpointer=InMemorySaver())


def resume(graph, thread_id: str, decision: dict) -> dict:
    """人工决定恢复执行的便捷封装（对应 API 层的 /approve 端点，v3b）。"""
    return graph.invoke(
        Command(resume=decision), config={"configurable": {"thread_id": thread_id}}
    )


def json_dumps(value: Any) -> str:
    """审计/调试用安全序列化。"""
    return json.dumps(value, ensure_ascii=False, default=str)
