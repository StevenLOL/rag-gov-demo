"""Retrieval quality evaluation (multiple corpora / multiple golden sets / multiple backends).

Metrics:
- recall@5: does the golden answer's source appear among the top-5 hits?
- top1:     is the golden source ranked first? (much stricter than recall@5)
- MRR:      mean reciprocal rank of the first expected source (sensitive to *where*
            in the top-5 the answer lands, which recall@5 is blind to)

Cost columns are part of the result, not an afterthought: a backend that wins on
recall but needs a model download and 30x the index-build time is a different
decision. The table reports index-build time and mean per-query latency.

Usage:
    python evaluation/run_eval.py                         # default corpus + golden_set.json
    python evaluation/run_eval.py --backends bm25 vector hybrid
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
  Optional fields (provenance for human review; not consumed by the metrics):
    "kind": "verbatim" | "paraphrase"  -- paraphrase questions deliberately avoid
         the corpus wording. They exist because a golden set the baseline already
         tops out on cannot tell two backends apart; the slice breakdown is where
         the difference shows.
    "anchor"                           -- why the expected source is what it is.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# When run directly (python evaluation/run_eval.py), prepend the repo root to
# sys.path so `import ragdemo` works; under pytest/make eval this is a no-op.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ragdemo.chunker import load_corpus
from ragdemo.config import BASE_DIR, CORPUS_PROFILES
from ragdemo.retriever import Backend, build_index

DEFAULT_GOLDEN = Path(__file__).parent / "golden_set.json"


def expected_sources_of(case: dict) -> list[str]:
    """Accept both single-source (`expected_source`) and any-of (`expected_sources`)."""
    if "expected_sources" in case:
        return list(case["expected_sources"])
    return [case["expected_source"]]


@dataclass
class CaseResult:
    """Per-question result for one backend."""

    question: str
    kind: str                       # verbatim | paraphrase (or whatever the set declares)
    expected_sources: list[str]
    recall_at_5: bool
    top1_source: str | None
    first_expected_rank: int | None   # 1-based; None = not in the top-5


@dataclass
class BackendReport:
    """One backend's scorecard, quality and cost side by side."""

    name: str
    cases: list[CaseResult] = field(default_factory=list)
    index_build_seconds: float = 0.0
    query_seconds: float = 0.0      # total across all queries

    @property
    def recall_at_5(self) -> str:
        hits = sum(1 for c in self.cases if c.recall_at_5)
        return f"{hits}/{len(self.cases)}"

    @property
    def top1(self) -> str:
        hits = sum(1 for c in self.cases if c.first_expected_rank == 1)
        return f"{hits}/{len(self.cases)}"

    @property
    def mrr(self) -> str:
        total = sum(1.0 / c.first_expected_rank for c in self.cases if c.first_expected_rank)
        return f"{total / len(self.cases):.3f}" if self.cases else "n/a"

    def slice_recall(self, kind: str) -> str:
        cases = [c for c in self.cases if c.kind == kind]
        if not cases:
            return "n/a"
        hits = sum(1 for c in cases if c.recall_at_5)
        return f"{hits}/{len(cases)}"

    def slice_top1(self, kind: str) -> str:
        cases = [c for c in self.cases if c.kind == kind]
        if not cases:
            return "n/a"
        hits = sum(1 for c in cases if c.first_expected_rank == 1)
        return f"{hits}/{len(cases)}"


def evaluate_backend(name: str, chunks: list, cases: list[dict]) -> BackendReport:
    """Build one backend over the corpus, run every case against it, and keep
    the cost numbers alongside the quality numbers."""
    report = BackendReport(name=name)

    start = time.perf_counter()
    index: Backend = build_index(chunks, name)
    report.index_build_seconds = time.perf_counter() - start

    for case in cases:
        expected = expected_sources_of(case)
        start = time.perf_counter()
        hits = index.search(case["question"], top_k=5)
        report.query_seconds += time.perf_counter() - start

        hit_sources = [h.chunk.source for h in hits]
        rank = next((i for i, s in enumerate(hit_sources, 1) if s in expected), None)
        report.cases.append(
            CaseResult(
                question=case["question"],
                kind=case.get("kind", "verbatim"),
                expected_sources=expected,
                recall_at_5=rank is not None,
                top1_source=hit_sources[0] if hit_sources else None,
                first_expected_rank=rank,
            )
        )
    return report


def run(corpus_dir: Path, golden: Path, backends: list[str] | None = None) -> dict[str, BackendReport]:
    """Evaluate one or more backends; keyed by backend name."""
    chunks = load_corpus(corpus_dir)
    cases = json.loads(golden.read_text(encoding="utf-8"))
    backends = backends or ["bm25"]
    return {name: evaluate_backend(name, chunks, cases) for name in backends}


def _print_detail(report: BackendReport) -> None:
    for case in report.cases:
        mark = "PASS" if case.recall_at_5 else "MISS"
        t1 = "OK" if case.first_expected_rank == 1 else (f"r{case.first_expected_rank}" if case.first_expected_rank else "--")
        print(f"[{mark}][top1 {t1}] {case.question}")
        print(f"        expect={case.expected_sources}  ->  top1={case.top1_source}")


def _print_table(reports: dict[str, BackendReport], n_cases: int) -> None:
    print("\n=== Comparison (same corpus, same golden set) ===\n")
    header = (
        f"{'backend':<10} {'recall@5':>9} {'top1':>9} {'MRR':>7} "
        f"{'paraphr@5':>10} {'paraphr-top1':>13} {'build s':>8} {'ms/query':>9}"
    )
    print(header)
    print("-" * len(header))
    for name, report in reports.items():
        per_query = (report.query_seconds / n_cases * 1000) if n_cases else 0.0
        print(
            f"{name:<10} {report.recall_at_5:>9} {report.top1:>9} {report.mrr:>7} "
            f"{report.slice_recall('paraphrase'):>10} {report.slice_top1('paraphrase'):>13} "
            f"{report.index_build_seconds:>8.2f} {per_query:>9.1f}"
        )


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
    parser.add_argument(
        "--backends", nargs="+", default=["bm25"],
        help="Backends to compare: bm25 vector hybrid (default: bm25)",
    )
    parser.add_argument("--detail", action="store_true", help="Print per-question results")
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
    print(f"Golden: {golden}")
    print(f"Backends: {args.backends}\n")

    reports = run(corpus_dir, golden, backends=args.backends)
    for name, report in reports.items():
        print(f"\n--- {name} ---")
        if args.detail:
            _print_detail(report)

    _print_table(reports, len(next(iter(reports.values())).cases))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
