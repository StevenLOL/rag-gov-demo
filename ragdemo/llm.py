"""本地 LLM 生成客户端（v1）。

主路径：Ollama 兼容 HTTP API（数据不出域）。
任何失败（服务未起/超时/模型缺失）都抛给上层由 citation.py 降级为抽取式——
本模块不吞错、不重试（v2 再加退避重试），保证失败路径可观测。
"""

from __future__ import annotations

import httpx

from .chunker import Chunk
from .config import OLLAMA_MODEL, OLLAMA_TIMEOUT, OLLAMA_URL

_PROMPT_TEMPLATE = """你是资料问答助手。只依据给定资料回答，禁止编造。
回答末尾用 [n] 标注所引用资料的编号。

资料：
{context}

问题：{question}

回答："""


def _render_context(chunks: list[Chunk]) -> str:
    """把命中 chunk 渲染成带编号的资料块（编号与引用列表一致）。"""
    blocks = []
    for i, chunk in enumerate(chunks, start=1):
        blocks.append(f"[{i}] 来源 {chunk.source} 「{chunk.title}」：\n{chunk.text}")
    return "\n\n".join(blocks)


def generate(question: str, chunks: list[Chunk]) -> str:
    """调用本地 Ollama 生成带引用标注的答案；失败抛异常（上层降级）。"""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": _PROMPT_TEMPLATE.format(context=_render_context(chunks), question=question),
        "stream": False,
        "options": {"temperature": 0.2},  # 问答场景压低随机性
    }
    response = httpx.post(
        f"{OLLAMA_URL}/api/generate", json=payload, timeout=OLLAMA_TIMEOUT
    )
    response.raise_for_status()
    return response.json()["response"].strip()
