"""本地 LLM 生成客户端（v1）。

主路径：Ollama 兼容 HTTP API（数据不出域）。

v1 收尾新增的两个能力（由本机实测驱动：本机有 granite4.2:3b，而默认配置的 qwen2.5:7b 并不存在）：
1. **模型自动发现**：查询 /api/tags 拿到本机已有模型；配置的模型不存在时自动回退到
   同系列或第一个可用模型，避免"配了模型名但本机没有 → 每次请求都等到超时才降级"；
2. **可用性探测**：is_available() 供 API 启动时决定走生成模式还是抽取式降级。

失败语义：本模块不吞错——连接失败/超时抛异常，由 citation.py 降级为抽取式引用模式。
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

# 提示词细节：不要写"[n]"这种占位符字面量——模型会照抄（本机实测结尾出现多余 [n]）。
_PROMPT_TEMPLATE = """你是资料问答助手。只依据给定资料回答，禁止编造。
回答中引用资料时，用方括号加数字编号标注，例如 [1] 或 [2]。

资料：
{context}

问题：{question}

回答："""

# 探测用短超时：生成可以慢，但探测必须快（否则拖慢每个请求）
_PROBE_TIMEOUT = 3.0


def _render_context(chunks: list[Chunk]) -> str:
    """把命中 chunk 渲染成带编号的资料块（编号与引用列表一致）。"""
    blocks = []
    for i, chunk in enumerate(chunks, start=1):
        blocks.append(f"[{i}] 来源 {chunk.source} 「{chunk.title}」：\n{chunk.text}")
    return "\n\n".join(blocks)


def list_models() -> list[str]:
    """列出本机 Ollama 已有模型（/api/tags）。"""
    response = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=_PROBE_TIMEOUT)
    response.raise_for_status()
    return [m["name"] for m in response.json().get("models", [])]


def is_available() -> bool:
    """Ollama 是否可达且有模型（供 API 启动时决定是否启用生成模式）。"""
    try:
        return bool(list_models())
    except Exception:  # noqa: BLE001 —— 探测失败即不可用（上层降级，不中断服务）
        return False


def resolve_model(preferred: str | None = None) -> str | None:
    """解析实际使用的模型：配置名优先 → 同系列 → 第一个可用；都没有返回 None。"""
    try:
        models = list_models()
    except Exception:  # noqa: BLE001
        return None
    if not models:
        return None

    preferred = preferred or OLLAMA_MODEL
    if preferred in models:
        return preferred
    # 同系列回退：配了 qwen2.5:7b 但本机只有 qwen2.5:3b 时也能直接用
    base = preferred.split(":")[0]
    for name in models:
        if name.split(":")[0] == base:
            return name
    return models[0]


def warmup(model: str | None = None) -> bool:
    """启动时预热：把模型载入并常驻，避免首请求撞上冷启动超时。

    本机实测：granite4.2:3b 冷启动（2.2GB 载入 GPU）约 34s，超过普通请求超时；
    预热后单次生成降到数秒。预热失败不影响服务（上层已是抽取式降级）。
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
                "options": {"num_predict": 1},  # 只生成一个 token，纯加载
            },
            timeout=OLLAMA_WARMUP_TIMEOUT,
        )
        response.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001 —— 预热失败只记日志，不阻断启动
        print(f"[llm] 预热失败（将走抽取式降级）：{exc}")
        return False


def generate(question: str, chunks: list[Chunk], model: str | None = None) -> str:
    """调用本地 Ollama 生成带引用标注的答案；失败抛异常（上层降级）。"""
    target = model or resolve_model()
    if target is None:
        raise RuntimeError("Ollama 不可用或本机没有可用模型")

    payload = {
        "model": target,
        "prompt": _PROMPT_TEMPLATE.format(context=_render_context(chunks), question=question),
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,   # 保持常驻，避免每请求重新载入
        # think=false：关闭思考型模型的长链推理（本机 granite4.2 实测 >60s → ~1.7s）
        "think": OLLAMA_THINK,
        "options": {
            "temperature": 0.2,           # 问答场景压低随机性
            "num_predict": OLLAMA_NUM_PREDICT,  # 硬性上限，防止无限生成撞超时
        },
    }
    response = httpx.post(
        f"{OLLAMA_URL}/api/generate", json=payload, timeout=OLLAMA_TIMEOUT
    )
    response.raise_for_status()
    return response.json()["response"].strip()
