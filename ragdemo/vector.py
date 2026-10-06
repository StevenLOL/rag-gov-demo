"""Vector retrieval backend (v2).

Design points:
- Vector store: **FAISS IndexFlatIP** (local in-memory index; data never
  leaves the domain);
- Similarity: embeddings are built with `normalize_embeddings=True` -> unit
  vectors -> **inner product = cosine** (a mathematical identity), so the
  fastest GEMM kernel can be used directly and scores naturally fall in
  [-1, 1];
- Embedding model: local sentence-transformers model (default
  intfloat/multilingual-e5-small, 384 dims, supports both Chinese and English,
  ~470MB; the lightweight first choice for mixed Chinese/English corpora);
- Model download: if the default Hugging Face endpoint is slow or unreachable,
  point `HF_ENDPOINT` at a mirror first;
- Hybrid retrieval: BM25 (sparse) + vector (dense) dual recall with RRF
  fusion (k=60); the refusal coverage gate still uses BM25 token coverage
  (no gate on the semantic side, to avoid false refusals).

Dependencies are optional: when sentence-transformers/faiss are not
installed, the upper layer automatically falls back to BM25 (see
retriever.build_index).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

# numpy is only actually used on the vector path; TYPE_CHECKING keeps
# `import ragdemo.vector` from forcing a numpy dependency
if TYPE_CHECKING:
    import numpy as np

from .chunker import Chunk
from .retriever import Backend, Bm25Backend, Hit


class Embedder(Protocol):
    """Embedder protocol (easy to swap in Ollama bge-m3 or cloud A/B experiments)."""

    def encode_passages(self, texts: list[str]) -> "np.ndarray": ...
    def encode_query(self, query: str) -> "np.ndarray": ...


@dataclass
class SentenceTransformerEmbedder:
    """Local sentence-transformers embedder (lazy model load; downloads/loads on first use)."""

    model_name: str = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
    device: str = os.getenv("EMBEDDING_DEVICE", "cpu")
    batch_size: int = 16
    _model: object = field(default=None, init=False, repr=False)

    def _load(self) -> object:
        """Load the model: prefer the local cache (offline-friendly, instant
        startup); only download over the network when the cache is missing."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # local dep, lazy import
            try:
                self._model = SentenceTransformer(
                    self.model_name, device=self.device, local_files_only=True
                )
            except Exception:  # noqa: BLE001 -- cache missing -> normal download path
                # If the default HF endpoint is slow or unreachable, set
                # HF_ENDPOINT to a mirror first
                self._model = SentenceTransformer(self.model_name, device=self.device)
        return self._model

    @property
    def _is_e5(self) -> bool:
        """e5-family models require query/passage prefixes, otherwise recall drops notably."""
        return "e5" in self.model_name.lower()

    @property
    def _bge_zh_instruction(self) -> str:
        """bge-zh-family models need a retrieval instruction prefix on the query side
        (not on the document side)."""
        name = self.model_name.lower()
        return "为这个句子生成表示以用于检索相关文章：" if ("bge" in name and "zh" in name) else ""

    def encode_passages(self, texts: list[str]) -> "np.ndarray":
        """Document-side encoding: adds the passage prefix (e5) and returns a normalized
        float32 matrix."""
        import numpy as np

        model = self._load()
        inputs = [f"passage: {t}" if self._is_e5 else t for t in texts]
        vectors = model.encode(
            inputs, normalize_embeddings=True, batch_size=self.batch_size
        )
        return np.asarray(vectors, dtype="float32")

    def encode_query(self, query: str) -> "np.ndarray":
        """Query-side encoding: e5 gets a query prefix, bge-zh gets an instruction
        prefix; shape is (1, dim)."""
        import numpy as np

        model = self._load()
        if self._is_e5:
            text = f"query: {query}"
        elif self._bge_zh_instruction:
            text = self._bge_zh_instruction + query
        else:
            text = query
        vector = model.encode([text], normalize_embeddings=True)
        return np.asarray(vector, dtype="float32")


@dataclass
class FaissBackend:
    """FAISS inner-product index (equivalent to cosine similarity after normalization)."""

    chunks: list[Chunk]
    embedder: Embedder
    _index: object = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        import faiss  # local dep, lazy import

        vectors = self.embedder.encode_passages(
            [f"{c.title}\n{c.text}" for c in self.chunks]
        )
        # Inner-product index: vectors are already normalized -> retrieval scores
        # are cosine similarities
        self._index = faiss.IndexFlatIP(vectors.shape[1])
        self._index.add(vectors)

    def search(self, query: str, top_k: int = 5) -> list[Hit]:
        scores, ids = self._index.search(self.embedder.encode_query(query), top_k)
        return [
            Hit(chunk=self.chunks[i], score=float(s))
            for s, i in zip(scores[0], ids[0])
            if i >= 0 and s > 0
        ]

    def coverage(self, query: str) -> float:
        """No token-coverage gate for semantic retrieval — refusal is instead decided
        by a cosine threshold (see citation.answer_question)."""
        return 1.0


@dataclass
class HybridBackend:
    """Hybrid retrieval: BM25 (sparse) + vector (dense), fused with RRF.

    RRF (Reciprocal Rank Fusion): score = Σ 1/(k + rank), k=60.
    Advantage: the two channels have different score scales (BM25 magnitudes
    vary, cosine is in [-1, 1]); rank-based fusion needs no score
    normalization — robust and parameter-free.
    """

    bm25: Backend
    vector: Backend
    rrf_k: int = 60

    def search(self, query: str, top_k: int = 5) -> list[Hit]:
        candidates: dict[str, float] = {}
        found: dict[str, Hit] = {}
        for backend in (self.bm25, self.vector):
            try:
                hits = backend.search(query, top_k=top_k * 2)
            except Exception:  # noqa: BLE001 -- one channel failing must not drag down
                # the whole result (degrade to the other channel)
                continue
            for rank, hit in enumerate(hits, start=1):
                key = hit.chunk.chunk_id
                candidates[key] = candidates.get(key, 0.0) + 1.0 / (self.rrf_k + rank)
                found[key] = hit.chunk
        ordered = sorted(candidates.items(), key=lambda kv: -kv[1])[:top_k]
        return [Hit(chunk=found[key], score=score) for key, score in ordered]

    def coverage(self, query: str) -> float:
        """The coverage gate reuses BM25 token coverage — no gate on the semantic side,
        avoiding false refusals on synonymous paraphrases."""
        return getattr(self.bm25, "coverage", lambda _q: 1.0)(query)


def build_vector_backend(chunks: list[Chunk]) -> Backend:
    """Factory: vector backend (raises when dependencies are missing; retriever.build_index
    falls back to BM25)."""
    return FaissBackend(chunks=chunks, embedder=SentenceTransformerEmbedder())


def build_hybrid_backend(chunks: list[Chunk]) -> Backend:
    """Factory: BM25 + vector hybrid backend."""
    return HybridBackend(bm25=Bm25Backend(chunks=chunks), vector=build_vector_backend(chunks))
