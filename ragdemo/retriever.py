"""BM25 retriever (v1, zero-dependency pure-Python implementation).

Why hand-written BM25 instead of vector retrieval:
- v1's goal is to get the "citation + refusal" skeleton working end to end; BM25 is good enough
  and requires no model downloads;
- The interface is designed to be swappable (Backend protocol), so v2's local embedding + FAISS
  requires no changes upstream;
- Bilingual tokenization: Latin text is split on words, CJK is split into single characters plus
  bigrams -- so the mixed Chinese/English governance corpus still matches.

Permission-aware retrieval (v4d)
--------------------------------
`search()` takes an optional `Principal`. When one is supplied, chunks the
principal may not read are removed **before ranking** — on this backend that
means inside the scoring loop, so a denied chunk never receives a score at all.
See `ragdemo/acl.py` for why the filter sits before the top-k cut.

`principal=None` means "no filtering". That is deliberate: the raw backend stays
usable for evaluation runs over the whole corpus. Every caller that serves an
end user resolves a principal first (see `ragdemo.tools_impl.impl_search_docs`).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Protocol

from . import acl
from .acl import Principal
from .chunker import Chunk

_LATIN_RE = re.compile(r"[a-zA-Z0-9]+")
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    """Bilingual tokenization: lowercased Latin words + CJK single characters and bigrams."""
    tokens = [t.lower() for t in _LATIN_RE.findall(text)]
    for run in _CJK_RUN_RE.findall(text):
        chars = list(run)
        tokens.extend(chars)
        tokens.extend(a + b for a, b in zip(chars, chars[1:]))
    return tokens


@dataclass
class Hit:
    """A single retrieval hit."""

    chunk: Chunk
    score: float


class Backend(Protocol):
    """Retrieval backend protocol (v2 will provide a FaissBackend implementation).

    `principal` is part of the protocol, not an afterthought bolted onto one
    implementation: a backend that cannot filter cannot claim to be a
    replacement for one that can.
    """

    def search(self, query: str, top_k: int = 5, principal: Principal | None = None) -> list[Hit]: ...


@dataclass
class Bm25Backend:
    """Okapi BM25 (k1=1.5, b=0.75) with an in-memory index built at startup."""

    chunks: list[Chunk]
    k1: float = 1.5
    b: float = 0.75
    # Fields below are built in __post_init__
    doc_tokens: list[list[str]] = field(default_factory=list, init=False)
    doc_lens: list[int] = field(default_factory=list, init=False)
    df: dict[str, int] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        for chunk in self.chunks:
            # Titles participate in tokenization: the title is the strongest topic signal in
            # the governance corpus
            tokens = tokenize(chunk.title + " " + chunk.text)
            self.doc_tokens.append(tokens)
            self.doc_lens.append(len(tokens))
        for tokens in self.doc_tokens:
            for term in set(tokens):
                self.df[term] = self.df.get(term, 0) + 1
        self.n_docs = len(self.chunks)
        self.avgdl = sum(self.doc_lens) / self.n_docs if self.n_docs else 0.0

    def _idf(self, term: str) -> float:
        """BM25 IDF (with protection for document frequency = 0)."""
        df = self.df.get(term, 0)
        if df == 0:
            return 0.0
        return math.log((self.n_docs - df + 0.5) / df + 1.0)

    def search(self, query: str, top_k: int = 5, principal: Principal | None = None) -> list[Hit]:
        """Return the top_k hits sorted by BM25 score in descending order.

        This is a genuine pre-filter: the visibility check sits at the top of
        the scoring loop, so a chunk the principal may not read is never
        scored, never ranked, and never truncated against a chunk they may.
        """
        q_tokens = tokenize(query)
        scores = [0.0] * self.n_docs
        visible = acl.visible_mask(self.chunks, principal)
        for i, tokens in enumerate(self.doc_tokens):
            if not tokens or not visible[i]:
                continue
            tf: dict[str, int] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1
            dl = self.doc_lens[i]
            for term in q_tokens:
                f = tf.get(term, 0)
                if f == 0:
                    continue
                idf = self._idf(term)
                if idf <= 0:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                scores[i] += idf * f * (self.k1 + 1) / denom
        ranked = sorted(
            ((s, i) for i, s in enumerate(scores)), key=lambda x: -x[0]
        )
        return [Hit(chunk=self.chunks[i], score=s) for s, i in ranked[:top_k] if s > 0]

    def coverage(self, query: str) -> float:
        """Coverage of the deduplicated query tokens in the corpus vocabulary -- the first
        gate of the refusal decision.

        Returns a value in 0-1: 1 means every query token appeared somewhere in the corpus.
        """
        q_tokens = set(tokenize(query))
        if not q_tokens:
            return 1.0
        hits = sum(1 for t in q_tokens if t in self.df)
        return hits / len(q_tokens)


def build_index(chunks: list[Chunk], backend: str | None = None) -> Backend:
    """Factory: picks the retrieval backend according to configuration, automatically falling
    back to BM25 when vector dependencies are missing.

    backend: bm25 (default, zero deps) | vector (FAISS) | hybrid (BM25 ⊕ vector, RRF fusion)
    """
    from .config import RETRIEVAL_BACKEND  # lazy import avoids a config/retriever circular dep

    backend = backend or RETRIEVAL_BACKEND
    if backend in ("vector", "hybrid"):
        try:
            from .vector import build_hybrid_backend, build_vector_backend
            return (
                build_hybrid_backend(chunks)
                if backend == "hybrid"
                else build_vector_backend(chunks)
            )
        except Exception as exc:  # noqa: BLE001 -- degrade when deps/model unavailable, keep serving
            import sys

            print(f"[retriever] vector backend unavailable ({exc}); falling back to BM25", file=sys.stderr)
    return Bm25Backend(chunks=chunks)
