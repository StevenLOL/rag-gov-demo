"""Vector/hybrid retrieval tests (v2).

Two categories:
1. Pure-Python tests (RRF fusion, factory fallback) — always run, no model dependency;
2. Tests that need a local embedding model (FAISS end-to-end) — automatically skipped
   when dependencies are missing or the model download fails.
"""

import pytest

from ragdemo.chunker import Chunk, load_corpus
from ragdemo.config import CORPUS_DIR
from ragdemo.retriever import Bm25Backend, Hit, build_index


class _FakeBackend:
    """Controllable fake backend: returns hits in the given order (used to verify that
    RRF looks at ranks only, not scores)."""

    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks

    def search(self, query: str, top_k: int = 5) -> list[Hit]:
        # Deliberately absurd score scale — verifies RRF is immune to score scale
        return [
            Hit(chunk=c, score=1000.0 - i) for i, c in enumerate(self.chunks[:top_k])
        ]

    def coverage(self, query: str) -> float:
        return 1.0


def _chunks() -> list[Chunk]:
    return [
        Chunk(chunk_id="a#0", source="a.md", title="甲", text="审批流程"),
        Chunk(chunk_id="b#0", source="b.md", title="乙", text="最小权限"),
        Chunk(chunk_id="c#0", source="c.md", title="丙", text="数据分级"),
    ]


def test_rrf_fusion_by_rank():
    """RRF fuses by rank: a chunk ranked first in both paths must come first; chunks
    unique to a single path still enter the results."""
    from ragdemo.vector import HybridBackend

    chunks = _chunks()
    # Path 1: A, B, C; path 2: B, C, A
    # -> B = 1/62 + 1/61 highest, A = 1/61 + 1/63 next, C = 1/63 + 1/62 lowest
    # Note: if the two paths rank symmetrically (e.g. A1 B2 vs B1 A2), RRF produces
    # ties — that is a property of RRF, not a bug
    backend = HybridBackend(
        bm25=_FakeBackend(chunks), vector=_FakeBackend([chunks[1], chunks[2], chunks[0]])
    )
    hits = backend.search("任意问题", top_k=3)
    assert [h.chunk.chunk_id for h in hits] == ["b#0", "a#0", "c#0"]
    # RRF scores should be far below the exaggerated input scores (proof it ranks by rank)
    assert all(0 < h.score < 1 for h in hits)


def test_rrf_score_formula():
    """RRF formula check: with k=60, first place on both paths -> 2/(60+1)."""
    from ragdemo.vector import HybridBackend

    chunks = _chunks()[:1]
    backend = HybridBackend(bm25=_FakeBackend(chunks), vector=_FakeBackend(chunks))
    hits = backend.search("x", top_k=1)
    assert hits[0].score == pytest.approx(2 / 61)


def test_hybrid_coverage_uses_bm25():
    """The coverage gate reuses BM25 token coverage (no gate on the semantic side,
    to avoid false rejections of paraphrased queries)."""
    from ragdemo.vector import HybridBackend

    chunks = load_corpus(CORPUS_DIR)
    bm25 = Bm25Backend(chunks=chunks)
    backend = HybridBackend(bm25=bm25, vector=_FakeBackend(chunks))
    assert backend.coverage("量子纠缠股票价格走势") < 0.5


def test_build_index_default_is_bm25():
    """Zero-dependency default: must work even without the vector dependencies installed."""
    index = build_index(load_corpus(CORPUS_DIR))
    assert isinstance(index, Bm25Backend)


def test_vector_backend_end_to_end():
    """FAISS end-to-end (requires a local embedding model; skipped when unavailable, not a failure)."""
    st = pytest.importorskip("sentence_transformers", reason="sentence-transformers not installed")
    pytest.importorskip("faiss", reason="faiss-cpu not installed")

    from ragdemo.vector import build_vector_backend

    chunks = load_corpus(CORPUS_DIR)
    try:
        index = build_vector_backend(chunks)
    except Exception as exc:  # noqa: BLE001 — skip when the model download fails (network-restricted environments)
        pytest.skip(f"embedding model unavailable: {exc}")

    hits = index.search("高风险动作执行前需要人工批准吗", top_k=3)
    assert hits, "semantic retrieval should hit the governance corpus"
    # Normalized inner product = cosine; scores must fall within [-1, 1]
    assert all(-1.0 <= h.score <= 1.0 for h in hits)
    assert hits[0].chunk.source == "agent_governance_basics.md"
