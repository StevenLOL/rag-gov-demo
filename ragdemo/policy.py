"""第二道闸：授权用途校验（policy gate）。

【三道闸的分工——这是本 demo 与「普通审批流」最不一样的地方】

  第一道 scopes.yaml      权限闸：工具在不在白名单？越权 → UNAUTHORIZED（不给审批机会）
  第二道 asset_policy.yaml 授权闸：这批素材能不能这么用？越界 → BLOCKED_BY_POLICY
  第三道 risk + interrupt  风险闸：高风险动作 → 挂起等人工决定（approve/reject）

关键区别（面试时最容易被追问的一点）：
  - 审批闸是「让人看一眼」，授权闸是「根本不该做」。
    把授权问题丢给人工审批是错误的治理设计：审批人并不比策略更懂
    COPYING-MEDIA 写了什么，而且"批准了"不等于"合法"。
  - 因此授权拒绝发生在 interrupt 之前：连挂起的机会都不给，直接 BLOCKED。
    这条由 tests/test_assets.py::test_license_gate_blocks_before_approval 断言。

【为什么值得做】对齐 Micron GenAI COE 的 G4（信任与控制 15%）与
DSO JD 的 D3（AI 治理 20%）：把一条法务条款变成 CI 里可断言的一行代码。
"""

from __future__ import annotations

from typing import Any

from .assets import get_package

# 登记「哪些工具需要过授权闸」——策略只作用于有授权语义的工具，其余直通。
POLICY_BOUND_TOOLS = {"extract_game_assets"}


def check_tool_policy(tool: str, params: dict[str, Any]) -> tuple[bool, str]:
    """校验一次工具调用的授权合规性。

    返回 (是否放行, 理由)。放行时理由为空串，方便审计直接落库。
    """
    if tool not in POLICY_BOUND_TOOLS:
        return True, ""

    package_id = params.get("package")
    use = params.get("use", "reference")  # 默认按「仅参考」处理（最小授权）

    if not package_id:
        return False, "缺少 package 参数（未登记素材包一律拒绝）"

    pkg = get_package(package_id)
    if pkg is None:
        return False, f"未登记的素材包 {package_id!r}：默认拒绝（未在 asset_policy.yaml 声明授权）"

    ok, reason = pkg.check_use(use)
    if not ok:
        return False, f"{reason}｜素材包={package_id}"
    return True, reason
