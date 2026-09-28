"""引用与拒答（v1 核心："诚实"的产品化）。

判定流程（双保险，阈值见 config.py）：
1. 覆盖率闸：查询词元在语料词典的覆盖率 < REFUSAL_COVERAGE → 拒答；
2. 分数闸：BM25 top1 分数 < RETRIEVAL_MIN_SCORE → 拒答；
3. 双闸都过 → 生成/摘录答案并附引用列表。

拒答不是报错，是一等公民的响应类型：返回 refused=True + 解释话术。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .chunker import Chunk
from .retriever import Bm25Backend, Hit


@dataclass
class Citation:
    """一条引用：能在语料文件里定位到原文。"""

    ref: int          # 序号，与答案文本中的 [n] 对应
    source: str       # 来源文件名
    title: str        # chunk 标题
    snippet: str      # 短摘录


@dataclass
class Answer:
    """/ask 端点的统一响应模型（v3 将扩展 approval 字段）。"""

    question: str
    refused: bool
    refusal_reason: str = ""
    answer: str = ""
    citations: list[Citation] = field(default_factory=list)
    mode: str = "extractive"   # extractive | llm（v2 由 llm.py 决定）


def _build_citations(hits: list[Hit]) -> list[Citation]:
    return [
        Citation(ref=i + 1, source=h.chunk.source, title=h.chunk.title, snippet=h.chunk.snippet)
        for i, h in enumerate(hits)
    ]


def _extractive_answer(hits: list[Hit]) -> str:
    """无 LLM 时的抽取式答案：直接给 top 命中原文 + 引用标记（永远可跑）。"""
    parts = ["根据资料："]
    for i, hit in enumerate(hits[:2], start=1):
        parts.append(f"[{i}] 「{hit.chunk.title}」：{hit.chunk.text.strip()[:300]}")
    return "\n\n".join(parts)


def answer_question(
    question: str,
    index: Bm25Backend,
    generate=None,
    refusal_coverage: float = 0.5,
    min_score: float = 2.0,
) -> Answer:
    """问答主入口。

    generate: 可选的 (question, context_chunks) -> str 生成函数（llm.py 提供）。
              为 None 或调用失败时走抽取式降级——demo 不因缺模型而不可用。
    """
    hits = index.search(question, top_k=3)

    # 闸 1：覆盖率
    coverage = index.coverage(question)
    if not hits or coverage < refusal_coverage:
        return Answer(
            question=question,
            refused=True,
            refusal_reason=(
                f"查询词元在语料中的覆盖率 {coverage:.0%} 低于阈值 "
                f"{refusal_coverage:.0%}，资料中无依据，拒绝编造。"
            ),
        )

    # 闸 2：BM25 分数
    top_score = hits[0].score
    if top_score < min_score:
        return Answer(
            question=question,
            refused=True,
            refusal_reason=(
                f"最相关片段得分 {top_score:.1f} 低于阈值 {min_score:.1f}，"
                "资料中无足够依据，拒绝编造。"
            ),
        )

    # 通过双闸 → 生成或摘录
    mode = "extractive"
    answer_text = ""
    if generate is not None:
        try:
            answer_text = generate(question, [h.chunk for h in hits])
            mode = "llm"
        except Exception as exc:  # noqa: BLE001 —— 降级是设计行为，不是吞错
            answer_text = ""
            # 降级原因记入审计便于排查，这里先留注释锚点（v2 接 Postgres 后落库）
            _ = exc
    if not answer_text:
        answer_text = _extractive_answer(hits)

    return Answer(
        question=question,
        refused=False,
        answer=answer_text,
        citations=_build_citations(hits),
        mode=mode,
    )
