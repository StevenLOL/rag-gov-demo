# RAI.md — Responsible AI notes

## What is actually implemented (not decoration)

1. **Honest boundaries** — the system refuses to answer when it can't
   (dual gate: token-coverage check + minimum retrieval score), instead of
   fabricating. See `ragdemo/citation.py`.
2. **Data stays local** — the primary path runs local inference with zero
   public-cloud dependencies; verifiable from `docker-compose.yml`.
3. **Traceability** — every Q&A (including refusals) lands in an audit JSONL
   file. See `ragdemo/audit.py`.
4. **Least privilege** — declarative per-tool scopes with risk levels and
   data classes. See `tools/scopes.yaml`.
5. **Testable governance** — governance behavior is asserted in CI.
   See `tests/test_governance.py`.
6. **Bounded, audited retry** — transient failures are retried with exponential
   backoff; deterministic ones (4xx, malformed body, policy denial) never are,
   because re-asking a "no" would misrepresent it in the audit log. See
   `ragdemo/retry.py` and `tests/test_retry.py`.
7. **Permission-aware retrieval** — chunks inherit an ACL from their source
   document, retrieval takes a principal, and candidates are filtered *before*
   ranking, so unauthorised content never reaches the model. See
   `ragdemo/acl.py` and `tests/test_acl.py`.

## Permission-aware retrieval: what is enforced, and what is not

**Enforced** (asserted by `tests/test_acl.py`):

- A chunk the principal may not read is never returned.
- The filter runs before the top-k cut, so denied chunks do not consume
  retrieval slots — a denied chunk that is the best lexical match does not
  push an authorised chunk out of the result.
- Denied chunks do not appear in the audit stream; only the **count** of what
  was withheld is logged.
- A refusal caused by the filter is indistinguishable from "nothing matched".

**Not enforced** — read these before treating the filter as a security boundary:

- **Nobody is authenticated.** A `Principal` is declared by the caller; wiring
  it to a real identity provider is out of scope. What is demonstrated is the
  enforcement shape, not the identity plumbing.
- **The dense path filters before truncation, not before scoring.** `IndexFlatIP`
  is an exact brute-force index, so widening the fetch costs nothing and the
  filter can run before the top-k cut; a denied chunk still has a dot product
  computed for it. An approximate index (IVF/HNSW) cannot do even this, and a
  production deployment needs a filtered ANN index — for example pgvector
  filtering inside the same SQL query.
- **This is application-layer filtering, not storage-layer row security.** A
  bug in the retrieval path, or any code path that reads the corpus directly,
  bypasses it entirely.
- **The refusal gate can leak existence indirectly.** BM25 token coverage is
  computed over the whole corpus vocabulary, not over the authorised subset, so
  a query whose only matches are restricted can still report a high coverage
  figure. Existence disclosure through this channel is not currently closed.

### Retry: what is enforced, and what is not

**Enforced**: attempts are capped, total wait is capped, backoff is exponential
and per-delay capped, and only allow-listed transient failures are retried.

**Not enforced**:

- **Retry does not make a flaky model reliable** — it converts one class of
  transient failure into an occasional success and no more. A model that
  times out consistently will still exhaust the budget and degrade.
- **The retry is per-call, not per-request.** A request that fans out to several
  generations can spend the budget several times over.
- **No circuit breaker.** Repeated exhaustion does not stop the system from
  calling a dead endpoint on the next request; the `/health` probe is
  availability information, not a breaker.

## Known limitations (honest list)

- Without a connected LLM, answers are extractive (quoted passages with
  citations); there is no generative fluency.
- Retrieval comparisons are corpus-bound: at 15 chunks the quality differences
  are a few questions wide, so no backend superiority can be claimed from the
  default corpus alone. The golden set is now two-slice (verbatim + paraphrase)
  to give the comparison headroom, and the paraphrase slice is reported
  separately; a larger-corpus experiment with a root-caused failure mode is
  described in the README. The paraphrase questions are hand-written and
  single-annotator: their `expected_source` labels are justified by an `anchor`
  note per question, but no second annotator has checked them.
- Audit is a single-machine JSONL file; hardening (signature, Postgres
  migration) is tracked as future work.
- **Asset classification uses keyword substring matching, not semantic
  understanding**, and has reproducible false positives observed on a real
  package: a "trees" category matched `cloak_inv.png` because the keyword
  `oak` is a substring of `cloak`; a "characters" category matched thousands
  of equipment layer images under `shockbolt/player/**` rather than actual
  NPC portraits. Keyword hits are **leads, not semantics**. The demo
  therefore positions classification as *sampling leads for human review*
  (it produces contact sheets for a person to inspect), never as an
  automatic ingest decision — the human review step is not optional.
- The authorization gate checks whether the *declared use* is within the
  license allow-list; it does not verify whether any individual file in a
  package actually originates from the licensed source. That is beyond this
  demo's forensic scope.
