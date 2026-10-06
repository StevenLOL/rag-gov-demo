"""Retrieval quality evaluation (multiple corpora / multiple golden sets).

Metrics:
- recall@5: does the golden answer's source appear among the top-5 hits?
- top1:     is the golden source ranked first? (much stricter than recall@5)

Usage:
    python evaluation/run_eval.py                         # default corpus + golden_set.json
    python evaluation/run_eval.py --corpus-profile legacy # large local corpus (if present)
    python evaluation/run_eval.py --golden my_set.json --corpus path/to/corpus

Why --corpus-profile / --golden exist:
  Two corpora are supported by design:
    data/corpus         default demo corpus (5 docs / 15 chunks) — unit tests and CI
                        depend on it; never change the default.
    data/corpus_legacy  a much larger local corpus (kept out of the repository; see
                        .gitignore) used for the scale experiment in the README.
  Each corpus pairs with its own golden set, so the runner must be able to
  evaluate either one without mutating the default.

Golden set format (set-based matching supported):
    [{"question": "...", "expected_source": "a.md"}]             single source
    [{"question": "...", "expected_sources": ["a.md", "b.md"]}]  any-of matching
  Optional "anchor" field: provenance note for human review; not consumed here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# When run directly (python evaluation/run_eval.py), prepend the repo root to
# sys.path so `import ragdemo` works; under pytest/make eval this is a no-op.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ragdemo.chunker import load_corpus
from ragdemo.config import BASE_DIR, CORPUS_PROFILES
from ragdemo.retriever import build_index

DEFAULT_GOLDEN = Path(__file__).parent / "golden_set.json"


def expected_sources_of(case: dict) -> list[str]:
    """Accept both single-source (`expected_source`) and any-of (`expected_sources`)."""
    if "expected_sources" in case:
        return list(case["expected_sources"])
    return [case["expected_source"]]


def run(corpus_dir: Path, golden: Path) -> list[dict]:
    """Run the evaluation and return per-question results."""
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
                # any-of matching: hitting any one of the expected sources counts
                "recall_at_5": bool(set(expected) & hit_sources),
                "top1_source": hits[0].chunk.source if hits else None,
            }
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Retrieval quality evaluation")
    parser.add_argument(
        "--corpus-profile",
        choices=sorted(CORPUS_PROFILES),
        default=None,
        help="Corpus profile: " + " / ".join(f"{k}={v.name}" for k, v in CORPUS_PROFILES.items()),
    )
    parser.add_argument("--corpus", default=None, help="Corpus directory (overrides --corpus-profile)")
    parser.add_argument("--golden", default=None, help="Golden set path (default: golden_set.json)")
    args = parser.parse_args()

    if args.corpus:
        corpus_dir = Path(args.corpus)
    else:
        # Fall back to the CORPUS_PROFILE env var, then the default profile.
        import os

        profile = args.corpus_profile or os.getenv("CORPUS_PROFILE", "gov")
        corpus_dir = CORPUS_PROFILES.get(profile, BASE_DIR / "data" / "corpus")
    golden = Path(args.golden) if args.golden else DEFAULT_GOLDEN

    print(f"Corpus: {corpus_dir}")
    print(f"Golden: {golden}\n")

    results = run(corpus_dir, golden)
    passed = sum(1 for r in results if r["recall_at_5"])
    top1 = sum(1 for r in results if r["top1_source"] in r["expected_sources"])
    for r in results:
        mark = "PASS" if r["recall_at_5"] else "MISS"
        t1 = "OK" if r["top1_source"] in r["expected_sources"] else "--"
        print(f"[{mark}][top1 {t1}] {r['question']}")
        print(f"        expect={r['expected_sources']}  ->  top1={r['top1_source']}")
    print(f"\nrecall@5 = {passed}/{len(results)}    top1 = {top1}/{len(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
