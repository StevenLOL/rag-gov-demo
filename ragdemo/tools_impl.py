"""工具真实实现注册表 —— 治理图 execute 节点的分派表。

【为什么用注册表而不是 if/else 链】
治理图（agents/graph.py）只关心「该不该做」，
本模块只关心「怎么做」。两者解耦后：
  - 新增工具 = 注册一个函数，不动治理逻辑（开闭原则）；
  - 未注册的工具（如 export_report / delete_record）走受控模拟，
    保证 tests/test_governance.py 的既有断言不被真实副作用污染。

【注册的工具】
  search_docs          low  真实：BM25/向量检索本地语料，带出处
  scan_asset_package   low  真实：只读扫描素材包（不落盘）
  extract_game_assets  high 真实：批量导出素材到磁盘（唯一写副作用）
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Callable

from . import assets
from .chunker import load_corpus
from .config import CORPUS_DIR, RETRIEVAL_BACKEND
from .retriever import build_index

Impl = Callable[[dict[str, Any]], dict[str, Any]]

_REGISTRY: dict[str, Impl] = {}


def register(name: str) -> Callable[[Impl], Impl]:
    """注册工具实现（装饰器用法见下方各函数）。"""

    def _wrap(fn: Impl) -> Impl:
        _REGISTRY[name] = fn
        return fn

    return _wrap


def dispatch(tool: str, params: dict[str, Any]) -> dict[str, Any]:
    """执行工具；未注册则回退到「受控模拟」（不产生任何真实副作用）。"""
    fn = _REGISTRY.get(tool)
    if fn is None:
        return {"simulated": True, "tool": tool, "params": params}
    return fn(params)


def has_impl(tool: str) -> bool:
    return tool in _REGISTRY


# ---------------------------------------------------------------- 检索

@lru_cache(maxsize=1)
def _index():
    """语料索引（进程内单例；MCP server 启动只构建一次）。"""
    return build_index(load_corpus(CORPUS_DIR), RETRIEVAL_BACKEND)


@register("search_docs")
def impl_search_docs(params: dict[str, Any]) -> dict[str, Any]:
    """检索本地治理语料，返回带出处的片段（引用是 RAG 可信度的底线）。"""
    query = params.get("query") or params.get("q") or ""
    top_k = int(params.get("top_k", 3))
    hits = _index().search(query, top_k=top_k)
    return {
        "query": query,
        "top_k": top_k,
        "hits": [
            {
                "chunk_id": h.chunk.chunk_id,
                "source": h.chunk.source,
                "title": h.chunk.title,
                "snippet": h.chunk.snippet,
                "score": round(float(h.score), 4),
            }
            for h in hits
        ],
    }


# ---------------------------------------------------------------- 素材

@register("scan_asset_package")
def impl_scan_asset_package(params: dict[str, Any]) -> dict[str, Any]:
    """只读扫描：统计 + 分类分布 + 抽样路径。不写盘，因此是低风险能力。"""
    result = assets.scan_package(
        params["package"], per_category=int(params.get("per_category", 5))
    )
    return result.to_dict()


@register("extract_game_assets")
def impl_extract_game_assets(params: dict[str, Any]) -> dict[str, Any]:
    """批量导出素材（高风险：真实写盘）。

    注意：本函数不做任何策略判断——授权校验由 ragdemo/policy.py 在
    execute 节点之前完成。执行层保持"傻"，策略层才能被单独测试。
    """
    return assets.extract_assets(
        package_id=params["package"],
        out_dir=params["out_dir"],
        categories=params.get("categories"),
        per_category=int(params.get("per_category", 3)),
        size=params.get("size"),
    )
