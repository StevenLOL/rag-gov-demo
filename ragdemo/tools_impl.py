"""Registry of real tool implementations — dispatch table for the governance
graph's execute node.

[Why a registry instead of an if/else chain]
The governance graph (agents/graph.py) only cares about "whether it should be
done"; this module only cares about "how it is done". Once decoupled:
  - Adding a tool = registering a function, without touching governance logic
    (open-closed principle);
  - Unregistered tools (e.g. export_report / delete_record) fall back to
    controlled simulation, keeping the existing assertions in
    tests/test_governance.py free from real side effects.

[Registered tools]
  search_docs          low  real: BM25/vector retrieval over the local corpus,
                            with provenance
  scan_asset_package   low  real: read-only scan of an asset package (no disk
                            writes)
  extract_game_assets  high real: bulk asset export to disk (the only write
                            side effect)
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
    """Register a tool implementation (decorator usage shown in the functions below)."""

    def _wrap(fn: Impl) -> Impl:
        _REGISTRY[name] = fn
        return fn

    return _wrap


def dispatch(tool: str, params: dict[str, Any]) -> dict[str, Any]:
    """Execute a tool; falls back to "controlled simulation" when unregistered
    (produces no real side effects)."""
    fn = _REGISTRY.get(tool)
    if fn is None:
        return {"simulated": True, "tool": tool, "params": params}
    return fn(params)


def has_impl(tool: str) -> bool:
    return tool in _REGISTRY


# ---------------------------------------------------------------- retrieval

@lru_cache(maxsize=1)
def _index():
    """Corpus index (in-process singleton; built once when the MCP server starts)."""
    return build_index(load_corpus(CORPUS_DIR), RETRIEVAL_BACKEND)


@register("search_docs")
def impl_search_docs(params: dict[str, Any]) -> dict[str, Any]:
    """Retrieve from the local governance corpus, returning snippets with provenance
    (citations are the bottom line of RAG trustworthiness)."""
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


# ---------------------------------------------------------------- assets

@register("scan_asset_package")
def impl_scan_asset_package(params: dict[str, Any]) -> dict[str, Any]:
    """Read-only scan: totals + category distribution + sampled paths. No disk writes,
    hence a low-risk capability."""
    result = assets.scan_package(
        params["package"], per_category=int(params.get("per_category", 5))
    )
    return result.to_dict()


@register("extract_game_assets")
def impl_extract_game_assets(params: dict[str, Any]) -> dict[str, Any]:
    """Bulk asset export (high risk: real disk writes).

    Note: this function performs no policy checks — authorization validation is
    done by ragdemo/policy.py before the execute node. Keeping the execution
    layer "dumb" is what makes the policy layer independently testable.
    """
    return assets.extract_assets(
        package_id=params["package"],
        out_dir=params["out_dir"],
        categories=params.get("categories"),
        per_category=int(params.get("per_category", 3)),
        size=params.get("size"),
    )
