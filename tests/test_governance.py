"""治理测试（v1 就进 CI 的部分：权限白名单 schema 校验）。

v3 将追加三条核心用例（当前 skip 占位，装 langgraph 后启用）：
1. 高风险动作未经批准必然挂起（interrupt 强制）
2. 越权工具调用必然被拒绝
3. interrupt-resume 恢复后不重放已执行节点
"""

from pathlib import Path

import pytest
import yaml

SCOPES_PATH = Path(__file__).resolve().parent.parent / "tools" / "scopes.yaml"
VALID_RISKS = {"low", "high"}


def _scopes() -> dict:
    return yaml.safe_load(SCOPES_PATH.read_text(encoding="utf-8"))


def test_scopes_file_exists_and_parses():
    scopes = _scopes()
    assert "tools" in scopes and len(scopes["tools"]) >= 4


def test_every_tool_declares_scope_and_risk():
    """每个工具必须声明 scope + risk——缺失即 CI 失败（治理即代码的第一条）。"""
    for name, spec in _scopes()["tools"].items():
        assert spec.get("scope"), f"{name} 缺少 scope 声明"
        assert spec.get("risk") in VALID_RISKS, f"{name} 的 risk 必须是 low/high"
        assert spec.get("data_class"), f"{name} 缺少数据分级"


def test_destructive_tools_are_high_risk():
    """破坏类/外发类工具必须是 high risk（对齐 agent_governance_basics.md）。"""
    for name in ("delete_record", "export_report", "call_cloud_llm"):
        assert _scopes()["tools"][name]["risk"] == "high", f"{name} 必须标记 high"


@pytest.mark.skip(reason="v3：需安装 langgraph 后启用 interrupt 挂起测试")
def test_high_risk_action_blocks_without_approval():
    ...


@pytest.mark.skip(reason="v3：越权运行时校验待接线")
def test_unscoped_tool_call_is_denied():
    ...


@pytest.mark.skip(reason="v3：interrupt-resume 一致性待接线")
def test_resume_after_interrupt_continues_not_replays():
    ...
