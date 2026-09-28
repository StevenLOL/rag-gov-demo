"""游戏美术素材包引擎：扫描 / 分类 / 分层抽样 / 导出（副作用唯一地）。

【复用与自建的边界——对齐 singapore/docs/068 的 L1-L7 判定】
复用（L1-L2，不重复造轮子）：
  - 分类关键词口径、分层抽样、保留 alpha 的做法，直接移植自实证脚本
    C:/src/games/scripts/03_extract_tengine_gfx_samples.py（167 行）与
    C:/src/games/scripts/12_extract_tome_chars_equips.py（77 行）；
    这两个脚本已在真实素材上跑通：tome-1.7.6-gfx.team 是 306MB / 21161 张 PNG。
自建（L4-L7，本项目的差异化）：
  - 授权策略层（asset_policy.yaml）：「能不能拿去用」从脚本注释升级为可执行门禁；
  - 风险分级与人工审批（scopes.yaml + LangGraph interrupt）：批量导出属高风险动作；
  - 审计留痕：导出谁、导出多少、谁批准的，全部进 JSONL。
换句话说：抽图本身不值钱（Photoshop/remove.bg 都能做），
值钱的是「抽图这个动作被治理」——这正是 DSO/Micron JD 的 G1/G3/G4 维度。

【依赖】Pillow 为可选依赖：仅导出缩略图 / 合成 contact sheet 时需要；
         纯扫描分类（只读 zip 目录）不需要 Pillow。
"""

from __future__ import annotations

import io
import os
import zipfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .config import BASE_DIR

POLICY_PATH = Path(BASE_DIR) / "tools" / "asset_policy.yaml"

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")

# 未配置策略文件时的兜底分类（保证模块可独立使用；正式运行走 YAML）
_FALLBACK_CATEGORIES: dict[str, list[str]] = {"未分类": [""]}


# ---------------------------------------------------------------- 策略加载

@dataclass(frozen=True)
class PackagePolicy:
    """单个素材包的授权声明。"""

    package_id: str
    path: str
    fmt: str                       # team-zip | directory
    license: str
    allowed_use: tuple[str, ...]
    denied_use: tuple[str, ...]
    note: str = ""

    def check_use(self, use: str) -> tuple[bool, str]:
        """校验用途是否被授权。返回 (是否放行, 理由)。

        判定顺序：显式禁止优先 → 再看是否在允许列表内。
        即「白名单之外即拒绝」，而不是「黑名单之外即放行」。
        """
        if use in self.denied_use:
            return False, f"用途 {use!r} 被显式禁止（license={self.license}）"
        if use not in self.allowed_use:
            return False, (
                f"用途 {use!r} 不在授权范围内（license={self.license}，"
                f"允许 {list(self.allowed_use)}）"
            )
        return True, f"用途 {use!r} 已授权（license={self.license}）"


@lru_cache(maxsize=1)
def load_policy() -> dict[str, Any]:
    """加载 asset_policy.yaml（lru_cache：一次进程只读一次盘）。"""
    if not POLICY_PATH.exists():
        return {"packages": {}, "categories": _FALLBACK_CATEGORIES}
    return yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8")) or {}


def load_categories() -> dict[str, list[str]]:
    """分类关键词表（策略外置，改分类不用改代码）。"""
    return load_policy().get("categories") or _FALLBACK_CATEGORIES


def get_package(package_id: str) -> PackagePolicy | None:
    """按 id 取素材包策略；未登记的包一律视为「未授权」（默认拒绝）。"""
    raw = load_policy().get("packages", {}).get(package_id)
    if raw is None:
        return None
    return PackagePolicy(
        package_id=package_id,
        path=raw.get("path", ""),
        fmt=raw.get("format", "team-zip"),
        license=raw.get("license", "unknown"),
        allowed_use=tuple(raw.get("allowed_use", [])),
        denied_use=tuple(raw.get("denied_use", [])),
        note=(raw.get("note") or "").strip(),
    )


def list_packages() -> list[dict[str, Any]]:
    """列出全部已登记素材包（供 MCP tools 与 /tools 端点暴露能力）。"""
    out = []
    for pid, raw in load_policy().get("packages", {}).items():
        out.append(
            {
                "package_id": pid,
                "format": raw.get("format"),
                "license": raw.get("license"),
                "allowed_use": raw.get("allowed_use", []),
                "denied_use": raw.get("denied_use", []),
                "exists": _source_exists(raw.get("path", "")),
            }
        )
    return out


def _source_exists(path: str) -> bool:
    """素材源是否存在（本机演示用：真实素材包 306MB 已在 E:/games）。"""
    return bool(path) and os.path.exists(path)


# ---------------------------------------------------------------- 扫描（只读）

@dataclass
class ScanResult:
    """扫描结果：只描述「包里有什么」，不产生任何写操作。"""

    package_id: str
    total_images: int
    categories: dict[str, int] = field(default_factory=dict)
    samples: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "total_images": self.total_images,
            "categories": self.categories,
            "samples": self.samples,
        }


def _list_images_zip(z: zipfile.ZipFile) -> list[str]:
    return [n for n in z.namelist() if n.lower().endswith(IMAGE_EXTS)]


def _list_images_dir(root: Path) -> list[str]:
    if not root.exists():
        return []
    return [
        str(p.relative_to(root)).replace("\\", "/")
        for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    ]


def classify(names: list[str], categories: dict[str, list[str]]) -> dict[str, list[str]]:
    """按关键词把图片路径归类。一个文件可同时命中多类（美术素材本就有多重语义）。"""
    out: dict[str, list[str]] = {}
    for label, kws in categories.items():
        hits = [n for n in names if any(k in n.lower() for k in kws)]
        if hits:
            out[label] = hits
    return out


def stratified_pick(names: list[str], limit: int) -> list[str]:
    """分层抽样：等步长取样，避免同类素材扎堆（移植自 03 号脚本 pick()）。

    同时按文件名前 12 字符去重，防止同一素材的 _a/_b 变体占满名额。
    """
    if limit <= 0 or not names:
        return []
    step = max(1, len(names) // (limit * 3))
    picked: list[str] = []
    seen: set[str] = set()
    for i in range(0, len(names), step):
        n = names[i]
        stem = n.rsplit("/", 1)[-1][:12]
        if stem in seen:
            continue
        seen.add(stem)
        picked.append(n)
        if len(picked) >= limit:
            break
    return picked


def scan_package(package_id: str, per_category: int = 5) -> ScanResult:
    """只读扫描：统计总数、分类分布、每类抽样若干路径。

    本函数是「低风险只读」能力的实现，不写任何文件，因此不需要人工审批。
    """
    pkg = get_package(package_id)
    if pkg is None:
        raise KeyError(f"未登记的素材包: {package_id}（默认拒绝）")
    source = Path(pkg.path)

    if pkg.fmt == "team-zip":
        if not source.is_file():
            raise FileNotFoundError(f"素材包不存在: {source}")
        with zipfile.ZipFile(source) as z:
            names = _list_images_zip(z)
    else:
        names = _list_images_dir(source)

    cats = classify(names, load_categories())
    return ScanResult(
        package_id=package_id,
        total_images=len(names),
        categories={k: len(v) for k, v in cats.items()},
        samples={k: stratified_pick(v, per_category) for k, v in cats.items()},
    )


# ---------------------------------------------------------------- 导出（副作用）

def extract_assets(
    package_id: str,
    out_dir: str | Path,
    categories: list[str] | None = None,
    per_category: int = 3,
    size: int | None = None,
) -> dict[str, Any]:
    """把抽样结果落到磁盘 —— 本模块唯一的写副作用发生地。

    调用方必须已经过了三道闸（权限 → 授权 → 审批）；本函数不做任何策略判断，
    保证「策略」与「执行」分离：策略可测试，执行可审计。

    size: 若给出，则等比缩放到该边长（缩略图模式，减少磁盘占用）。
    """
    from PIL import Image  # 可选依赖：仅真正导出时才导入

    pkg = get_package(package_id)
    if pkg is None:
        raise KeyError(f"未登记的素材包: {package_id}（默认拒绝）")

    want = set(categories) if categories else None
    scan = scan_package(package_id, per_category=per_category)
    picked: list[str] = []
    for label, names in scan.samples.items():
        if want and label not in want:
            continue
        picked.extend(names)

    out_root = Path(out_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    source = Path(pkg.path)

    def _save(raw: bytes, rel: str) -> None:
        """把一张图按 rel 的相对路径落盘，保留 alpha（立绘/图标不能合底色）。"""
        im = Image.open(io.BytesIO(raw))
        im = im.convert("RGBA")
        if size is not None:
            im.thumbnail((size, size), Image.LANCZOS)
        dst = out_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        im.save(dst)
        written.append(str(dst))

    if pkg.fmt == "team-zip":
        with zipfile.ZipFile(source) as z:
            for rel in picked:
                try:
                    _save(z.read(rel), rel.replace("data/gfx/", ""))
                except Exception as exc:  # 单张失败不影响整批，但必须暴露
                    written.append(f"FAILED:{rel}:{exc}")
    else:
        for rel in picked:
            _save((source / rel).read_bytes(), rel)

    return {
        "package_id": package_id,
        "out_dir": str(out_root),
        "requested_categories": sorted(want) if want else "ALL",
        "written_count": len(written),
        "written": written[:50],  # 只回前 50 条，避免 MCP 响应过大
    }
