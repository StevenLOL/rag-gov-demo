"""FastAPI entry point (v1): /health, /ask, /audit.

Loads the local corpus and builds the BM25 index at startup; the LLM is optional
(automatic fallback to extractive mode when Ollama is unreachable).
v2 will add a Postgres session store and a Streamlit frontend; v3 will put LangGraph
governance orchestration in front of /ask.
"""

from __future__ import annotations

import time
from functools import partial

from fastapi import FastAPI
from pydantic import BaseModel

from ragdemo import acl, audit, citation, llm
from ragdemo.chunker import load_corpus
from ragdemo.config import CORPUS_DIR, REFUSAL_COVERAGE, RETRIEVAL_BACKEND
from ragdemo.retriever import build_index

app = FastAPI(title="rag-gov-demo", version="0.1.0")

# Process-level singleton: the corpus index is built once at startup (small corpus,
# a full rebuild is fine)
_chunks = load_corpus(CORPUS_DIR)
_index = build_index(_chunks)

# LLM availability cache: probing has a cost, and when the service is down no request
# should wait out the full timeout
_llm_state = {"checked": 0.0, "available": False, "model": None}
_LLM_TTL = 30.0  # seconds: re-probe at most once every 30 seconds


def refresh_llm(force: bool = False) -> None:
    """Refresh local LLM availability (with a TTL to avoid frequent probing)."""
    now = time.time()
    if not force and now - _llm_state["checked"] < _LLM_TTL:
        return
    available = llm.is_available()
    _llm_state.update(
        checked=now,
        available=available,
        model=llm.resolve_model() if available else None,
    )


refresh_llm(force=True)  # Probe once at startup so /health can report status immediately


@app.on_event("startup")
def _startup_warmup() -> None:
    """Warm up the local model in the background: prevents the first Q&A request from
    hitting a cold-start timeout (measured ~34s cold start)."""
    if not _llm_state["available"]:
        return

    def _warm() -> None:
        llm.warmup(_llm_state["model"])

    import threading

    threading.Thread(target=_warm, daemon=True).start()


class AskRequest(BaseModel):
    """POST /ask request body."""

    question: str
    # v4d: who is asking, as {"id", "groups", "clearance"}. Declared by the
    # caller and NOT verified -- this demo has no authentication; what it shows
    # is that retrieval is filtered by principal once one exists.
    principal: dict | None = None


class CitationOut(BaseModel):
    """A single citation entry."""

    ref: int
    source: str
    title: str
    snippet: str


class AskResponse(BaseModel):
    """POST /ask response body (v3 will add approval fields)."""

    question: str
    refused: bool
    refusal_reason: str = ""
    answer: str = ""
    citations: list[CitationOut] = []
    mode: str = "extractive"


@app.get("/health")
def health() -> dict:
    """Liveness check + runtime shape (for deployment probes): corpus size, retrieval
    backend, local LLM status."""
    return {
        "status": "ok",
        "chunks": len(_chunks),
        "retrieval_backend": RETRIEVAL_BACKEND,
        "llm_available": _llm_state["available"],
        "llm_model": _llm_state["model"],
    }


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    """Main Q&A endpoint: citation + refusal double gate, every request audited."""
    refresh_llm()  # If Ollama starts only later at runtime, it is discovered within 30 seconds
    generate = partial(llm.generate, model=_llm_state["model"]) if _llm_state["available"] else None
    # Resolve the caller's principal before retrieval: the filter has to run
    # before ranking, so it cannot be applied after the fact.
    principal = acl.principal_from_dict(req.principal) or acl.default_principal()
    result = citation.answer_question(
        req.question,
        _index,
        generate=generate,  # When None, citation falls back to extractive mode
        refusal_coverage=REFUSAL_COVERAGE,
        # min_score is deliberately NOT passed here: the score gate must run on
        # the backend's own scale (BM25 absolute score vs cosine vs RRF), and
        # only the backend knows which one it scores in.
        principal=principal,
    )
    audit.append_event(
        "refused" if result.refused else "ask",
        {
            "question": req.question,
            "principal": principal.to_dict(),
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
    """Audit event query (v3 will switch to Postgres pagination)."""
    return {"events": audit.read_events()}
