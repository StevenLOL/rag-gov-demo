"""Tests for the asset engine and the licensing gate.

The three things asserted here map directly onto the governance claims the demo makes:
1. Unregistered asset packages are denied by default (anything outside the allow-list
   is refused, rather than anything outside a block-list being allowed);
2. The licensing gate rejects before human approval happens ("approved" does not
   equal "lawful");
3. Sampling/classification is a deterministic, reproducible process (same input ->
   same samples, which makes audit replay possible).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from helpers import make_package
from ragdemo import assets, policy


# ---------------------------------------------------------------- fixtures

@pytest.fixture
def pkg(monkeypatch, tmp_path):
    """Point the assets/policy source of truth at the synthetic package (cases stay isolated)."""
    info = make_package(tmp_path)
    monkeypatch.setattr(assets, "POLICY_PATH", info["policy"])
    assets.load_policy.cache_clear()
    yield info
    assets.load_policy.cache_clear()


# ---------------------------------------------------------------- licensing gate

def test_unregistered_package_is_denied_by_default(pkg):
    """Unregistered = unauthorized = denied (explicit deny beats implicit allow)."""
    assert assets.get_package("no-such-package") is None
    ok, reason = policy.check_tool_policy(
        "extract_game_assets", {"package": "no-such-package", "use": "reference"}
    )
    assert ok is False and "denied by default" in reason


def test_license_gate_blocks_denied_use(pkg):
    """Use falls within denied_use -> the licensing gate refuses."""
    ok, reason = policy.check_tool_policy(
        "extract_game_assets", {"package": "test-pkg", "use": "ship"}
    )
    assert ok is False
    assert "TEST-ONLY" in reason and "ship" in reason


def test_license_gate_allows_reference(pkg):
    """Use falls within allowed_use -> allowed (an auditable reason is also returned)."""
    ok, reason = policy.check_tool_policy(
        "extract_game_assets", {"package": "test-pkg", "use": "reference"}
    )
    assert ok is True and reason


def test_policy_gate_skips_unbound_tools(pkg):
    """Only registered tools go through the licensing gate (search_docs and the like pass through)."""
    assert policy.check_tool_policy("search_docs", {})[0] is True


# ---------------------------------------------------------------- classification and sampling

def test_classify_by_keywords_is_transparent(pkg):
    """Classification is pure string matching: explainable, auditable (no semantic model, no black box)."""
    names = ["data/gfx/grass_01.png", "data/gfx/npc/hero.png", "data/gfx/zzz.png"]
    cats = assets.classify(names, assets.load_categories())
    assert "grass" in cats and "data/gfx/grass_01.png" in cats["grass"]
    assert "characters" in cats and "data/gfx/npc/hero.png" in cats["characters"]
    # Images matching no keyword must not appear out of nowhere
    assert "data/gfx/zzz.png" not in [n for v in cats.values() for n in v]


def test_stratified_pick_is_deterministic_and_bounded(pkg):
    """Sampling determinism: same input always yields the same result (a prerequisite for audit replay), and never exceeds limit."""
    names = [f"data/gfx/grass_{i:02d}.png" for i in range(30)]
    a = assets.stratified_pick(names, 3)
    b = assets.stratified_pick(names, 3)
    assert a == b and len(a) == 3


# ---------------------------------------------------------------- scanning and export (needs Pillow)

def test_scan_is_readonly(pkg):
    """Scanning only describes "what is in the package"; it produces no files."""
    before = {p.name for p in pkg["zip"].parent.iterdir()}
    r = assets.scan_package("test-pkg", per_category=2)
    assert r.total_images == 10
    assert r.categories["grass"] == 5 and r.categories["characters"] == 2
    assert len(r.samples["grass"]) == 2
    assert {p.name for p in pkg["zip"].parent.iterdir()} == before  # zero write side effects


def test_extract_writes_files_only_when_called(pkg, tmp_path):
    """Export is the only place a write side effect happens; the directory does not
    exist before the call and files really land on disk after it."""
    pytest.importorskip("PIL")
    out = tmp_path / "out"
    res = assets.extract_assets("test-pkg", out, categories=["grass"], per_category=3, size=16)
    assert res["written_count"] == 3
    assert out.exists() and len(list(out.rglob("*.png"))) == 3


def test_extract_without_approval_never_happens_via_policy_path(pkg, tmp_path):
    """The export function itself makes no policy judgment — policy runs before it.

    This test locks in the boundary of responsibility: the execution layer stays
    "dumb" so the policy layer can be tested in isolation.
    (Therefore calling extract_assets directly still writes to disk; blocking is
    policy.py's job.)
    """
    pytest.importorskip("PIL")
    out = tmp_path / "raw"
    assets.extract_assets("test-pkg", out, categories=["desert"], per_category=1)
    assert len(list(out.rglob("*.png"))) == 1


# ---------------------------------------------------------------- real package (test if present, skip if not)

REAL_PKG = "tome-1.7.6-gfx"


def test_real_package_scan_if_present():
    """When the real package is present, run a read-only scan over it (306MB / 21,161 PNGs;
    the source of the empirical numbers)."""
    pkg = assets.get_package(REAL_PKG)  # uses the repository's own asset_policy.yaml
    if pkg is None or not assets._source_exists(pkg.path):
        pytest.skip(f"real asset package unavailable: {REAL_PKG}")
    r = assets.scan_package(REAL_PKG, per_category=3)
    assert r.total_images > 10000, "real package should hold tens of thousands of images"
    assert len(r.categories) >= 5
