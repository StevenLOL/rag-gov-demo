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
