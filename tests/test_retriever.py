"""retriever tests: BM25 ranking, bilingual tokenization, coverage."""

from ragdemo.chunker import load_corpus
from ragdemo.config import CORPUS_DIR
from ragdemo.retriever import build_index, tokenize


def test_tokenize_bilingual():
    tokens = tokenize("数据分级 data classification")
    assert "数据" in tokens and "分级" in tokens  # CJK bigrams
    assert "数据分级" not in tokens                 # Bigrams only, no 4-grams
    assert "classification" in tokens               # Lowercase Latin words


def test_real_corpus_loads():
    chunks = load_corpus(CORPUS_DIR)
    assert len(chunks) >= 5  # Three corpus docs yield at least 5 chunks


def test_related_query_ranks_governance_chunk():
    index = build_index(load_corpus(CORPUS_DIR))
    hits = index.search("高风险动作 执行前 人工批准")
    assert hits, "governance corpus should be hit"
    assert hits[0].chunk.source == "agent_governance_basics.md"


def test_coverage_low_for_unrelated_query():
    index = build_index(load_corpus(CORPUS_DIR))
    # The governance corpus contains nothing about "quantum entanglement"
    assert index.coverage("量子纠缠股票价格走势") < 0.5


def test_coverage_high_for_related_query():
    index = build_index(load_corpus(CORPUS_DIR))
    assert index.coverage("敏感信息 数据分级 本地部署") > 0.5
