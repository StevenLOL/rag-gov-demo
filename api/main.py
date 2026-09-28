"""FastAPI 入口（v1）：/health、/ask、/audit。

启动时加载本地语料并构建 BM25 索引；LLM 可选（Ollama 不可达自动降级抽取式）。
v2 将增加 Postgres 会话库与 Streamlit 前端；v3 将在 /ask 前挂 LangGraph 治理编排。
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from ragdemo import audit, citation, llm
from ragdemo.chunker import load_corpus
from ragdemo.config import CORPUS_DIR, REFUSAL_COVERAGE, RETRIEVAL_MIN_SCORE
from ragdemo.retriever import build_index

app = FastAPI(title="rag-gov-demo", version="0.1.0")

# 进程级单例：语料索引在启动时构建一次（语料小，全量重建即可）
_chunks = load_corpus(CORPUS_DIR)
_index = build_index(_chunks)


class AskRequest(BaseModel):
    """POST /ask 请求体。"""

    question: str


class CitationOut(BaseModel):
    """引用条目。"""

    ref: int
    source: str
    title: str
    snippet: str


class AskResponse(BaseModel):
    """POST /ask 响应体（v3 将扩展 approval 字段）。"""

    question: str
    refused: bool
    refusal_reason: str = ""
    answer: str = ""
    citations: list[CitationOut] = []
    mode: str = "extractive"


@app.get("/health")
def health() -> dict:
    """存活检查 + 索引规模（部署探针用）。"""
    return {"status": "ok", "chunks": len(_chunks)}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    """问答主端点：引用 + 拒答双闸，全部请求落审计。"""
    result = citation.answer_question(
        req.question,
        _index,
        generate=llm.generate,  # Ollama 不可达时 citation 内部自动降级
        refusal_coverage=REFUSAL_COVERAGE,
        min_score=RETRIEVAL_MIN_SCORE,
    )
    audit.append_event(
        "refused" if result.refused else "ask",
        {
            "question": req.question,
            "mode": result.mode,
            "n_citations": len(result.citations),
            "reason": result.refusal_reason or "",
        },
    )
    return AskResponse(
        question=result.question,
        refused=result.refused,
        refusal_reason=result.refusal_reason,
        answer=result.answer,
        citations=[
            CitationOut(ref=c.ref, source=c.source, title=c.title, snippet=c.snippet)
            for c in result.citations
        ],
        mode=result.mode,
    )


@app.get("/audit")
def audit_log() -> dict:
    """审计事件查询（v3 换 Postgres 分页）。"""
    return {"events": audit.read_events()}
