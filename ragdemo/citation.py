"""Citation and refusal (v1 core: productizing "honesty").

Decision flow (two-gate safety net):
1. Coverage gate: if the query tokens' coverage in the corpus vocabulary < REFUSAL_COVERAGE → refuse;
2. Score gate: if the top-1 score is below the backend's own declared floor
   (`index.min_score` -- each backend declares the scale its scores live on:
   BM25 absolute score, vector cosine, hybrid RRF declares none) → refuse.
   An explicit `min_score` argument overrides the backend's declaration.
3. Both gates passed → generate/extract the answer and attach the citation list.

A refusal is not an error but a first-class response type: returns refused=True plus an
explanatory message.

Permission-aware retrieval (v4d): `answer_question` accepts a `Principal` and
hands it to the backend, so the filter runs before ranking. When nothing
survives the filter the refusal is worded exactly like "nothing matched" —
deliberately indistinguishable, so a caller cannot probe for the *existence* of
material they are not cleared to read.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .acl import Principal
from .chunker import Chunk
from .retriever import Bm25Backend, Hit


@dataclass
class Citation:
    """One citation: locates the original text within a corpus file."""

    ref: int          # Reference number, matching the [n] markers in the answer text
    source: str       # Source file name
    title: str        # Chunk title
    snippet: str      # Short excerpt


@dataclass
class Answer:
    """Unified response model for the /ask endpoint (v3 will add the approval field)."""

    question: str
    refused: bool
    refusal_reason: str = ""
    answer: str = ""
    citations: list[Citation] = field(default_factory=list)
    mode: str = "extractive"   # extractive | llm (decided by llm.py in v2)


def _build_citations(hits: list[Hit]) -> list[Citation]:
    return [
        Citation(ref=i + 1, source=h.chunk.source, title=h.chunk.title, snippet=h.chunk.snippet)
        for i, h in enumerate(hits)
    ]


def _extractive_answer(hits: list[Hit]) -> str:
    """Extractive answer without an LLM: returns the top hits' source text + citation markers
    (always works)."""
    parts = ["According to the corpus:"]
    for i, hit in enumerate(hits[:2], start=1):
        parts.append(f"[{i}] \"{hit.chunk.title}\": {hit.chunk.text.strip()[:300]}")
    return "\n\n".join(parts)


def answer_question(
    question: str,
    index: Bm25Backend,
    generate=None,
    refusal_coverage: float = 0.5,
    min_score: float | None = None,
    principal: Principal | None = None,
) -> Answer:
    """Main Q&A entry point.

    generate:  optional (question, context_chunks) -> str generation function (provided by
               llm.py). When None or when the call fails, falls back to the extractive path
               -- the demo never becomes unavailable just because a model is missing.
    min_score: optional explicit override of the score-gate floor. When None
               (the default), the backend's own declared floor (`index.min_score`)
               is used -- a BM25 score and a cosine similarity live on different
               scales, and one hardcoded number cannot serve both.
    principal: who is asking. Passed straight to the backend, which filters before
               ranking; None means "no filtering" (whole corpus visible).
    """
    hits = index.search(question, top_k=3, principal=principal)

    # Gate 0: nothing survived retrieval. On the permission-aware path this is
    # where a fully-filtered query lands, and it must be indistinguishable from
    # "the corpus simply has nothing on this" -- see the module docstring.
    if not hits:
        return Answer(
            question=question,
            refused=True,
            refusal_reason=(
                "No passage in the authorised set matches this question; "
                "refusing to fabricate."
            ),
        )

    # Gate 1: coverage
    coverage = index.coverage(question)
    if coverage < refusal_coverage:
        return Answer(
            question=question,
            refused=True,
            refusal_reason=(
                f"Query token coverage in the corpus is {coverage:.0%}, below the "
                f"{refusal_coverage:.0%} threshold; no grounding in the corpus, "
                "refusing to fabricate."
            ),
        )

    # Gate 2: retrieval score, on the backend's own scale. The threshold is a
    # property of the backend, not of this function: a hardcoded BM25 floor
    # (2.0) applied to a cosine-scale backend (scores <= 1.0) refused every
    # answer, which is exactly the bug this parameterization fixes.
    threshold = min_score if min_score is not None else getattr(index, "min_score", 0.0)
    top_score = hits[0].score
    if top_score < threshold:
        return Answer(
            question=question,
            refused=True,
            refusal_reason=(
                f"Top passage score {top_score:.4g} is below the {threshold:.4g} "
                "threshold; insufficient grounding in the corpus, refusing to fabricate."
            ),
        )

    # Both gates passed → generate or extract
    mode = "extractive"
    answer_text = ""
    if generate is not None:
        try:
            answer_text = generate(question, [h.chunk for h in hits])
            mode = "llm"
        except Exception as exc:  # noqa: BLE001 -- degradation is designed behavior, not error swallowing
            answer_text = ""
            # Record the degradation reason in the audit log for troubleshooting; comment anchor
            # kept here (persist to the database in v2 once Postgres is wired in)
            _ = exc
    if not answer_text:
        answer_text = _extractive_answer(hits)

    return Answer(
        question=question,
        refused=False,
        answer=answer_text,
        citations=_build_citations(hits),
        mode=mode,
    )
