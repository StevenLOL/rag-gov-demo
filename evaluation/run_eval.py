"""检索质量评估（v2 扩充到 20 题；当前 6 题冒烟版）。

指标：
- recall@5： golden 答案所在 source 是否出现在 top5 命中里；
- 引用命中率（v2）：golden chunk 是否被引用列表包含。

用法：python evaluation/run_eval.py   （或 make eval）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 直跑脚本（python evaluation/run_eval.py）时把仓库根目录加入 sys.path，
# 使 `import ragdemo` 生效；经 pytest/make eval（根目录为 cwd）时本行无副作用。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ragdemo.chunker import load_corpus
from ragdemo.config import CORPUS_DIR
from ragdemo.retriever import build_index

GOLDEN_SET = Path(__file__).parent / "golden_set.json"


def run() -> list[dict]:
    """跑完评估并返回逐题结果（v2 由 CI 断言阈值）。"""
    index = build_index(load_corpus(CORPUS_DIR))
    cases = json.loads(GOLDEN_SET.read_text(encoding="utf-8"))
    results = []
    for case in cases:
        hits = index.search(case["question"], top_k=5)
        hit_sources = {h.chunk.source for h in hits}
        results.append(
            {
                "question": case["question"],
                "expected_source": case["expected_source"],
                "recall_at_5": case["expected_source"] in hit_sources,
                "top1_source": hits[0].chunk.source if hits else None,
            }
        )
    return results


if __name__ == "__main__":
    results = run()
    passed = sum(1 for r in results if r["recall_at_5"])
    for r in results:
        mark = "PASS" if r["recall_at_5"] else "MISS"
        print(f"[{mark}] {r['question']}  →  top1={r['top1_source']}")
    print(f"\nrecall@5 = {passed}/{len(results)}")
