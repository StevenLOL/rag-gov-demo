"""素材引擎与授权闸测试。

断言的三件事，正好对应 demo 想说明的治理主张：
1. 未登记素材包默认拒绝（白名单之外即拒绝，而不是黑名单之外即放行）；
2. 授权闸拒绝发生在人工审批之前（"批准了"不等于"合法"）；
3. 抽样/分类是可复现的确定性过程（同样的输入 → 同样的样本，便于审计复盘）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from helpers import make_package
from ragdemo import assets, policy


# ---------------------------------------------------------------- 夹具

@pytest.fixture
def pkg(monkeypatch, tmp_path):
    """把 assets/policy 的策略源切到合成包（每个用例互不污染）。"""
    info = make_package(tmp_path)
    monkeypatch.setattr(assets, "POLICY_PATH", info["policy"])
    assets.load_policy.cache_clear()
    yield info
    assets.load_policy.cache_clear()


# ---------------------------------------------------------------- 授权闸

def test_unregistered_package_is_denied_by_default(pkg):
    """未登记 = 未授权 = 拒绝（显式 deny 优于隐式 allow）。"""
    assert assets.get_package("no-such-package") is None
    ok, reason = policy.check_tool_policy(
        "extract_game_assets", {"package": "no-such-package", "use": "reference"}
    )
    assert ok is False and "默认拒绝" in reason


def test_license_gate_blocks_denied_use(pkg):
    """用途在 denied_use 内 → 授权闸拒绝。"""
    ok, reason = policy.check_tool_policy(
        "extract_game_assets", {"package": "test-pkg", "use": "ship"}
    )
    assert ok is False
    assert "TEST-ONLY" in reason and "ship" in reason


def test_license_gate_allows_reference(pkg):
    """用途在 allowed_use 内 → 放行（放行的同时也回一条可审计的理由）。"""
    ok, reason = policy.check_tool_policy(
        "extract_game_assets", {"package": "test-pkg", "use": "reference"}
    )
    assert ok is True and reason


def test_policy_gate_skips_unbound_tools(pkg):
    """只有登记过的工具需要过授权闸（search_docs 之类直通，避免误伤）。"""
    assert policy.check_tool_policy("search_docs", {})[0] is True


# ---------------------------------------------------------------- 分类与抽样

def test_classify_by_keywords_is_transparent(pkg):
    """分类是纯字符串匹配：可解释、可审计（不做语义模型，避免黑箱）。"""
    names = ["data/gfx/grass_01.png", "data/gfx/npc/hero.png", "data/gfx/zzz.png"]
    cats = assets.classify(names, assets.load_categories())
    assert "草地" in cats and "data/gfx/grass_01.png" in cats["草地"]
    assert "人物" in cats and "data/gfx/npc/hero.png" in cats["人物"]
    # 未命中任何关键词的图片不应凭空出现
    assert "data/gfx/zzz.png" not in [n for v in cats.values() for n in v]


def test_stratified_pick_is_deterministic_and_bounded(pkg):
    """抽样确定性：同样输入必得同样结果（审计复盘的前提），且不超过 limit。"""
    names = [f"data/gfx/grass_{i:02d}.png" for i in range(30)]
    a = assets.stratified_pick(names, 3)
    b = assets.stratified_pick(names, 3)
    assert a == b and len(a) == 3


# ---------------------------------------------------------------- 扫描与导出（需 Pillow）

def test_scan_is_readonly(pkg):
    """扫描只描述「包里有什么」，不产生任何文件。"""
    before = {p.name for p in pkg["zip"].parent.iterdir()}
    r = assets.scan_package("test-pkg", per_category=2)
    assert r.total_images == 10
    assert r.categories["草地"] == 5 and r.categories["人物"] == 2
    assert len(r.samples["草地"]) == 2
    assert {p.name for p in pkg["zip"].parent.iterdir()} == before  # 零写副作用


def test_extract_writes_files_only_when_called(pkg, tmp_path):
    """导出是唯一写副作用发生地；调用前目录不存在，调用后确实落盘。"""
    pytest.importorskip("PIL")
    out = tmp_path / "out"
    res = assets.extract_assets("test-pkg", out, categories=["草地"], per_category=3, size=16)
    assert res["written_count"] == 3
    assert out.exists() and len(list(out.rglob("*.png"))) == 3


def test_extract_without_approval_never_happens_via_policy_path(pkg, tmp_path):
    """导出函数本身不做策略判断——策略在它之前。

    这条测试锁住职责边界：执行层保持"傻"，策略层才能被单独测试。
    （因此直接调用 extract_assets 会照常落盘；阻断由 policy.py 负责。）
    """
    pytest.importorskip("PIL")
    out = tmp_path / "raw"
    assets.extract_assets("test-pkg", out, categories=["沙漠"], per_category=1)
    assert len(list(out.rglob("*.png"))) == 1


# ---------------------------------------------------------------- 真实素材包（有则测，无则跳过）

REAL_PKG = "tome-1.7.6-gfx"


def test_real_package_scan_if_present():
    """真实素材包存在时跑一遍只读扫描（306MB / 21161 张 PNG，实证数据来源）。"""
    pkg = assets.get_package(REAL_PKG)  # 走仓库自带的 asset_policy.yaml
    if pkg is None or not assets._source_exists(pkg.path):
        pytest.skip(f"真实素材包不可用：{REAL_PKG}")
    r = assets.scan_package(REAL_PKG, per_category=3)
    assert r.total_images > 10000, "真实包应有两万张量级图片"
    assert len(r.categories) >= 5
