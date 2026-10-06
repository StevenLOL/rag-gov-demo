"""citation tests: dual-gate refusal, citation format, extractive fallback."""

from ragdemo.chunker import load_corpus
from ragdemo.config import CORPUS_DIR
from ragdemo.citation import answer_question
from ragdemo.retriever import build_index


def _index():
    return build_index(load_corpus(CORPUS_DIR))


def test_refuses_unrelated_question():
    # Question is Chinese on purpose: the corpus is Chinese.
    result = answer_question("量子纠缠对股票价格的影响是什么", _index())
    assert result.refused
    assert "coverage" in result.refusal_reason
    assert result.citations == []


def test_answers_with_citations():
    result = answer_question("高风险动作执行前需要人工批准吗", _index())
    assert not result.refused
    assert result.citations, "answers must carry citations"
    assert result.citations[0].ref == 1
    assert result.citations[0].source.endswith(".md")
    assert "[1]" in result.answer  # the extractive answer carries citation markers


def test_refuses_low_score_question():
    # Coverage may pass the gate (common characters match), but the BM25 score fails it
    result = answer_question(
        "的了吗呢吧", _index(), refusal_coverage=0.0, min_score=999.0
    )
    assert result.refused
    assert "score" in result.refusal_reason


def test_degrades_to_extractive_when_llm_fails():
    def broken_generate(question, chunks):
        raise RuntimeError("Ollama is not running")

    result = answer_question("docker compose 启动哪些容器", _index(), generate=broken_generate)
    assert not result.refused
    assert result.mode == "extractive"  # degradation is by design
