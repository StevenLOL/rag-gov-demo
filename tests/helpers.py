"""测试夹具共享：合成素材包 + 策略文件。

为什么自己造素材包而不是用真实素材：
  - 测试必须快（真实包 306MB / 21161 张，只适合做可选的"有则测"用例）；
  - 测试必须确定（合成包内容固定，断言才能精确）。
真实素材包的扫描用例见 tests/test_assets.py::test_real_package_scan_if_present。
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import yaml


def png_bytes(color=(200, 30, 30, 255), size=(8, 8)) -> bytes:
    """生成一张极小的 PNG（避免往仓库里塞二进制资产）。"""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGBA", size, color).save(buf, "PNG")
    return buf.getvalue()


# 合成包内的图片路径：刻意覆盖「多类命中 / 目录关键词 / 未命中」三种情况
FAKE_NAMES = [
    "data/gfx/grass_01.png", "data/gfx/grass_02.png", "data/gfx/grass_03.png",
    "data/gfx/grass_04.png", "data/gfx/grass_05.png",
    "data/gfx/sand_01.png", "data/gfx/sand_02.png",
    "data/gfx/npc/hero_01.png", "data/gfx/npc/hero_02.png",
    "data/gfx/ui/panel.png",
]


def make_package(tmp_path: Path, name: str = "test-pkg") -> dict:
    """造一个合成素材包 + 对应策略文件。

    返回 {"package_id": str, "zip": Path, "policy": Path}
    调用方需自行把 ragdemo.assets.POLICY_PATH 指向 policy 并清 lru_cache。
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
                "note": "测试用合成素材包",
            }
        },
        "categories": {"草地": ["grass"], "沙漠": ["sand"], "人物": ["/npc/"]},
    }
    ppath = tmp_path / "asset_policy.yaml"
    ppath.write_text(yaml.safe_dump(policy_text, allow_unicode=True), encoding="utf-8")
    return {"package_id": name, "zip": zpath, "policy": ppath}
