"""LLM 客户端测试（v1 收尾：模型自动发现 + 可用性探测）。

全部用 monkeypatch 替身，不依赖本机是否真的装了 Ollama——CI 里也必须稳定可跑。
"""

import httpx
import pytest
from fastapi.testclient import TestClient

from api.main import app  # api 是顶层包（不在 ragdemo 下）
from ragdemo import llm


class _FakeResponse:
    """httpx 响应替身。"""

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
    """本机有配置模型时优先用它。"""
    _patch_tags(monkeypatch, ["qwen2.5:7b", "granite4.2:3b"])
    assert llm.resolve_model(preferred="qwen2.5:7b") == "qwen2.5:7b"


def test_resolve_model_falls_back_to_same_family(monkeypatch):
    """配置 qwen2.5:7b 但本机只有 qwen2.5:3b → 同系列回退（本机就是这个情况）。"""
    _patch_tags(monkeypatch, ["qwen2.5:3b"])
    assert llm.resolve_model(preferred="qwen2.5:7b") == "qwen2.5:3b"


def test_resolve_model_falls_back_to_any_local_model(monkeypatch):
    """同系列也没有 → 用第一个可用模型，而不是每次请求都超时降级。"""
    _patch_tags(monkeypatch, ["granite4.2:3b"])
    assert llm.resolve_model(preferred="qwen2.5:7b") == "granite4.2:3b"


def test_resolve_model_none_when_service_down(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("down")))
    assert llm.resolve_model() is None


def test_generate_builds_prompt_with_citations(monkeypatch):
    """生成请求必须带上带编号的资料块，并强制回答标注 [n]。"""
    captured = {}

    def fake_post(url, json=None, **kwargs):
        captured.update(url=url, payload=json)
        return _FakeResponse({"response": "需要人工批准 [1]"})

    monkeypatch.setattr(llm.httpx, "post", fake_post)

    class Chunk:
        source = "agent_governance_basics.md"
        title = "人在回路"
        text = "高风险动作必须人工批准。"

    answer = llm.generate("高风险动作要批准吗", [Chunk()], model="granite4.2:3b")
    assert answer == "需要人工批准 [1]"
    assert captured["payload"]["model"] == "granite4.2:3b"
    assert "[1]" in captured["payload"]["prompt"]
    assert "高风险动作要批准吗" in captured["payload"]["prompt"]
    assert captured["payload"]["options"]["temperature"] == 0.2


def test_generate_raises_when_no_model(monkeypatch):
    """没有可用模型时明确报错（上层降级），不静默返回空串。"""
    monkeypatch.setattr(httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("down")))
    with pytest.raises(RuntimeError):
        llm.generate("问题", [])


def test_health_exposes_runtime_shape():
    """/health 必须暴露检索后端与 LLM 状态——部署排障靠它。"""
    client = TestClient(app)
    data = client.get("/health").json()
    assert data["status"] == "ok" and data["chunks"] > 0
    assert "retrieval_backend" in data and "llm_available" in data
