"""审计日志（v1 形态：本地 JSONL；v3 迁移 Postgres 审计表）。

设计意图：
- v1 就把"每一步留痕"立起来：每次问答（含拒答）都落一行 JSON；
- v3 的事件类型将扩展为 approval_granted / approval_rejected / unauthorized_blocked，
  表结构见 docs/GOVERNANCE.md 的 Manage 函数映射；
- MDDI 公共部门规则的工程化锚点："使用 AI 自负其责"→ 先要能查到"AI 当时答了什么"。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .config import AUDIT_LOG


def append_event(event_type: str, payload: dict, log_path: Path | None = None) -> None:
    """追加一条审计事件（JSONL，一行一事件）。

    event_type: ask / refused（v1）；v3 扩展审批类事件。
    """
    path = log_path or AUDIT_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "type": event_type,
        **payload,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_events(log_path: Path | None = None) -> list[dict]:
    """读取全部审计事件（/audit 端点与未来治理报表共用）。"""
    path = log_path or AUDIT_LOG
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
