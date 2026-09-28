"""citation 测试：双闸拒答、引用格式、抽取式降级。"""

from ragdemo.chunker import load_corpus
from ragdemo.config import CORPUS_DIR
from ragdemo.citation import answer_question
from ragdemo.retriever import build_index


def _index():
    return build_index(load_corpus(CORPUS_DIR))


def test_refuses_unrelated_question():
    result = answer_question("量子纠缠对股票价格的影响是什么", _index())
    assert result.refused
    assert "覆盖率" in result.refusal_reason
    assert result.citations == []


def test_answers_with_citations():
    result = answer_question("高风险动作执行前需要人工批准吗", _index())
    assert not result.refused
    assert result.citations, "答案必须带引用"
    assert result.citations[0].ref == 1
    assert result.citations[0].source.endswith(".md")
    assert "[1]" in result.answer  # 抽取式答案带引用标记


def test_refuses_low_score_question():
    # 覆盖率可能过闸（常见字命中），但 BM25 分数不过闸
    result = answer_question(
        "的了吗呢吧", _index(), refusal_coverage=0.0, min_score=999.0
    )
    assert result.refused
    assert "得分" in result.refusal_reason


def test_degrades_to_extractive_when_llm_fails():
    def broken_generate(question, chunks):
        raise RuntimeError("Ollama 未启动")

    result = answer_question("docker compose 启动哪些容器", _index(), generate=broken_generate)
    assert not result.refused
    assert result.mode == "extractive"  # 降级是设计行为
