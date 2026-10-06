"""Shared test fixtures: synthetic asset package + policy file.

Why build a synthetic package instead of using the real one:
  - Tests must be fast (the real package is 306MB / 21,161 images, suitable only for
    optional "test-if-present" cases);
  - Tests must be deterministic (a synthetic package has fixed contents, so assertions
    can be precise).
For the real-package scan case, see tests/test_assets.py::test_real_package_scan_if_present.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import yaml


def png_bytes(color=(200, 30, 30, 255), size=(8, 8)) -> bytes:
    """Generate a tiny PNG (avoids committing binary assets to the repository)."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGBA", size, color).save(buf, "PNG")
    return buf.getvalue()


# Image paths inside the synthetic package: deliberately covers three cases —
# "multi-category hits / directory keyword / no hit"
FAKE_NAMES = [
    "data/gfx/grass_01.png", "data/gfx/grass_02.png", "data/gfx/grass_03.png",
    "data/gfx/grass_04.png", "data/gfx/grass_05.png",
    "data/gfx/sand_01.png", "data/gfx/sand_02.png",
    "data/gfx/npc/hero_01.png", "data/gfx/npc/hero_02.png",
    "data/gfx/ui/panel.png",
]


def make_package(tmp_path: Path, name: str = "test-pkg") -> dict:
    """Build a synthetic asset package plus a matching policy file.

    Returns {"package_id": str, "zip": Path, "policy": Path}.
    The caller must point ragdemo.assets.POLICY_PATH at the policy file and clear
    the lru_cache.
    """
    zpath = tmp_path / "fake.team"
    with zipfile.ZipFile(zpath, "w") as z:
        for n in FAKE_NAMES:
            z.writestr(n, png_bytes())

    policy_text = {
        "packages": {
            name: {
                "path": str(zpath).replace("\\", "/"),
                "format": "team-zip",
                "license": "TEST-ONLY",
                "allowed_use": ["reference"],
                "denied_use": ["ship"],
                "note": "synthetic asset package for tests",
            }
        },
        "categories": {"grass": ["grass"], "desert": ["sand"], "characters": ["/npc/"]},
    }
    ppath = tmp_path / "asset_policy.yaml"
    ppath.write_text(yaml.safe_dump(policy_text, allow_unicode=True), encoding="utf-8")
    return {"package_id": name, "zip": zpath, "policy": ppath}
