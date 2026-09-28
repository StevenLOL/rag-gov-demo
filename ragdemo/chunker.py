"""Markdown 语料分块器（v1）。

策略：按 Markdown 标题（# / ## / ###）切块，标题行作为 chunk 的 title 元数据——
引用溯源的最小单位就是 chunk（来源文件 + 标题 + 原文）。

不做的事（诚实边界）：
- 不做语义切块（v2 视效果引入）；
- 不在此层做向量化（retriever 负责索引）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Chunk:
    """最小检索单元：一段带出处的原文。"""

    chunk_id: str      # 全局唯一：{source}#{序号}
    source: str        # 来源文件名（引用展示用）
    title: str         # 所在标题（引用展示用）
    text: str          # 原文正文

    @property
    def snippet(self) -> str:
        """引用卡片用的短摘录（120 字符）。"""
        text = re.sub(r"\s+", " ", self.text).strip()
        return text[:120] + ("…" if len(text) > 120 else "")


_HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)$")


def chunk_markdown(text: str, source: str) -> list[Chunk]:
    """把一份 Markdown 文本按标题切分为 Chunk 列表。

    规则：
    - 每个标题开启一个新 chunk，title = 标题文字；
    - 文件开头无标题的散文本归入 title="(intro)"；
    - 纯空白 chunk 丢弃。
    """
    chunks: list[Chunk] = []
    current_title = "(intro)"
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if body:
            chunks.append(
                Chunk(
                    chunk_id=f"{source}#{len(chunks)}",
                    source=source,
                    title=current_title,
                    text=body,
                )
            )

    for line in text.splitlines():
        match = _HEADING_RE.match(line.strip())
        if match:
            flush()
            buffer = []
            current_title = match.group(2).strip()
        else:
            buffer.append(line)
    flush()
    return chunks


def load_corpus(corpus_dir: Path) -> list[Chunk]:
    """加载目录下全部 .md 语料并分块（按文件名排序保证确定性）。"""
    chunks: list[Chunk] = []
    for path in sorted(corpus_dir.glob("*.md")):
        chunks.extend(chunk_markdown(path.read_text(encoding="utf-8"), path.name))
    return chunks
