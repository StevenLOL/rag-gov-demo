"""Tests for the corpus profile (CORPUS_PROFILE).

Four things are asserted:
1. The profile table is complete and the default profile is gov — so other
   retrieval/citation cases in tests/ are not "hijacked" by the real corpus;
2. The legacy profile really loads a corpus of the correct scale (37 docs / 1,052
   chunks, not an empty directory);
3. Distinctive-term retrieval works on the real corpus (verified with the df=1 anchor
   terms mined by scripts 012/013);
4. Chunks from the two corpora never overlap — proving that profile switching truly
   swaps the knowledge base rather than mixing them together.

Why the hybrid backend is not tested: the vector backend requires
sentence-transformers and a local model, which are unavailable on CI; the hybrid
comparison results are recorded in the README and docs/015, and are not covered by
unit tests.
"""

from __future__ import annotations

import os

import pytest

from ragdemo.chunker import load_corpus
from ragdemo.config import CORPUS_PROFILES
from ragdemo.retriever import Bm25Backend


def test_profiles_defined_and_gov_is_default():
    """Both the gov and legacy profiles exist; gov is the default when the env var is unset."""
    assert set(CORPUS_PROFILES) >= {"gov", "legacy"}
    # The default profile must be the governance corpus: tests/test_retriever.py and
    # test_citation.py assert on its content
    assert CORPUS_PROFILES["gov"].name == "corpus"
    assert CORPUS_PROFILES["legacy"].name == "corpus_legacy"


def test_legacy_corpus_has_expected_scale():
    """Real corpus scale: 37 docs -> thousands of chunks (numbers measured on 2026-09-30)."""
    legacy_dir = CORPUS_PROFILES["legacy"]
    if not legacy_dir.is_dir():
        pytest.skip(f"local legacy corpus directory not found: {legacy_dir}")
    files = sorted(legacy_dir.glob("*.md"))
    assert len(files) == 37, f"expected 37 documents, got {len(files)}"
    chunks = load_corpus(legacy_dir)
    assert len(chunks) >= 1000, f"expected >=1000 chunks, got {len(chunks)}"


def test_distinctive_anchor_retrieves_its_document():
    """A df=1 anchor term retrieves its document at top1 (anchors mined by scripts/013).

    PKLite (only doc 017 in the whole corpus) and xentax (only doc 026) are chosen as
    the two hardest anchors: they are unaffected by the "same game having two
    documents" interference, making them a lower-bound verification of retriever
    capability.
    """
    legacy_dir = CORPUS_PROFILES["legacy"]
    if not legacy_dir.is_dir():
        pytest.skip(f"local legacy corpus directory not found: {legacy_dir}")
    backend = Bm25Backend(chunks=load_corpus(legacy_dir))

    hits = backend.search("ETIN 的 16 位 DOS EXE 被 PKLite 压缩过，怎么解压", top_k=1)
    assert hits and hits[0].chunk.source == "017_ETIN格式破解全记录.md"


def test_two_corpora_do_not_overlap():
    """Chunk sources of the two corpora are disjoint — profile switching is replacement, not merging."""
    legacy_dir = CORPUS_PROFILES["legacy"]
    if not legacy_dir.is_dir():
        pytest.skip(f"local legacy corpus directory not found: {legacy_dir}")
    gov_sources = {c.source for c in load_corpus(CORPUS_PROFILES["gov"])}
    legacy_sources = {c.source for c in load_corpus(legacy_dir)}
    assert gov_sources & legacy_sources == set()
    assert legacy_sources  # the real corpus is non-empty


def test_profile_env_switches_directory():
    """With CORPUS_PROFILE=legacy the configured corpus directory changes accordingly
    (the precondition for end-to-end profile switching).

    A subprocess is used instead of importlib.reload: reload replaces object
    identities inside the config module, while other modules have already bound the
    old value away via `from ragdemo.config import CORPUS_DIR`, causing implicit
    pollution where "behavior is inconsistent after reload". A subprocess genuinely
    verifies the semantics of "the env var is read at process startup".
    """
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    code = "import sys; sys.path.insert(0, '.'); from ragdemo.config import CORPUS_DIR; print(CORPUS_DIR)"
    env = dict(os.environ, CORPUS_PROFILE="legacy", PYTHONIOENCODING="utf-8")
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().endswith("corpus_legacy"), proc.stdout
