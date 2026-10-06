"""LLM client tests (v1 wrap-up: automatic model discovery + availability probing).

Everything uses monkeypatch doubles and does not depend on whether Ollama is actually
installed locally — the tests must also run reliably in CI.
"""

import httpx
import pytest
from fastapi.testclient import TestClient

from api.main import app  # api is a top-level package (not under ragdemo)
from ragdemo import llm


class _FakeResponse:
    """httpx response double."""

    def __init__(self, payload: dict, ok: bool = True):
        self._payload = payload
        self._ok = ok

    def raise_for_status(self) -> None:
        if not self._ok:
            raise httpx.HTTPError("boom")

    def json(self) -> dict:
        return self._payload


def _patch_tags(monkeypatch, models: list[str]) -> None:
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: _FakeResponse({"models": [{"name": m} for m in models]})
    )


def test_list_models(monkeypatch):
    _patch_tags(monkeypatch, ["granite4.2:3b", "qwen2.5:7b"])
    assert llm.list_models() == ["granite4.2:3b", "qwen2.5:7b"]


def test_is_available_true_and_false(monkeypatch):
    _patch_tags(monkeypatch, ["granite4.2:3b"])
    assert llm.is_available() is True

    monkeypatch.setattr(httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("down")))
    assert llm.is_available() is False


def test_resolve_model_prefers_configured(monkeypatch):
    """When the configured model is available locally, prefer it."""
    _patch_tags(monkeypatch, ["qwen2.5:7b", "granite4.2:3b"])
    assert llm.resolve_model(preferred="qwen2.5:7b") == "qwen2.5:7b"


def test_resolve_model_falls_back_to_same_family(monkeypatch):
    """Configured qwen2.5:7b but only qwen2.5:3b exists locally -> same-family fallback
    (this is the actual local setup)."""
    _patch_tags(monkeypatch, ["qwen2.5:3b"])
    assert llm.resolve_model(preferred="qwen2.5:7b") == "qwen2.5:3b"


def test_resolve_model_falls_back_to_any_local_model(monkeypatch):
    """No same-family model either -> use the first available model, instead of timing
    out and degrading on every request."""
    _patch_tags(monkeypatch, ["granite4.2:3b"])
    assert llm.resolve_model(preferred="qwen2.5:7b") == "granite4.2:3b"


def test_resolve_model_none_when_service_down(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("down")))
    assert llm.resolve_model() is None


def test_generate_builds_prompt_with_citations(monkeypatch):
    """Generation requests must carry numbered source blocks and force answers to cite [n]."""
    captured = {}

    def fake_post(url, json=None, **kwargs):
        captured.update(url=url, payload=json)
        return _FakeResponse({"response": "Human approval required [1]"})

    monkeypatch.setattr(llm.httpx, "post", fake_post)

    class Chunk:
        source = "agent_governance_basics.md"
        title = "人在回路"
        text = "高风险动作必须人工批准。"

    answer = llm.generate("高风险动作要批准吗", [Chunk()], model="granite4.2:3b")
    assert answer == "Human approval required [1]"
    assert captured["payload"]["model"] == "granite4.2:3b"
    assert "[1]" in captured["payload"]["prompt"]
    assert "高风险动作要批准吗" in captured["payload"]["prompt"]
    assert captured["payload"]["options"]["temperature"] == 0.2
    # Guard against unbounded generation: hard token cap + thinking mode off
    # (measured on local granite4.2: >60s -> ~1.7s)
    assert captured["payload"]["options"]["num_predict"] > 0
    assert captured["payload"].get("think") is False


def test_generate_raises_when_no_model(monkeypatch):
    """When no model is available, raise a clear error (the caller degrades) instead of
    silently returning an empty string."""
    monkeypatch.setattr(httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("down")))
    with pytest.raises(RuntimeError):
        llm.generate("问题", [])


def test_health_exposes_runtime_shape():
    """/health must expose the retrieval backend and LLM status — deployment
    troubleshooting depends on it."""
    client = TestClient(app)
    data = client.get("/health").json()
    assert data["status"] == "ok" and data["chunks"] > 0
    assert "retrieval_backend" in data and "llm_available" in data
