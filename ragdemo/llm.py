"""Local LLM generation client (v1).

Main path: Ollama-compatible HTTP API (data never leaves the domain).

Two capabilities added at v1 wrap-up (driven by on-device testing: this
machine has granite4.2:3b, while the default-configured qwen2.5:7b does not
exist):
1. **Model auto-discovery**: query /api/tags to get locally available models;
   when the configured model is missing, automatically fall back to the same
   family or the first available model, avoiding "configured model name not
   present on this machine -> every request waits until timeout before
   degrading";
2. **Availability probing**: is_available() lets the API decide at startup
   between generation mode and extractive fallback.

Failure semantics: this module never swallows errors — connection
failures/timeouts raise exceptions, and citation.py degrades to extractive
citation mode.
"""

from __future__ import annotations

import httpx

from .chunker import Chunk
from .config import (
    OLLAMA_KEEP_ALIVE,
    OLLAMA_MODEL,
    OLLAMA_NUM_PREDICT,
    OLLAMA_THINK,
    OLLAMA_TIMEOUT,
    OLLAMA_URL,
    OLLAMA_WARMUP_TIMEOUT,
)

# Prompt detail: do not write placeholder literals like "[n]" — the model will
# copy them verbatim (verified on-device: spurious [n] showed up at the end).
# The prompt is written in English; the corpus passages it embeds are Chinese
# and the model answers over them, citing by number.
_PROMPT_TEMPLATE = """You are a corpus-grounded QA assistant. Answer strictly from the
given corpus passages; never fabricate. When citing a passage, mark it with a
bracketed number, e.g. [1] or [2].

Corpus:
{context}

Question: {question}

Answer:"""

# Short probe timeout: generation may be slow, but probing must be fast
# (otherwise it slows down every request)
_PROBE_TIMEOUT = 3.0


def _render_context(chunks: list[Chunk]) -> str:
    """Render hit chunks into numbered context blocks (numbering matches the
    citation list)."""
    blocks = []
    for i, chunk in enumerate(chunks, start=1):
        blocks.append(f"[{i}] Source {chunk.source} | {chunk.title}:\n{chunk.text}")
    return "\n\n".join(blocks)


def list_models() -> list[str]:
    """List models already present on the local Ollama instance (/api/tags)."""
    response = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=_PROBE_TIMEOUT)
    response.raise_for_status()
    return [m["name"] for m in response.json().get("models", [])]


def is_available() -> bool:
    """Whether Ollama is reachable and has models (lets the API decide at startup
    whether to enable generation mode)."""
    try:
        return bool(list_models())
    except Exception:  # noqa: BLE001 -- probe failure means unavailable (upper layer
        # degrades; service is not interrupted)
        return False


def resolve_model(preferred: str | None = None) -> str | None:
    """Resolve the model actually used: configured name first -> same family -> first
    available; None when none exist."""
    try:
        models = list_models()
    except Exception:  # noqa: BLE001
        return None
    if not models:
        return None

    preferred = preferred or OLLAMA_MODEL
    if preferred in models:
        return preferred
    # Same-family fallback: if qwen2.5:7b is configured but only qwen2.5:3b exists
    # locally, it can still be used directly
    base = preferred.split(":")[0]
    for name in models:
        if name.split(":")[0] == base:
            return name
    return models[0]


def warmup(model: str | None = None) -> bool:
    """Warm up at startup: load the model and keep it resident, avoiding the first
    request hitting a cold-start timeout.

    Measured on this machine: granite4.2:3b cold start (loading 2.2GB onto GPU)
    takes ~34s, exceeding the normal request timeout; after warm-up, a single
    generation drops to a few seconds. Warm-up failure does not affect service
    (the upper layer is already the extractive fallback).
    """
    target = model or resolve_model()
    if target is None:
        return False
    try:
        response = httpx.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": target,
                "prompt": "hi",
                "stream": False,
                "keep_alive": OLLAMA_KEEP_ALIVE,
                "options": {"num_predict": 1},  # generate one token only; purely loading
            },
            timeout=OLLAMA_WARMUP_TIMEOUT,
        )
        response.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001 -- warm-up failure is only logged; startup
        # is not blocked
        print(f"[llm] warmup failed (will degrade to extractive mode): {exc}")
        return False


def generate(question: str, chunks: list[Chunk], model: str | None = None) -> str:
    """Call local Ollama to generate an answer with citation markers; raises on
    failure (upper layer degrades)."""
    target = model or resolve_model()
    if target is None:
        raise RuntimeError("Ollama unavailable or no usable model found locally")

    payload = {
        "model": target,
        "prompt": _PROMPT_TEMPLATE.format(context=_render_context(chunks), question=question),
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,   # keep resident; avoid reloading per request
        # think=false: disable the long chain-of-thought of thinking models
        # (measured on local granite4.2: >60s -> ~1.7s)
        "think": OLLAMA_THINK,
        "options": {
            "temperature": 0.2,           # low randomness for Q&A scenarios
            "num_predict": OLLAMA_NUM_PREDICT,  # hard cap; prevents unbounded generation
            # hitting the timeout
        },
    }
    response = httpx.post(
        f"{OLLAMA_URL}/api/generate", json=payload, timeout=OLLAMA_TIMEOUT
    )
    response.raise_for_status()
    return response.json()["response"].strip()
