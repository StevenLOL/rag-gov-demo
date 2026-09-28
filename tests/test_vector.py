"""向量/混合检索测试（v2）。

分两类：
1. 纯 Python 可跑的（RRF 融合、工厂回退）——永远执行，不依赖模型；
2. 需要本地嵌入模型的（FAISS 端到端）——缺依赖或模型下载失败时自动 skip。
"""

import pytest

from ragdemo.chunker import Chunk, load_corpus
from ragdemo.config import CORPUS_DIR
from ragdemo.retriever import Bm25Backend, Hit, build_index


class _FakeBackend:
    """可控的假后端：按传入顺序返回命中（用于验证 RRF 只看排名不看分数）。"""

    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks

    def search(self, query: str, top_k: int = 5) -> list[Hit]:
        # 故意用离谱的分数尺度——验证 RRF 对分数尺度免疫
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
    """RRF 按排名融合：两路都排第一的 chunk 必须第一；单路独有的也能进入结果。"""
    from ragdemo.vector import HybridBackend

    chunks = _chunks()
    # 路径1：甲、乙、丙；路径2：乙、丙、甲
    # → 乙 = 1/62 + 1/61 最高，甲 = 1/61 + 1/63 次之，丙 = 1/63 + 1/62 最低
    # 注：若两路排名对称（如 甲1乙2 vs 乙1甲2），RRF 会出现并列——这是 RRF 的性质而非 bug
    backend = HybridBackend(
        bm25=_FakeBackend(chunks), vector=_FakeBackend([chunks[1], chunks[2], chunks[0]])
    )
    hits = backend.search("任意问题", top_k=3)
    assert [h.chunk.chunk_id for h in hits] == ["b#0", "a#0", "c#0"]
    # RRF 分数应远小于输入的夸张分数（说明看的是排名）
    assert all(0 < h.score < 1 for h in hits)


def test_rrf_score_formula():
    """RRF 公式校验：k=60 时两路均第一 → 2/(60+1)。"""
    from ragdemo.vector import HybridBackend

    chunks = _chunks()[:1]
    backend = HybridBackend(bm25=_FakeBackend(chunks), vector=_FakeBackend(chunks))
    hits = backend.search("x", top_k=1)
    assert hits[0].score == pytest.approx(2 / 61)


def test_hybrid_coverage_uses_bm25():
    """覆盖率闸沿用 BM25 词元覆盖（语义侧不设闸，避免对同义改写误拒）。"""
    from ragdemo.vector import HybridBackend

    chunks = load_corpus(CORPUS_DIR)
    bm25 = Bm25Backend(chunks=chunks)
    backend = HybridBackend(bm25=bm25, vector=_FakeBackend(chunks))
    assert backend.coverage("量子纠缠股票价格走势") < 0.5


def test_build_index_default_is_bm25():
    """默认零依赖：不装向量依赖也必须能用。"""
    index = build_index(load_corpus(CORPUS_DIR))
    assert isinstance(index, Bm25Backend)


def test_vector_backend_end_to_end():
    """FAISS 端到端（需本地嵌入模型；不可用时 skip，不算失败）。"""
    st = pytest.importorskip("sentence_transformers", reason="未安装 sentence-transformers")
    pytest.importorskip("faiss", reason="未安装 faiss-cpu")

    from ragdemo.vector import build_vector_backend

    chunks = load_corpus(CORPUS_DIR)
    try:
        index = build_vector_backend(chunks)
    except Exception as exc:  # noqa: BLE001 —— 模型下载失败时跳过（网络受限环境）
        pytest.skip(f"嵌入模型不可用：{exc}")

    hits = index.search("高风险动作执行前需要人工批准吗", top_k=3)
    assert hits, "语义检索应命中治理语料"
    # 归一化后内积 = 余弦，分数必须落在 [-1, 1]
    assert all(-1.0 <= h.score <= 1.0 for h in hits)
    assert hits[0].chunk.source == "agent_governance_basics.md"
