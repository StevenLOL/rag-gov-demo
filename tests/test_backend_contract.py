"""Backend contract tests (v4a).

"Pluggable" is a claim about *behaviour*, not about class hierarchies. Any
backend `build_index` can return must honour the same contract, otherwise
plugging one in silently disables parts of the system:

- the search signature accepts `principal` (the permission filter is part of
  the protocol, not an optional extra -- see ragdemo/acl.py);
- results are ranked, capped, and reproducible;
- the refusal gate's `coverage()` exists and returns a number in [0, 1];
- an unknown backend name raises instead of quietly serving something else.

BM25 always runs. The dense and hybrid backends need a local embedding model,
so they skip (not fail) when the model is unavailable -- CI exercises the BM25
contract; a machine with the model cached runs all three.
"""

import pytest

from ragdemo import acl
from ragdemo.acl import Principal
from ragdemo.chunker import load_corpus
from ragdemo.config import CORPUS_DIR
from ragdemo.retriever import Bm25Backend, build_index


def _all_backends():
    """(name, factory) pairs. Dense backends are only offered when their
    dependencies import; the model itself may still be missing, in which case
    the fixture skips."""
    backends = [("bm25", lambda chunks: build_index(chunks, "bm25"))]
    try:
        import faiss  # noqa: F401
        import sentence_transformers  # noqa: F401
    except ImportError:
        return backends
    backends.append(("vector", lambda chunks: build_index(chunks, "vector")))
    backends.append(("hybrid", lambda chunks: build_index(chunks, "hybrid")))
    return backends


@pytest.fixture(scope="module", params=_all_backends(), ids=lambda p: p[0])
def built(request):
    """One backend per param, built once per module: the dense path pays a
    one-time model-load cost that must not be repeated per test."""
    chunks = load_corpus(CORPUS_DIR)
    try:
        return request.param[0], request.param[1](chunks), chunks
    except Exception as exc:  # noqa: BLE001 -- model load can fail in offline environments
        pytest.skip(f"backend unavailable: {exc}")


def test_search_accepts_the_principal_keyword(built):
    """The permission filter is part of the Backend protocol."""
    _, index, _ = built
    hits = index.search("数据分级", top_k=3, principal=acl.default_principal())
    assert isinstance(hits, list)


def test_results_are_capped_and_ranked(built):
    _, index, _ = built
    hits = index.search("数据分级 事故 审计", top_k=3)
    assert 0 < len(hits) <= 3
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True), "hits must come back best-first"


def test_repeated_calls_are_deterministic(built):
    _, index, _ = built
    first = [h.chunk.chunk_id for h in index.search("高风险动作 执行前 人工批准", top_k=5)]
    second = [h.chunk.chunk_id for h in index.search("高风险动作 执行前 人工批准", top_k=5)]
    assert first == second


def test_principal_filtering_hides_and_never_displaces(built):
    """The two-sided pre-filter guarantee.

    Hiding: a chunk the principal may not read is never returned.

    Never displacing: visible chunks keep the rank the unfiltered search gave
    them, so removing denied chunks *frees* slots for the next visible ones
    instead of shrinking the result. (This is exactly what post-filtering gets
    wrong, and why `filtered` is NOT a subset of `unfiltered`: when denied
    chunks occupied top-k slots, the freed slots are refilled by chunks the
    unfiltered window never showed.)
    """
    _, index, chunks = built
    staff = Principal(id="bob@example.com", groups=("all-staff",), clearance="internal")

    unfiltered = [h.chunk.chunk_id for h in index.search("事故 处理 上报", top_k=5)]
    filtered = [h.chunk.chunk_id for h in index.search("事故 处理 上报", top_k=5, principal=staff)]

    restricted = {c.chunk_id for c in chunks if not acl.chunk_visible(c, staff)}
    visible = {c.chunk_id for c in chunks if acl.chunk_visible(c, staff)}

    assert not (set(filtered) & restricted), "a denied chunk must never be returned"
    assert set(unfiltered) & visible, "guard: the query must reach visible material too"
    # No displacement: every visible chunk in the unfiltered window is still
    # there, in the same relative order.
    kept = [cid for cid in unfiltered if cid in visible]
    assert kept and kept == [cid for cid in filtered if cid in kept]


def test_coverage_gate_exists_on_every_backend(built):
    """citation.py's refusal decision calls coverage(); a backend without it
    breaks the refusal path at runtime."""
    _, index, _ = built
    value = index.coverage("完全无关的问题 量子纠缠")
    assert 0.0 <= value <= 1.0


def test_unknown_backend_name_raises_instead_of_serving_something_else():
    """A typo in RETRIEVAL_BACKEND must fail loudly: quietly returning a
    different retrieval stack than the operator asked for is a configuration
    bug that looks exactly like the intended one."""
    chunks = load_corpus(CORPUS_DIR)
    with pytest.raises(ValueError):
        build_index(chunks, "bm25-with-a-typo")


def test_default_backend_is_bm25_without_configuration():
    """Zero-dependency default: a fresh clone with no env vars must work."""
    assert isinstance(build_index(load_corpus(CORPUS_DIR)), Bm25Backend)
