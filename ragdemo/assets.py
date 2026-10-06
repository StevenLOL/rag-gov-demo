"""Game art asset pack engine: scan / classify / stratified sampling / export
(the sole place with side effects).

Reuse vs. build-from-scratch boundary:

Reused (low novelty, no reason to reinvent the wheel):
  - The classification keyword scheme, stratified sampling and the
    alpha-preserving export approach follow common practice for sprite packs.
    While developing this, the reference pack used was a 306 MB Tales of
    Maj'Eyal gfx archive holding 21,161 PNG images.
Built from scratch (what actually differentiates this project):
  - License policy layer (asset_policy.yaml): "may we use this?" is upgraded
    from a comment buried in a script into an executable gate;
  - Risk grading with human approval (scopes.yaml + LangGraph interrupt):
    bulk export is a high-risk action;
  - Audit trail: what was exported, how much, and who approved it — all of it
    goes into JSONL.

In other words, extracting images is not the valuable part (any image tool can
do that); what is valuable is that the extraction action itself is governed.

[Dependencies] Pillow is optional: only needed for exporting thumbnails /
         compositing contact sheets; a pure scan/classify pass (read-only zip
         listing) does not require Pillow.
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

# Fallback classification used when no policy file is configured (keeps the
# module usable standalone; the real run goes through YAML)
_FALLBACK_CATEGORIES: dict[str, list[str]] = {"uncategorized": [""]}


# ---------------------------------------------------------------- Policy loading

@dataclass(frozen=True)
class PackagePolicy:
    """License declaration for a single asset pack."""

    package_id: str
    path: str
    fmt: str                       # team-zip | directory
    license: str
    allowed_use: tuple[str, ...]
    denied_use: tuple[str, ...]
    note: str = ""

    def check_use(self, use: str) -> tuple[bool, str]:
        """Check whether a use is authorized. Returns (allowed, reason).

        Decision order: explicit denial takes precedence → then check whether
        the use is in the allowed list. That is, "deny anything outside the
        whitelist", rather than "allow anything outside the blacklist".
        """
        if use in self.denied_use:
            return False, f"use {use!r} is explicitly denied (license={self.license})"
        if use not in self.allowed_use:
            return False, (
                f"use {use!r} is not within the licensed scope (license={self.license}, "
                f"allowed: {list(self.allowed_use)})"
            )
        return True, f"use {use!r} is authorized (license={self.license})"


@lru_cache(maxsize=1)
def load_policy() -> dict[str, Any]:
    """Load asset_policy.yaml (lru_cache: read from disk only once per process)."""
    if not POLICY_PATH.exists():
        return {"packages": {}, "categories": _FALLBACK_CATEGORIES}
    return yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8")) or {}


def load_categories() -> dict[str, list[str]]:
    """Classification keyword table (kept external in policy; changing
    categories requires no code changes)."""
    return load_policy().get("categories") or _FALLBACK_CATEGORIES


def get_package(package_id: str) -> PackagePolicy | None:
    """Fetch a pack's policy by id; any unregistered pack is treated as
    "unauthorized" (deny by default)."""
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
    """List all registered asset packs (exposed to MCP tools and the /tools
    endpoint)."""
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
    """Whether the asset source exists on this machine.

    The paths in tools/asset_policy.yaml are local and machine-specific, so a
    package reports exists=false until the operator fills in a real path.
    """
    return bool(path) and os.path.exists(path)


# ---------------------------------------------------------------- Scanning (read-only)

@dataclass
class ScanResult:
    """Scan result: describes only "what the pack contains"; performs no
    write operations whatsoever."""

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
    """Classify image paths by keywords. A file may hit multiple categories
    at once (art assets are inherently multi-semantic)."""
    out: dict[str, list[str]] = {}
    for label, kws in categories.items():
        hits = [n for n in names if any(k in n.lower() for k in kws)]
        if hits:
            out[label] = hits
    return out


def stratified_pick(names: list[str], limit: int) -> list[str]:
    """Stratified sampling: pick at even strides to avoid clustering of the
    same asset type (ported from pick() in script 03).

    Also dedupes by the first 12 characters of the file name so that _a/_b
    variants of the same asset do not fill the quota.
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
    """Read-only scan: total counts, category distribution, and a few sampled
    paths per category.

    This function implements the "low-risk read-only" capability: it writes
    no files and therefore needs no human approval.
    """
    pkg = get_package(package_id)
    if pkg is None:
        raise KeyError(f"Unregistered asset package: {package_id} (denied by default)")
    source = Path(pkg.path)

    if pkg.fmt == "team-zip":
        if not source.is_file():
            raise FileNotFoundError(f"Asset package not found: {source}")
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


# ---------------------------------------------------------------- Export (side effects)

def extract_assets(
    package_id: str,
    out_dir: str | Path,
    categories: list[str] | None = None,
    per_category: int = 3,
    size: int | None = None,
) -> dict[str, Any]:
    """Persist the sampled results to disk — the sole place in this module
    with write side effects.

    Callers must have already passed the three gates (permissions →
    authorization → approval); this function makes no policy decisions of its
    own, keeping "policy" and "execution" separate: policy stays testable,
    execution stays auditable.

    size: if given, proportionally scale down to that edge length (thumbnail
    mode, reducing disk usage).
    """
    from PIL import Image  # Optional dependency: imported only when actually exporting

    pkg = get_package(package_id)
    if pkg is None:
        raise KeyError(f"Unregistered asset package: {package_id} (denied by default)")

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
        """Write one image to disk at the relative path rel, preserving alpha
        (characters/icons must not be flattened onto a background color)."""
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
                except Exception as exc:  # a single failure must not break the batch, but must be surfaced
                    written.append(f"FAILED:{rel}:{exc}")
    else:
        for rel in picked:
            _save((source / rel).read_bytes(), rel)

    return {
        "package_id": package_id,
        "out_dir": str(out_root),
        "requested_categories": sorted(want) if want else "ALL",
        "written_count": len(written),
        "written": written[:50],  # return only the first 50 entries to keep MCP responses small
    }
