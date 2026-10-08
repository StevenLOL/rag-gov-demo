"""Markdown corpus chunker (v1).

Strategy: split on Markdown headings (# / ## / ###); the heading line becomes the chunk's title
metadata -- the smallest unit of citation traceability is the chunk (source file + title + text).

Permission metadata (v4d): a document declares its own access list in a YAML
front-matter block, and **every chunk cut from it inherits it**. Permissions
therefore live with the content, not in a separate table that can drift away
from it. See `ragdemo/acl.py` for how the decision is made.

What we deliberately do not do (honest boundaries):
- No semantic chunking (may be introduced in v2 depending on results);
- No vectorization at this layer (the retriever owns indexing).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import acl as _acl

# Front matter: a YAML block fenced by `---` on the very first line. Optional --
# a document without one inherits the corpus-wide defaults.
_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)


@dataclass
class Chunk:
    """The minimal retrieval unit: a piece of source text with provenance."""

    chunk_id: str      # Globally unique: {source}#{index}
    source: str        # Source file name (for citation display)
    title: str         # Containing heading (for citation display)
    text: str          # Original body text
    # Access control (v4d), inherited from the source document at ingestion:
    acl: tuple[str, ...] = field(default_factory=tuple)  # allow-tokens: "group:sre", "user:a@b", "*"
    sensitivity: str = "internal"                        # public | internal | confidential | restricted

    @property
    def snippet(self) -> str:
        """Short excerpt for citation cards (120 characters)."""
        text = re.sub(r"\s+", " ", self.text).strip()
        return text[:120] + ("…" if len(text) > 120 else "")


_HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)$")


def chunk_markdown(
    text: str,
    source: str,
    acl: tuple[str, ...] | list[str] | str = (),
    sensitivity: str = "internal",
) -> list[Chunk]:
    """Split a Markdown document into a list of Chunks by heading.

    Rules:
    - Each heading starts a new chunk, with title = the heading text;
    - Untitled loose text at the beginning of the file goes into a chunk with title="(intro)";
    - Whitespace-only chunks are discarded.

    acl / sensitivity: the document's declaration, copied verbatim onto every
    chunk. Inheritance is unconditional -- there is no per-chunk override, so a
    chunk cannot accidentally end up more readable than the document it came
    from.
    """
    allow = _as_tokens(acl)
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
                    acl=allow,
                    sensitivity=sensitivity,
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


def _as_tokens(value: Any) -> tuple[str, ...]:
    """Normalize an allow-list declaration into a tuple of tokens.

    Accepts a single string, a list, or a comma-separated string (the shape an
    environment variable arrives in) so the same parser serves the corpus
    front matter and the configured defaults.
    """
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(t.strip() for t in value.split(",") if t.strip())
    return tuple(str(t).strip() for t in value if str(t).strip())


def split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """Peel an optional YAML front-matter block off the top of a document.

    Returns (declaration, body). The body is what gets chunked, so the
    declaration never leaks into retrieved text or into an embedding.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    import yaml  # local dep; only needed for documents that actually declare an ACL

    parsed = yaml.safe_load(match.group(1)) or {}
    if not isinstance(parsed, dict):
        raise ValueError(f"corpus front matter must be a YAML mapping, got {type(parsed).__name__}")
    return parsed, text[match.end() :]


def parse_acl(
    declaration: dict[str, Any],
    default_acl: tuple[str, ...] = (),
    default_sensitivity: str = "internal",
) -> tuple[tuple[str, ...], str]:
    """Read `acl` / `sensitivity` out of a front-matter mapping.

    Missing keys fall back to the corpus-wide defaults, so a partially
    classified document still gets a complete, explicit ACL. `sensitivity` is
    validated here: an unrecognised label raises at ingestion rather than
    silently meaning "less sensitive".
    """
    allow = _as_tokens(declaration.get("acl")) or default_acl
    sensitivity = str(declaration.get("sensitivity", default_sensitivity)).strip().lower()
    _acl.sensitivity_rank(sensitivity)  # raises on a typo
    return allow, sensitivity


def load_corpus(
    corpus_dir: Path,
    default_acl: Any = None,
    default_sensitivity: str | None = None,
) -> list[Chunk]:
    """Load and chunk all .md corpus files in a directory (sorted by file name for determinism).

    Each document may declare `acl` / `sensitivity` in a front-matter block; a
    document that declares nothing inherits `default_acl` /
    `default_sensitivity` (see config.CORPUS_DEFAULT_*), which is why the
    default is explicit configuration rather than an implicit "everybody".
    """
    from .config import CORPUS_DEFAULT_ACL, CORPUS_DEFAULT_SENSITIVITY

    allow_default = _as_tokens(default_acl if default_acl is not None else CORPUS_DEFAULT_ACL)
    sensitivity_default = (
        default_sensitivity or CORPUS_DEFAULT_SENSITIVITY
    )

    chunks: list[Chunk] = []
    for path in sorted(corpus_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        declaration, body = split_front_matter(text)
        allow, sensitivity = parse_acl(declaration, allow_default, sensitivity_default)
        chunks.extend(chunk_markdown(body, path.name, acl=allow, sensitivity=sensitivity))
    return chunks
