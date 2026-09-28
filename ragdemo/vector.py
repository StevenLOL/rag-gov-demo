"""向量检索后端（v2）。

设计要点（承接 docs/067 §3 与 docs/068 复用判定）：
- 向量库：**FAISS IndexFlatIP**（本地内存索引，数据不出域）；
- 相似度：嵌入时 `normalize_embeddings=True` → 单位向量 → **内积 = 余弦**（数学恒等），
  因此可以直接用最快的 GEMM 内核，且分数天然落在 [-1, 1]；
- 嵌入模型：本地 sentence-transformers 模型（默认 intfloat/multilingual-e5-small，384 维，
  中文/英文都支持，体积 ~470MB；中英混排语料的首选轻量款）；
- 模型下载：国内网络建议 `export HF_ENDPOINT=https://hf-mirror.com`；
- 混合检索：BM25（稀疏）+ 向量（稠密）两路召回，RRF 融合（k=60），
  拒答的覆盖率闸仍沿用 BM25 的词元覆盖（语义侧不设闸，避免误拒）。

依赖是可选的：未安装 sentence-transformers/faiss 时上层自动回退 BM25（见 retriever.build_index）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

# numpy 只在向量路径真正用到；用 TYPE_CHECKING 保持 import ragdemo.vector 不强制依赖 numpy
if TYPE_CHECKING:
    import numpy as np

from .chunker import Chunk
from .retriever import Backend, Bm25Backend, Hit


class Embedder(Protocol):
    """嵌入器协议（便于替换为 Ollama bge-m3 或云端对照实验）。"""

    def encode_passages(self, texts: list[str]) -> "np.ndarray": ...
    def encode_query(self, query: str) -> "np.ndarray": ...


@dataclass
class SentenceTransformerEmbedder:
    """本地 sentence-transformers 嵌入器（懒加载模型，首次使用才下载/载入）。"""

    model_name: str = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
    device: str = os.getenv("EMBEDDING_DEVICE", "cpu")
    batch_size: int = 16
    _model: object = field(default=None, init=False, repr=False)

    def _load(self) -> object:
        """加载模型：优先用本地缓存（离线友好、秒开），缓存缺失时才联网下载。"""
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # 本地依赖，延迟导入
            try:
                self._model = SentenceTransformer(
                    self.model_name, device=self.device, local_files_only=True
                )
            except Exception:  # noqa: BLE001 —— 缓存缺失 → 走正常下载路径
                # 国内网络建议先 export HF_ENDPOINT=https://hf-mirror.com
                self._model = SentenceTransformer(self.model_name, device=self.device)
        return self._model

    @property
    def _is_e5(self) -> bool:
        """e5 系列要求 query/passage 前缀，否则召回率明显下降。"""
        return "e5" in self.model_name.lower()

    @property
    def _bge_zh_instruction(self) -> str:
        """bge-zh 系列查询侧需要检索指令前缀（文档侧不加）。"""
        name = self.model_name.lower()
        return "为这个句子生成表示以用于检索相关文章：" if ("bge" in name and "zh" in name) else ""

    def encode_passages(self, texts: list[str]) -> "np.ndarray":
        """文档侧编码：加 passage 前缀（e5），归一化后返回 float32 矩阵。"""
        import numpy as np

        model = self._load()
        inputs = [f"passage: {t}" if self._is_e5 else t for t in texts]
        vectors = model.encode(
            inputs, normalize_embeddings=True, batch_size=self.batch_size
        )
        return np.asarray(vectors, dtype="float32")

    def encode_query(self, query: str) -> "np.ndarray":
        """查询侧编码：e5 加 query 前缀、bge-zh 加指令前缀，形状 (1, dim)。"""
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
    """FAISS 内积索引（归一化后等价于余弦相似度）。"""

    chunks: list[Chunk]
    embedder: Embedder
    _index: object = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        import faiss  # 本地依赖，延迟导入

        vectors = self.embedder.encode_passages(
            [f"{c.title}\n{c.text}" for c in self.chunks]
        )
        # 内积索引：向量已归一化 → 检索分数就是余弦相似度
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
        """语义检索不做词元覆盖闸——拒答改由余弦阈值判定（见 citation.answer_question）。"""
        return 1.0


@dataclass
class HybridBackend:
    """混合检索：BM25（稀疏）+ 向量（稠密），RRF 融合。

    RRF（Reciprocal Rank Fusion）：score = Σ 1/(k + rank)，k=60。
    优点：两路分数尺度不同（BM25 分数量级不定、余弦在 [-1,1]），
    用排名融合无需归一化分数，鲁棒且无需调参。
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
            except Exception:  # noqa: BLE001 —— 单路失败不拖垮整体（降级为另一路）
                continue
            for rank, hit in enumerate(hits, start=1):
                key = hit.chunk.chunk_id
                candidates[key] = candidates.get(key, 0.0) + 1.0 / (self.rrf_k + rank)
                found[key] = hit.chunk
        ordered = sorted(candidates.items(), key=lambda kv: -kv[1])[:top_k]
        return [Hit(chunk=found[key], score=score) for key, score in ordered]

    def coverage(self, query: str) -> float:
        """覆盖率闸沿用 BM25 的词元覆盖——语义侧不设闸，避免对同义改写误拒。"""
        return getattr(self.bm25, "coverage", lambda _q: 1.0)(query)


def build_vector_backend(chunks: list[Chunk]) -> Backend:
    """工厂：向量后端（缺依赖时抛异常，由 retriever.build_index 回退 BM25）。"""
    return FaissBackend(chunks=chunks, embedder=SentenceTransformerEmbedder())


def build_hybrid_backend(chunks: list[Chunk]) -> Backend:
    """工厂：BM25 + 向量混合后端。"""
    return HybridBackend(bm25=Bm25Backend(chunks=chunks), vector=build_vector_backend(chunks))
