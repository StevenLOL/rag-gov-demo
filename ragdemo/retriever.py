"""BM25 检索器（v1，零依赖纯 Python 实现）。

为什么手写 BM25 而不是上向量检索：
- v1 的目标是把"引用+拒答"的骨架跑通，BM25 够用且零模型下载；
- 接口按可替换设计（Backend 协议），v2 引入本地 embedding + FAISS 时不动上层；
- 双语分词：拉丁词按词切，CJK 按字 + 二元组（bigram）切——治理语料中英混排也能命中。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Protocol

from .chunker import Chunk

_LATIN_RE = re.compile(r"[a-zA-Z0-9]+")
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    """双语分词：拉丁小写词 + CJK 单字与二元组。"""
    tokens = [t.lower() for t in _LATIN_RE.findall(text)]
    for run in _CJK_RUN_RE.findall(text):
        chars = list(run)
        tokens.extend(chars)
        tokens.extend(a + b for a, b in zip(chars, chars[1:]))
    return tokens


@dataclass
class Hit:
    """一条检索命中。"""

    chunk: Chunk
    score: float


class Backend(Protocol):
    """检索后端协议（v2 将提供 FaissBackend 实现）。"""

    def search(self, query: str, top_k: int = 5) -> list[Hit]: ...


@dataclass
class Bm25Backend:
    """Okapi BM25（k1=1.5, b=0.75），内存索引，启动时构建。"""

    chunks: list[Chunk]
    k1: float = 1.5
    b: float = 0.75
    # 以下字段在 __post_init__ 中构建
    doc_tokens: list[list[str]] = field(default_factory=list, init=False)
    doc_lens: list[int] = field(default_factory=list, init=False)
    df: dict[str, int] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        for chunk in self.chunks:
            # 标题参与分词：标题是治理语料里最强的主题信号
            tokens = tokenize(chunk.title + " " + chunk.text)
            self.doc_tokens.append(tokens)
            self.doc_lens.append(len(tokens))
        for tokens in self.doc_tokens:
            for term in set(tokens):
                self.df[term] = self.df.get(term, 0) + 1
        self.n_docs = len(self.chunks)
        self.avgdl = sum(self.doc_lens) / self.n_docs if self.n_docs else 0.0

    def _idf(self, term: str) -> float:
        """BM25 IDF（含 doc frequency = 0 的保护）。"""
        df = self.df.get(term, 0)
        if df == 0:
            return 0.0
        return math.log((self.n_docs - df + 0.5) / df + 1.0)

    def search(self, query: str, top_k: int = 5) -> list[Hit]:
        """返回按 BM25 分数降序的 top_k 命中。"""
        q_tokens = tokenize(query)
        scores = [0.0] * self.n_docs
        for i, tokens in enumerate(self.doc_tokens):
            if not tokens:
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
        """查询词元（去重）在语料词典中的覆盖率——拒答判定的第一道闸。

        返回值 0~1：1 表示查询里每个词元语料里都出现过。
        """
        q_tokens = set(tokenize(query))
        if not q_tokens:
            return 1.0
        hits = sum(1 for t in q_tokens if t in self.df)
        return hits / len(q_tokens)


def build_index(chunks: list[Chunk], backend: str | None = None) -> Backend:
    """工厂函数：按配置选择检索后端，向量依赖缺失时自动回退 BM25。

    backend: bm25（默认，零依赖）| vector（FAISS）| hybrid（BM25 ⊕ 向量，RRF 融合）
    """
    from .config import RETRIEVAL_BACKEND  # 延迟导入避免配置/检索循环依赖

    backend = backend or RETRIEVAL_BACKEND
    if backend in ("vector", "hybrid"):
        try:
            from .vector import build_hybrid_backend, build_vector_backend
            return (
                build_hybrid_backend(chunks)
                if backend == "hybrid"
                else build_vector_backend(chunks)
            )
        except Exception as exc:  # noqa: BLE001 —— 依赖/模型不可用时降级，不中断服务
            import sys

            print(f"[retriever] 向量后端不可用（{exc}），回退 BM25", file=sys.stderr)
    return Bm25Backend(chunks=chunks)
