"""Centralized configuration: paths, thresholds, and external service addresses.

Design principles:
1. Everything has a default value -- the code runs right after cloning with no env vars set;
2. The data plane stays "in-domain" by default -- corpus, index, and audit all live in local
   repository directories;
3. Remote services (LLM APIs other than Ollama) are never hardcoded; for v2 comparison
   experiments they are injected via environment variables.
"""

import os
from pathlib import Path

# Repository root (one level above ragdemo/config.py)
BASE_DIR = Path(__file__).resolve().parent.parent

# ---- Data paths (fully local, self-contained) ----
# Corpus profiles: the same code can mount different knowledge bases, switched via
# CORPUS_PROFILE (effective across the whole API / UI / MCP stack).
#   gov    -- governance teaching corpus (data/corpus, 5 docs / 15 chunks): the default profile
#             for unit tests and CI; do not touch;
#   legacy -- real dosgames reverse-engineering docs (data/corpus_legacy, 37 docs / 1052 chunks):
#             the demo and load-testing profile.
# Why profiles instead of simply changing the default directory: the retrieval/citation tests in
# tests/ assert on the governance corpus content; once the default directory becomes legacy,
# those tests would all break -- profiles let the two corpora coexist without breaking each other.
CORPUS_PROFILES: dict[str, Path] = {
    "gov": BASE_DIR / "data" / "corpus",
    "legacy": BASE_DIR / "data" / "corpus_legacy",
}
_DEFAULT_PROFILE = os.getenv("CORPUS_PROFILE", "gov")
CORPUS_DIR = Path(
    os.getenv("CORPUS_DIR", str(CORPUS_PROFILES.get(_DEFAULT_PROFILE, CORPUS_PROFILES["gov"])))
)
AUDIT_LOG = Path(os.getenv("AUDIT_LOG", BASE_DIR / "data" / "audit" / "audit.jsonl"))
# Persistence location of the governance graph checkpointer (SqliteSaver). Thread cursors are
# stored here keyed by thread_id and survive process restarts; STATE_DB=":memory:" falls back
# to an in-memory version (for test isolation).
STATE_DB = Path(os.getenv("STATE_DB", BASE_DIR / "data" / "audit" / "state.db"))

# ---- Refusal decision (two-gate safety net; see citation.py for details) ----
# Coverage: refuse when the fraction of query tokens found in the corpus falls below this value
REFUSAL_COVERAGE = float(os.getenv("REFUSAL_COVERAGE", 0.5))
# Refuse when the BM25 top-1 absolute score falls below this value
RETRIEVAL_MIN_SCORE = float(os.getenv("RETRIEVAL_MIN_SCORE", 2.0))

# ---- Retrieval backend (v2): bm25 (default, zero deps) | vector (FAISS) | hybrid (RRF fusion) ----
RETRIEVAL_BACKEND = os.getenv("RETRIEVAL_BACKEND", "bm25")

# Embedding model (local sentence-transformers; for faster downloads in China, set
# HF_ENDPOINT=https://hf-mirror.com)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "cpu")
# Refusal threshold for the vector backend (normalized inner product = cosine, range -1..1)
VECTOR_MIN_SCORE = float(os.getenv("VECTOR_MIN_SCORE", 0.35))

# ---- Local LLM (Ollama-compatible HTTP API) ----
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
# Generation timeout (seconds): measured locally, granite4.2:3b cold start (2.2GB loaded onto
# the GPU) takes about 34s, so the default is relaxed to 60s and paired with a startup warmup
# -- after warmup, a single generation drops to a few seconds
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", 60))
# Warmup timeout (seconds): only used to load the model into memory at startup, so it may be
# longer
OLLAMA_WARMUP_TIMEOUT = float(os.getenv("OLLAMA_WARMUP_TIMEOUT", 180))
# Model residency (Ollama keep_alive): defaults to 10m so each request does not reload the model
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "10m")
# Max tokens per generation: without a cap, thinking models (e.g. local granite4.2) keep
# generating until timeout
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", 256))
# Whether the model is allowed to "think" (thinking mode): when disabled, the local granite4.2
# drops from >60s to ~1.7s
OLLAMA_THINK = os.getenv("OLLAMA_THINK", "false").lower() == "true"

# ---- Reserved for v2/v3 ----
POSTGRES_DSN = os.getenv("POSTGRES_DSN", "")  # v2: session store + v3: durable checkpointer
