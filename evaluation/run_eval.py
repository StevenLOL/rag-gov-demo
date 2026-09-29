"""检索质量评估（支持多套语料 / 多套 golden set）。

指标：
- recall@5： golden 答案所在 source 是否出现在 top5 命中里；
- top1：     golden source 是否是 top1（比 recall@5 严格得多）。

用法：
    python evaluation/run_eval.py                        # 默认：治理语料 + golden_set.json
    python evaluation/run_eval.py --corpus-profile legacy # 真实 dosgames 逆向语料
    python evaluation/run_eval.py --golden golden_set_legacy.json --corpus data/corpus_legacy

为什么要有 --corpus-profile / --golden（2026-09-30 补）：
  仓库里有两套语料：
    data/corpus        治理教学语料（5 篇 / 15 chunk）—— 单元测试与 CI 依赖它，不能动默认；
    data/corpus_legacy 真实 dosgames 逆向文档（37 篇 / 1052 chunk）—— 演示与压力测试用。
  两套语料各有自己的 golden set，评估脚本必须能分别跑，而不是改默认目录去互相破坏。

golden set 格式（v3 起支持集合判定）：
    [{"question": "...", "expected_source": "a.md"}]              单值判定
    [{"question": "...", "expected_sources": ["a.md", "b.md"]}]    集合判定（答案本就跨多篇时用）
  另可选 "anchor" 字段：记录该题锚点词的语料归属证据，仅供人工复核，脚本不消费。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 直跑脚本（python evaluation/run_eval.py）时把仓库根目录加入 sys.path，
# 使 `import ragdemo` 生效；经 pytest/make eval（根目录为 cwd）时本行无副作用。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ragdemo.chunker import load_corpus
from ragdemo.config import BASE_DIR, CORPUS_PROFILES
from ragdemo.retriever import build_index

DEFAULT_GOLDEN = Path(__file__).parent / "golden_set.json"


def expected_sources_of(case: dict) -> list[str]:
    """兼容单值（expected_source）与集合（expected_sources）两种写法。"""
    if "expected_sources" in case:
        return list(case["expected_sources"])
    return [case["expected_source"]]


def run(corpus_dir: Path, golden: Path) -> list[dict]:
    """跑完评估并返回逐题结果（v2 由 CI 断言阈值）。"""
    index = build_index(load_corpus(corpus_dir))
    cases = json.loads(golden.read_text(encoding="utf-8"))
    results = []
    for case in cases:
        hits = index.search(case["question"], top_k=5)
        hit_sources = {h.chunk.source for h in hits}
        expected = expected_sources_of(case)
        results.append(
            {
                "question": case["question"],
                "expected_source": expected[0],
                "expected_sources": expected,
                # 集合判定：命中集合中任意一篇即算召回成功
                "recall_at_5": bool(set(expected) & hit_sources),
                "top1_source": hits[0].chunk.source if hits else None,
            }
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="检索质量评估")
    parser.add_argument(
        "--corpus-profile",
        choices=sorted(CORPUS_PROFILES),
        default=None,
        help="语料档位：" + " / ".join(f"{k}={v.name}" for k, v in CORPUS_PROFILES.items()),
    )
    parser.add_argument("--corpus", default=None, help="直接指定语料目录（优先于 --corpus-profile）")
    parser.add_argument("--golden", default=None, help="golden set 文件路径（默认 golden_set.json）")
    args = parser.parse_args()

    if args.corpus:
        corpus_dir = Path(args.corpus)
    else:
        # 未指定时用环境变量 CORPUS_PROFILE，其次默认档位（治理语料）
        import os

        profile = args.corpus_profile or os.getenv("CORPUS_PROFILE", "gov")
        corpus_dir = CORPUS_PROFILES.get(profile, BASE_DIR / "data" / "corpus")
    golden = Path(args.golden) if args.golden else DEFAULT_GOLDEN

    print(f"语料：{corpus_dir}")
    print(f"golden：{golden}\n")

    results = run(corpus_dir, golden)
    passed = sum(1 for r in results if r["recall_at_5"])
    top1 = sum(1 for r in results if r["top1_source"] in r["expected_sources"])
    for r in results:
        mark = "PASS" if r["recall_at_5"] else "MISS"
        t1 = "✓" if r["top1_source"] in r["expected_sources"] else "✗"
        print(f"[{mark}][top1 {t1}] {r['question']}")
        print(f"        expect={r['expected_sources']}  →  top1={r['top1_source']}")
    print(f"\nrecall@5 = {passed}/{len(results)}    top1 = {top1}/{len(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
