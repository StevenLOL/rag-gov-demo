"""Permission-aware retrieval: which chunks a caller is allowed to see (v4d).

The three gates in `agents/graph.py` govern **agent actions** — may this tool
call run at all, who approves it, where is the audit trail. They say nothing
about **what the retriever is allowed to return**. This module closes that gap:

    every chunk carries an ACL inherited from its source document, retrieval
    takes a `Principal`, and candidates are filtered BEFORE ranking.

Why pre-filter and not post-filter
----------------------------------
Post-filtering — take top-k, then drop what the caller may not see — breaks
recall in a way that is easy to miss: denied chunks consume slots inside the
top-k, so an authorised document that ranked k+1 is silently lost. Worse, the
unauthorised text has already been assembled into the model's context and into
whatever the audit log records.

Pre-filtering narrows the candidate set first and only then ranks what
survived. A denied chunk therefore never displaces an authorised one and never
reaches the model.

The filter is applied **before truncation** in every backend:

- BM25 — the check sits inside the scoring loop, so a denied chunk never even
  receives a score.
- dense (FAISS) — the index is exact (`IndexFlatIP`, brute force), so widening
  the fetch to every vector costs the same single GEMM as fetching top-k. The
  filter then runs before the top-k cut, which is where the recall damage of
  post-filtering actually happens.

What this module deliberately does NOT do
-----------------------------------------
- **It does not authenticate anybody.** A `Principal` is *declared* by the
  caller; binding it to a real identity provider is out of scope for this demo.
  What is demonstrated here is the enforcement shape, not the plumbing.
- **It is not a substitute for storage-level row security.** A retrieval filter
  in application code is one layer; see `docs/RAI.md` for the current boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable, Sequence

if TYPE_CHECKING:  # typing-only: keeps acl.py importable without the rest of the stack
    from .chunker import Chunk
    from .retriever import Hit

# Ordered from least to most sensitive; a principal's clearance is a ceiling on
# this scale, not a grant.
SENSITIVITY_LEVELS: tuple[str, ...] = ("public", "internal", "confidential", "restricted")
_RANK: dict[str, int] = {name: i for i, name in enumerate(SENSITIVITY_LEVELS)}

# Wildcard allow-token: a chunk carrying it is readable by any principal whose
# clearance covers its sensitivity.
ANY_PRINCIPAL = "*"


def sensitivity_rank(name: str) -> int:
    """Rank of a sensitivity label (higher = more sensitive).

    Raises on an unknown label: an ACL typo must fail loudly at ingestion
    rather than silently degrade into "everyone may read this".
    """
    key = str(name).strip().lower()
    if key not in _RANK:
        raise ValueError(f"unknown sensitivity {name!r}; expected one of {list(SENSITIVITY_LEVELS)}")
    return _RANK[key]


@dataclass(frozen=True)
class Principal:
    """Who is asking. Declared by the caller; this demo does not verify it."""

    id: str = "anonymous"
    groups: tuple[str, ...] = ()
    clearance: str = "internal"   # ceiling on SENSITIVITY_LEVELS

    def __post_init__(self) -> None:
        sensitivity_rank(self.clearance)  # fail loudly on a bad clearance label

    @property
    def tokens(self) -> frozenset[str]:
        """Everything this principal can be matched against in an allow-list."""
        return frozenset({f"user:{self.id}", *(f"group:{g}" for g in self.groups)})

    @property
    def ceiling(self) -> int:
        return sensitivity_rank(self.clearance)

    def to_dict(self) -> dict[str, Any]:
        """Audit-safe projection (a dict, so JSONL stays flat and greppable)."""
        return {"id": self.id, "groups": list(self.groups), "clearance": self.clearance}


def principal_from_dict(raw: Any) -> "Principal | None":
    """Build a Principal from a request payload.

    Returns None when `raw` is None — the caller decides what "no principal"
    means for its own path (the retrieval entry points substitute the
    configured default; the pure backends treat it as "do not filter").
    """
    if raw is None:
        return None
    if isinstance(raw, Principal):
        return raw
    if not isinstance(raw, dict):
        raise TypeError(f"principal must be a dict or Principal, got {type(raw).__name__}")
    groups = raw.get("groups") or ()
    if isinstance(groups, str):
        groups = (groups,)
    return Principal(
        id=str(raw.get("id", "anonymous")),
        groups=tuple(str(g) for g in groups),
        clearance=str(raw.get("clearance", "internal")),
    )


def default_principal() -> Principal:
    """The principal used when a request declares none (see config.py for the
    environment overrides).

    Default is the least-privileged identity that still exercises the filter:
    a member of no special group, cleared for internal material only.
    """
    from .config import PRINCIPAL_CLEARANCE, PRINCIPAL_GROUPS, PRINCIPAL_ID

    return Principal(id=PRINCIPAL_ID, groups=PRINCIPAL_GROUPS, clearance=PRINCIPAL_CLEARANCE)


def allows(allow: Iterable[str], sensitivity: str, principal: Principal) -> bool:
    """The access decision, in one place.

    Two independent conditions, both required:

    1. **membership** — the principal appears in the allow-list (or the list
       carries the `*` wildcard);
    2. **clearance** — the chunk's sensitivity sits at or below the principal's
       ceiling.

    An **empty allow-list denies everybody**. That is the whole point of
    "deny by default": a document that was never classified is not a document
    that everybody may read.
    """
    tokens = {str(t) for t in allow or ()}
    if not tokens:
        return False
    if ANY_PRINCIPAL not in tokens and not (tokens & principal.tokens):
        return False
    return sensitivity_rank(sensitivity) <= principal.ceiling


def chunk_visible(chunk: "Chunk", principal: Principal) -> bool:
    """Whether one chunk may enter this principal's candidate set."""
    return allows(chunk.acl, chunk.sensitivity, principal)


def visible_mask(chunks: Sequence["Chunk"], principal: Principal | None) -> list[bool]:
    """Per-chunk visibility flags; `principal=None` marks everything visible.

    Computing this once per query keeps the BM25 scoring loop free of
    per-chunk set algebra.
    """
    if principal is None:
        return [True] * len(chunks)
    return [chunk_visible(chunk, principal) for chunk in chunks]


def filter_hits(hits: list["Hit"], principal: Principal | None) -> list["Hit"]:
    """Drop hits the principal may not see.

    Used by the dense path, where the index has already produced scores; it is
    still applied **before** the top-k cut (see the module docstring).
    """
    if principal is None:
        return list(hits)
    return [hit for hit in hits if chunk_visible(hit.chunk, principal)]


def partition(chunks: Sequence["Chunk"], principal: Principal | None) -> tuple[list["Chunk"], list["Chunk"]]:
    """Split a corpus into (visible, hidden) for one principal.

    The hidden list exists so callers can log **how many** chunks the filter
    removed. It must never be logged by content: identifiers, titles or
    snippets of denied chunks would turn the audit stream into a second, less
    protected copy of the restricted corpus.
    """
    if principal is None:
        return list(chunks), []
    visible: list["Chunk"] = []
    hidden: list["Chunk"] = []
    for chunk in chunks:
        (visible if chunk_visible(chunk, principal) else hidden).append(chunk)
    return visible, hidden
