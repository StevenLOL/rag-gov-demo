# rag-gov-demo

[![CI](https://github.com/StevenLOL/rag-gov-demo/actions/workflows/ci.yml/badge.svg)](https://github.com/StevenLOL/rag-gov-demo/actions/workflows/ci.yml)

A **governance-first agentic RAG reference implementation**:
every answer carries citations, the system refuses to answer when it can't,
high-risk tool actions require human approval, every step is audited,
and every permission is declared.

## Why this exists

Most RAG demos stop at "retrieval works". Mature platforms — Dify, RAGFlow,
enterprise knowledge bases — ship solid traditional access control for
*documents* (who can log in, who can read what). What is consistently missing
is governance at the level of **agent actions**: should this tool call run at
all, who approves it, where is the audit trail?

This repository implements that missing layer as runnable, testable code —
not as a slide deck.

| Layer | What it shows | Status |
|---|---|---|
| v1 — Trusted retrieval | Citations + refusal (dual-gate), one command to run | ✅ Shipped |
| v2 — Delivery maturity | Streamlit UI, FAISS/RRF hybrid retrieval, Ollama LLM | ✅ Shipped (Postgres pending) |
| v3 — Controllable autonomy | LangGraph `interrupt()` approval, least-privilege scopes, IMDA-style governance docs | ✅ v3a shipped; approval-card UI pending |
| v4b — Delegated authority | Supervisor/worker orchestration where every gate is re-evaluated per worker call | ✅ Shipped |
| v4d — Permission-aware retrieval | Chunks inherit an ACL from their source; retrieval pre-filters by principal before ranking | ✅ Shipped |
| v4c — Resilience | Bounded retry with exponential backoff, and an explicit retryable / never-retryable taxonomy | ✅ Shipped |

## The three gates

The governed MCP server (`mcp_server.py`, hand-written JSON-RPC 2.0 over
stdio, zero SDK dependencies) returns **adjudications, not raw results**:

| Gate | Source | Trigger | Result |
|---|---|---|---|
| Permission gate | `tools/scopes.yaml` | Tool not in allow-list | `blocked_unauthorized` (no approval offered) |
| Authorization gate | `tools/asset_policy.yaml` | Use exceeds license (e.g. shipping reference-only assets) | `blocked_by_policy` (no approval offered) |
| Risk gate | `risk: high` in tool declaration | High-risk action | `awaiting_approval` + `thread_id` |

**The authorization gate runs *before* the approval gate on purpose.**
An approver does not know what the license file says; "approved" does not
mean "licensed". This ordering is asserted by
`tests/test_mcp_server.py::test_policy_gate_blocks_before_approval`.

### Two-phase commit for human-in-the-loop over a stateless protocol

```jsonc
// Phase 1: the call is suspended
{"name":"extract_game_assets","arguments":{"package":"tome-1.7.6-gfx","use":"reference"}}
→ {"status":"awaiting_approval","thread_id":"8d517188","payload":{...}}

// Phase 2: same call, plus the operator's decision
{"name":"extract_game_assets","arguments":{...,"_approval":{"thread_id":"8d517188","type":"approve","operator":"demo"}}}
→ {"status":"executed","output":{"written_count":26}}
```

Run the scripted four-act demo (block → suspend → approve → reject) with:

```bash
python mcp_server.py --selftest
```

## Retrieval is an access decision

The three gates govern **agent actions**. They say nothing about **what the
retriever is allowed to return**, so the corpus carries its own permissions
and retrieval filters by principal *before* ranking:

```markdown
---
acl: ["group:sre", "group:security"]
sensitivity: confidential
---
```

- Every chunk inherits the declaration of the document it was cut from; there
  is no per-chunk override, so a chunk cannot end up more readable than its
  source.
- Two conditions, both required: the principal appears in the allow-list, and
  the chunk's sensitivity sits at or below the principal's clearance ceiling.
  An empty allow-list denies everybody — "unclassified" is not "public".
- Pre-filtering, not post-filtering: a denied chunk never consumes a top-k
  slot, so it cannot push an authorised passage out of the result. One test
  asserts this directly, because "it wasn't returned" is also true of
  post-filtering, which quietly destroys recall.
- The audit stream records **how many** chunks were withheld, never which.

Refusals caused by the filter are worded exactly like "nothing matched" —
otherwise the refusal itself becomes an existence oracle for restricted
material. `docs/RAI.md` lists what this does *not* cover (no authentication,
and the dense path filters before truncation rather than before scoring).

## Retry is an allow-list, not a while-loop

A warm local model occasionally hiccups, and one more attempt is often enough.
But retrying the *wrong* failure is worse than not retrying: re-asking a
deterministic "no" records one decision as several in the audit log.

| Failure | Retried | Why |
|---|---|---|
| connection refused / timeout | yes | transient by nature |
| HTTP 429, 5xx | yes | server-side or rate-limit pressure |
| HTTP 4xx (bad request, model not found) | **no** | the same request fails identically |
| malformed response body | **no** | retrying cannot change the shape |
| a policy denial | **no** | it is a decision, not a failure |
| anything unrecognised | **no** | never amplify an unknown fault |

Bounded twice: `max_attempts` caps how many times we ask, `max_total_wait`
caps how long the caller waits — when the next backoff would exceed the
remaining budget the retry is abandoned *before* sleeping. Every scheduled
retry and every exhaustion lands in the audit stream; a healthy call produces
exactly one request and zero events.

## Quick start

Python 3.12, no cloud dependencies:

```bash
pip install -r requirements.txt
python -m pytest -q                    # 61 passed, 0 skipped
uvicorn api.main:app --reload          # or: make run
# → http://localhost:8000/docs  (POST /ask)
```

Without a local LLM the API automatically degrades to **extractive citation
mode** (returns quoted passages with sources) — the demo always runs.

Optional local LLM via any Ollama-compatible endpoint
(`OLLAMA_URL`, auto model discovery, warmup, `think=false` for reasoning
models — measured >60s → ~1.7s per answer on a 3B model).

## Corpus and evaluation

The default corpus (`data/corpus/`, five short governance documents) is in
**Chinese** — deliberately. The retriever implements bilingual tokenization
(Latin words + CJK unigrams/bigrams), and Chinese text is the hard case for
lexical search. All code, comments, API surface and docs are in English.

| Backend | recall@5 | top1 | Notes |
|---|---|---|---|
| BM25 (default) | 20/20 | 19/20 | zero-dependency, Okapi k1=1.5 b=0.75 |
| vector (FAISS) | 20/20 | 20/20 | `intfloat/multilingual-e5-small`, normalized IP = cosine |
| hybrid (RRF) | 20/20 | 19/20 | RRF k=60, rank-based fusion |

At 15 chunks all backends are saturated, so these numbers demonstrate a
**working, switchable evaluation pipeline**, not a superiority claim.

### Scale experiment (BM25 vs hybrid on ~1k chunks)

On a much larger private corpus (37 documents / 1052 chunks of legacy-system
reverse-engineering notes, kept out of the repository — data, not code),
the same pipeline shows real separation, with a root-caused failure mode:

| Backend | recall@5 | top1 |
|---|---|---|
| BM25 | 29/31 | 23/31 |
| hybrid | **31/31** | **26/31** |

Diagnosed cause (verified at token level, not guessed): BM25's tf saturation
caps a single rare anchor term at ~4–7 points, while generic high-frequency
terms accumulate freely; character-bigram tokenization also produces
cross-word pseudo-terms whose IDF is the highest in the corpus. Vector/semantic
fusion closes exactly this gap. This is why the retrieval layer here is a
**teaching implementation**: in production you would select a mature retrieval
engine, and spend the engineering budget on the governance layer that no
off-the-shelf product provides.

```bash
make eval            # default corpus + golden_set.json (reproducible from a fresh clone)
```

## Governance

- Per-tool least privilege: `tools/scopes.yaml` (declarative scopes + risk levels + data classes)
- High-risk actions: LangGraph `interrupt()` with approve/reject/edit/respond decisions
- Governance behavior tests run in CI: `tests/test_governance.py`
- Documents: [docs/GOVERNANCE.md](docs/GOVERNANCE.md) (IMDA MGF-Agentic style Agent
  Identity Card + L0–L4 autonomy statement) and [docs/RAI.md](docs/RAI.md) (honest limitations list)

## Project layout

```
mcp_server.py        governed MCP server (JSON-RPC 2.0, three gates, two-phase commit)
agents/graph.py      LangGraph orchestration: interrupt/approval routing
ragdemo/             retrieval, citation, refusal, audit, policy, assets, LLM client
api/main.py          FastAPI surface (/ask, /health, /audit)
ui/                  Streamlit demo UI
tools/*.yaml         permission scopes + asset license policy
evaluation/          golden sets + eval runner (recall@5, top1)
tests/               61 tests incl. governance behavior + cross-process state persistence
data/corpus/         default demo corpus (Chinese, 5 docs / 15 chunks)
```

## Roadmap

- [ ] v2: Postgres session store; Docker compose verified end-to-end
- [ ] v3b: Streamlit approval card (approve/reject/edit/respond)
- [ ] v3c: Postgres checkpointer replacing in-memory saver; signed audit records
