"""retriever 测试：BM25 排序、双语分词、覆盖率。"""

from ragdemo.chunker import load_corpus
from ragdemo.config import CORPUS_DIR
from ragdemo.retriever import build_index, tokenize


def test_tokenize_bilingual():
    tokens = tokenize("数据分级 data classification")
    assert "数据" in tokens and "分级" in tokens  # CJK 二元组
    assert "数据分级" not in tokens                 # 只切到二元组，无 4 元组
    assert "classification" in tokens               # 拉丁小写词


def test_real_corpus_loads():
    chunks = load_corpus(CORPUS_DIR)
    assert len(chunks) >= 5  # 三份语料至少切出 5 个 chunk


def test_related_query_ranks_governance_chunk():
    index = build_index(load_corpus(CORPUS_DIR))
    hits = index.search("高风险动作 执行前 人工批准")
    assert hits, "治理语料应命中"
    assert hits[0].chunk.source == "agent_governance_basics.md"


def test_coverage_low_for_unrelated_query():
    index = build_index(load_corpus(CORPUS_DIR))
    # 治理语料里没有"量子纠缠"相关内容
    assert index.coverage("量子纠缠股票价格走势") < 0.5


def test_coverage_high_for_related_query():
    index = build_index(load_corpus(CORPUS_DIR))
    assert index.coverage("敏感信息 数据分级 本地部署") > 0.5
