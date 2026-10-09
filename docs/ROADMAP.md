# Roadmap — v4

Next increments for `rag-gov-demo`, in priority order. Each one is scoped
against seams that already exist in the code, so no re-architecture is needed.

Status convention follows the README layer table. Reviewed and re-ordered
2026-10-09; see "Order and rationale" for why the order changed.

| Increment | Theme | Primary files | Depends on | Status |
|---|---|---|---|---|
| **v4b** | Multi-agent orchestration: does authority survive delegation? | `agents/supervisor.py`, reuse `graph.py` gates | none | ✅ shipped |
| **v4d** | Permission-aware retrieval (pre-filter) | `ragdemo/acl.py`, `ragdemo/chunker.py`, `ragdemo/retriever.py`, `ragdemo/citation.py` | none | ✅ shipped |
| **v4c** | Resilience: retry with backoff | `ragdemo/retry.py`, `ragdemo/llm.py` | none | ✅ shipped |
| **v4a** | Pluggable retrieval backends + comparative evaluation | `ragdemo/retriever.py`, `evaluation/` | none (local model optional) | ✅ shipped |

---

## v4b — Multi-agent orchestration (in progress)

### Motivation

Today the graph is a single agent with a tool belt. That is the right place to
start — it keeps the governance hard to misread. But real deployments split work:
a supervisor that decomposes a request, workers that own a narrow slice, results
gathered back. The interesting governance question shows up exactly at that seam:
**when authority is delegated to a sub-agent, which gate travels with it?**

That question is answerable here because the primitives already exist.

### Current seam

`agents/graph.py` already implements, and is already tested for:

- `interrupt()` — suspend a high-risk action pending human decision
- `Command(resume=...)` — resume from persisted state rather than replaying
- `SqliteSaver` checkpointer — the thread cursor survives a process restart
- `scopes.yaml` — least-privilege: a tool outside the whitelist is denied
  outright rather than suspended

v4b reuses all four; it does not re-implement them.

### The answer this repository commits to

**Every gate travels, and every gate is evaluated per worker call.** A worker runs
the permission gate, the authorization gate and the risk gate itself, plus one
gate that only exists because authority was delegated:

- **delegation gate** — a worker may only invoke a tool whose declared scope is a
  subset of what the supervisor granted for that subtask.

The rejected alternative was to grade risk once, at the supervisor boundary, and
let workers inherit the verdict. It is cheaper and looks tidier, and it is wrong:
any high-risk action a worker reaches on its own would bypass the gate entirely.
That is precisely the path by which least-privilege gets silently defeated, so
the tests assert the per-call behaviour directly.

Two consequences worth stating explicitly:

- The supervisor is **not** a gate. It chooses work and hands out the least scope
  each subtask needs; it never decides whether an action is allowed. A planner bug
  therefore cannot become a permission bypass.
- Every audit event carries `principal` (who initiated the request) **and**
  `worker` (which node acted). Without `principal`, an approval can only be
  attributed to "some node in the graph", which is not an audit trail.

### Done when

- [x] Supervisor + workers runnable end to end; results gathered per subtask.
- [x] A test asserts that an unscoped tool call is denied **at the worker**, not
      only at the supervisor (delegation does not widen authority).
- [x] A test asserts that a worker reaching beyond its granted scope is denied
      at the worker and is never offered human approval.
- [x] A test asserts high-risk actions still suspend and still resume exactly
      once when raised from within a worker.
- [x] A test asserts two high-risk subtasks suspend **sequentially** — if the gate
      ran only once at the boundary, the second one would sail through.
- [x] A test asserts audit events carry principal and worker.
- [x] Existing graph tests unchanged and green.

---

## v4d — Permission-aware retrieval (pre-filter)

### Motivation

The three gates govern **agent actions**. They do not govern **what the retriever
is allowed to return**. That gap matters more than it looks:

- Post-filtering — take top-k, then drop what the user may not see — breaks
  recall (if every hit is denied, the answer is empty or invented) and, worse,
  means the unauthorised content has already passed through the candidate set.
- Pre-filtering — narrow the candidate space by permission first, then rank by
  similarity — is the correct shape for regulated data. Unauthorised content is
  never returned, so it never reaches the model or the audit log.

Retrieval is an access decision, not a presentation concern.

### Work items

1. Carry `acl` / `sensitivity` metadata on `Chunk`, inherited from the source
   document at ingestion.
2. Resolve a principal (identity, groups, clearance ceiling) before retrieval.
3. Pre-filter candidates by that principal, then rank; refuse rather than
   degrade when nothing survives the filter.
4. Assert by test that a query from an unauthorised principal never returns the
   chunk, **and that the denied chunk does not appear in the audit log**.
5. Record the boundary in `docs/RAI.md`: what is enforced, and what is not yet.

### Design decisions actually taken

- **The corpus declares its own ACL.** Each document carries a YAML
  front-matter block (`acl`, `sensitivity`); every chunk cut from it inherits
  that declaration unconditionally — there is no per-chunk override, so a chunk
  cannot end up more readable than its source document. The block is stripped
  at ingestion, so it never becomes retrievable text or embedding input.
- **Two independent conditions, both required**: group/user membership in the
  allow-list, *and* the chunk's sensitivity sitting at or below the principal's
  clearance ceiling. An empty allow-list denies everybody — "unclassified" is
  not a synonym for "public".
- **`principal=None` means "do not filter"**, deliberately: the raw backend
  stays usable for whole-corpus evaluation runs. Every path that serves an end
  user resolves a principal first (the configured least-privileged default), so
  an unfiltered query is an explicit choice rather than an oversight.
- **The audit stream records the *count* of filtered-out chunks, never their
  identifiers.** Logging what was withheld would turn the audit file into a
  second, less-protected copy of the restricted corpus.
- **A refusal caused by the filter is worded exactly like "nothing matched".**
  Otherwise the refusal becomes an existence oracle for restricted material.

### Done when

- [x] Chunks carry permission metadata; the corpus declares it.
- [x] Retrieval accepts a principal and pre-filters before ranking.
- [x] Tests assert non-return **and** non-appearance in the audit stream.
- [x] `docs/RAI.md` states the current boundary honestly.

### One existing assertion changed on purpose

`tests/test_governance.py::test_side_effect_executes_exactly_once_after_resume`
used to assert the audit file had exactly two lines. The retrieval layer now
writes its own `retrieval` event into the same stream, so the assertion counts
`tool_executed` events instead. That is the point of the increment: one stream,
so "the denied chunk never appears in the audit log" is a checkable statement
rather than a claim.

---

## v4c — Resilience: retry with backoff

### Motivation

The layer is mostly there already, which is easy to miss:

- `ragdemo/llm.py` sets three separate timeouts — a short `_PROBE_TIMEOUT` for
  availability probing, `OLLAMA_WARMUP_TIMEOUT` for cold start (a first request
  measures ~34 s), and `OLLAMA_TIMEOUT` for generation.
- Failures degrade rather than fail: the module docstring records that
  "failures/timeouts raise exceptions, and `citation.py` degrades to
  extractive".
- `api/main.py` exposes `GET /health` returning corpus size, active retrieval
  backend, and LLM availability.

What is **not** there is retry. A transient failure on a warm local model
currently goes straight to extractive fallback even when one more attempt would
have succeeded. That is the gap worth closing — nothing else in this layer.

### Work items

1. Add bounded retry with exponential backoff around the generation call.
2. Keep it **bounded**: cap attempts, cap total wait, never retry on a
   deterministic refusal (a policy denial must not be retried — it is not
   transient, and retrying it would make the audit log dishonest).
3. Classify failure modes explicitly: retried (connection failure, timeout,
   5xx) versus never retried (4xx, policy denial, schema validation). Document
   the table and assert it.
4. Every retry and every exhaustion must be observable: land it in the same
   audit stream the rest of the system already writes to.

### Design decisions actually taken

- **The taxonomy is the deliverable, not the loop.** Retrying is easy; deciding
  what may be retried is the engineering. The rule is *transient by allow-list,
  deterministic by default*: anything not explicitly known to be transient is
  not retried, so an unrecognised fault is never amplified.
- **A policy denial is never retried, and there is a type for it.**
  `ragdemo/retry.py` defines `PolicyRefusal(NonRetryable)`. A denial is a
  *decision*; re-asking would record one decision as several in the audit log,
  which is indistinguishable from "the system kept trying until it got through".
- **Bounded twice.** `max_attempts` bounds how many times we ask;
  `max_total_wait` bounds how long the caller waits. A cap on attempts alone is
  not a cap on latency — when the next backoff would exceed the remaining
  budget the retry is abandoned *before* sleeping, so the caller never waits
  past the budget.
- **Only the HTTP call is retried.** Resolving the model is not: a service with
  no model will not grow one in the next 500 ms.
- **No failure means no trace.** With a healthy call there is exactly one
  request and zero audit events — asserted, so the happy path cannot silently
  start retrying.

### Done when

- [x] Retry is bounded, backoff is exponential, and both are configurable.
- [x] Deterministic refusals are never retried (asserted by test).
- [x] Retry attempts and exhaustions appear in the audit stream.
- [x] Existing behaviour with no failures is unchanged.

---

## v4a — Pluggable retrieval backends and a comparison

### Motivation

Retrieval is currently a single hand-written BM25 implementation. That is a
deliberate property of this repository (`mcp_server.py` is hand-written too), and
it should stay that way: the governance story is easier to audit when the moving
parts are few and readable.

But "we wrote it ourselves" is not the same question as "should we have". An
engineering team choosing a retrieval stack needs the comparison, not the claim.

### ⚠️ Blocker: the golden set is saturated

The existing baseline on `evaluation/golden_set.json` (20 questions) is
**recall@5 = 20/20**. A comparison run against a set where the baseline already
scores 100% has no headroom — the best possible result is "all three get 20/20",
which proves nothing except that the experiment was under-designed.

**This must be fixed before any comparison is run**: extend or harden the golden
set until BM25 demonstrably misses some questions. Do the comparison after, not
before.

### Compare retrieval layers, not orchestration frameworks

The candidates worth putting on the comparison table are retrieval options:

| Option | What it is | Why it is on the table |
|---|---|---|
| Hand-written BM25 (current) | zero-dependency lexical retrieval | the baseline |
| FAISS / pgvector | dense vector retrieval | semantic recall; pgvector can filter and rank inside one query |
| Cross-encoder reranking | a precision stage | most production precision gain comes from the reranker, not the fusion |
| Elasticsearch / OpenSearch kNN | BM25 + vectors + native RRF in one engine | the common "add no new datastore" answer |

Orchestration frameworks are deliberately **not** on this list: they are not
retrieval implementations, so comparing them here would measure framework
wrapping rather than retrieval quality. Orchestration is covered by v4b.

### Current seam

`ragdemo/retriever.py` already defines the extension point:

```python
class Backend(Protocol):      # the contract any implementation satisfies
class Bm25Backend:            # current default
def build_index(chunks, backend=None) -> Backend   # factory / selector
```

So v4a is: implement more classes against the existing `Protocol`, register them
in the factory, and let `RETRIEVAL_BACKEND` select between them. Nothing else
changes.

### Work items

1. **Fix the golden set first** (see the blocker above).
2. **Add the dependency first, not last.** Put any new dependency in
   `requirements.txt` **before** writing code against it. This repository has
   twice been bitten by the same class of bug — a locally rich environment hides
   a missing dependency that then fails selection on CI (see the CI-note comments
   beside `Pillow` and `langgraph-checkpoint-sqlite`).
3. Implement each new backend satisfying `Backend`.
4. Register them in `build_index(backend=...)`; keep BM25 as the default so
   existing behaviour is unchanged.
5. **Evaluation, not benchmarking theatre.** Report `recall@5` and `top1` side by
   side, with the BM25 baseline visible in the same table.
6. Write down what each option actually costs — added dependencies, index build
   time, cold-start behaviour, and whether permission filtering happens inside
   the engine. A backend that retrieves marginally better but adds 200 MB and
   4 seconds of cold start has not obviously won.

### Design decisions actually taken

- **The blocker was real and the hardening worked.** 43 paraphrase questions
  were added to the 20 verbatim ones (each carrying an `anchor` justifying its
  expected source, so the golden set stays reviewable). BM25 dropped from a
  meaningless 20/20 to 59/63 recall@5, 39/63 top1, MRR 0.735 — every miss is a
  paraphrase, which is precisely the failure mode lexical search is expected to
  have.
- **No new dependency was needed** — the vector and hybrid backends already
  existed behind the `Backend` protocol. v4a therefore became: harden the eval,
  extend the runner (MRR + cost columns + slice breakdown), and test the
  contract every backend must honour.
- **A backend contract is a test suite, not a convention.**
  `tests/test_backend_contract.py` runs the same assertions against every
  backend `build_index` can return: `principal` is accepted (the permission
  filter is part of the protocol), results are ranked/capped/deterministic,
  `coverage()` exists for the refusal gate, and the dense backends hide but
  never displace visible chunks.
- **One behaviour change: an unknown backend name now raises.** Previously a
  typo in `RETRIEVAL_BACKEND` silently served BM25 — a configuration bug that
  looks exactly like the intended configuration.
- **The comparison surfaced an honest finding:** all three backends miss
  `断网了还能不能继续用`. Reported in the README instead of dropping the question.

### Done when

- [x] Golden set hardened; BM25 baseline no longer saturated.
- [x] Backends selectable via `RETRIEVAL_BACKEND` with no code change.
- [x] BM25 remains the default; `/health` still reports the active backend.
- [x] A comparison table exists with recall@5 / top1 plus the cost columns.
- [x] New tests cover each new backend's contract compliance.
- [x] Full suite still green (see "Local test command" below).

---

## Local test command

```bash
cd C:/src/RAG_LLM_agents/demo
<python> -m pytest tests/ -q -p no:cacheprovider --basetemp=./.pytest_tmp
```

Both flags are required on this workstation: the default cache/temp location
triggers a bulk temp-directory cleanup that the sandbox blocks, and the run
aborts **after** the tests have already passed. Moving the temp root inside the
repository avoids it. This is an environment constraint, not a test defect — CI
is unaffected.

Retrieval baseline (last measured: `recall@5 = 20/20`, `top1 = 19/20`):

```bash
<python> evaluation/run_eval.py
```

**Gate for every increment: the suite must stay at 69 passed or better — additions
only, never a net decrease.**

---

## Order and rationale

**v4b first.** It has the highest differentiation and the lowest risk: no new
dependency, no CI surface, and it answers a question the ecosystem mostly
hand-waves ("authority survives delegation"). Cheap to revert, expensive to skip.

**v4d second.** It closes the one gap a reviewer is most likely to find: the gates
govern actions but not retrieval. Small, self-contained, and it is the difference
between "we added access control" and "retrieval is an access decision".

**v4c third.** Smallest in scope now that timeouts, degradation and `/health`
already exist; only retry is genuinely missing.

**v4a last**, reversing the previous order. Two reasons: it is the only increment
that adds a dependency and therefore touches CI, and its prerequisite — a golden
set with headroom — does not exist yet. Both are cheap to fix, but neither should
be discovered mid-increment.

---

## Risks

| Risk | Mitigation |
|---|---|
| A new dependency fails selection on CI in a clean environment | Add to `requirements.txt` first; confirm CI green before writing code against it |
| Adding a heavyweight dependency dilutes the "readable, hand-written" property | Additive and selectable only — BM25 stays the default, no existing path is replaced |
| Dependency weight and cold-start cost get ignored in favour of accuracy numbers | Require the cost columns in the v4a comparison table |
| The comparison is run against a saturated golden set and proves nothing | Harden the golden set first; treat it as a v4a blocker |
| Delegated authority silently widens in a multi-agent graph | Delegation gate plus tests asserting worker-level denial and per-call suspension (v4b) |
| Retrieval returns content the caller may not see | Pre-filter, not post-filter; assert absence from the audit log (v4d) |
| Retry masks a deterministic refusal | Never retry refusals; classify them; assert it; log it |
