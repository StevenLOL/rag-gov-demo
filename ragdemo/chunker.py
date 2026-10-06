"""Markdown corpus chunker (v1).

Strategy: split on Markdown headings (# / ## / ###); the heading line becomes the chunk's title
metadata -- the smallest unit of citation traceability is the chunk (source file + title + text).

What we deliberately do not do (honest boundaries):
- No semantic chunking (may be introduced in v2 depending on results);
- No vectorization at this layer (the retriever owns indexing).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Chunk:
    """The minimal retrieval unit: a piece of source text with provenance."""

    chunk_id: str      # Globally unique: {source}#{index}
    source: str        # Source file name (for citation display)
    title: str         # Containing heading (for citation display)
    text: str          # Original body text

    @property
    def snippet(self) -> str:
        """Short excerpt for citation cards (120 characters)."""
        text = re.sub(r"\s+", " ", self.text).strip()
        return text[:120] + ("…" if len(text) > 120 else "")


_HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)$")


def chunk_markdown(text: str, source: str) -> list[Chunk]:
    """Split a Markdown document into a list of Chunks by heading.

    Rules:
    - Each heading starts a new chunk, with title = the heading text;
    - Untitled loose text at the beginning of the file goes into a chunk with title="(intro)";
    - Whitespace-only chunks are discarded.
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
    """Load and chunk all .md corpus files in a directory (sorted by file name for determinism)."""
    chunks: list[Chunk] = []
    for path in sorted(corpus_dir.glob("*.md")):
        chunks.extend(chunk_markdown(path.read_text(encoding="utf-8"), path.name))
    return chunks
