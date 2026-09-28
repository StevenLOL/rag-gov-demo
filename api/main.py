"""FastAPI 入口（v1）：/health、/ask、/audit。

启动时加载本地语料并构建 BM25 索引；LLM 可选（Ollama 不可达自动降级抽取式）。
v2 将增加 Postgres 会话库与 Streamlit 前端；v3 将在 /ask 前挂 LangGraph 治理编排。
"""

from __future__ import annotations

import time
from functools import partial

from fastapi import FastAPI
from pydantic import BaseModel

from ragdemo import audit, citation, llm
from ragdemo.chunker import load_corpus
from ragdemo.config import CORPUS_DIR, REFUSAL_COVERAGE, RETRIEVAL_BACKEND, RETRIEVAL_MIN_SCORE
from ragdemo.retriever import build_index

app = FastAPI(title="rag-gov-demo", version="0.1.0")

# 进程级单例：语料索引在启动时构建一次（语料小，全量重建即可）
_chunks = load_corpus(CORPUS_DIR)
_index = build_index(_chunks)

# LLM 可用性缓存：探测有成本，服务不可用时也不能让每个请求都等满超时
_llm_state = {"checked": 0.0, "available": False, "model": None}
_LLM_TTL = 30.0  # 秒：最多每 30 秒重新探测一次


def refresh_llm(force: bool = False) -> None:
    """刷新本地 LLM 可用性（带 TTL，避免频繁探测）。"""
    now = time.time()
    if not force and now - _llm_state["checked"] < _LLM_TTL:
        return
    available = llm.is_available()
    _llm_state.update(
        checked=now,
        available=available,
        model=llm.resolve_model() if available else None,
    )


refresh_llm(force=True)  # 启动时探一次，/health 立刻能报状态


@app.on_event("startup")
def _startup_warmup() -> None:
    """后台预热本地模型：避免首个问答请求撞上冷启动超时（实测冷启动 ~34s）。"""
    if not _llm_state["available"]:
        return

    def _warm() -> None:
        llm.warmup(_llm_state["model"])

    import threading

    threading.Thread(target=_warm, daemon=True).start()


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
    """存活检查 + 运行形态（部署探针用）：语料规模、检索后端、本地 LLM 状态。"""
    return {
        "status": "ok",
        "chunks": len(_chunks),
        "retrieval_backend": RETRIEVAL_BACKEND,
        "llm_available": _llm_state["available"],
        "llm_model": _llm_state["model"],
    }


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    """问答主端点：引用 + 拒答双闸，全部请求落审计。"""
    refresh_llm()  # 运行期若 Ollama 才启动，最多 30 秒内被发现
    generate = partial(llm.generate, model=_llm_state["model"]) if _llm_state["available"] else None
    result = citation.answer_question(
        req.question,
        _index,
        generate=generate,  # 为 None 时 citation 走抽取式降级
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
