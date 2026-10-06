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

## Known limitations (honest list)

- Without a connected LLM, answers are extractive (quoted passages with
  citations); there is no generative fluency.
- Retrieval comparisons are corpus-bound: at 15 chunks all three backends
  saturate (recall@5 20/20; top1 19/20, 20/20, 19/20), so no backend
  superiority can be claimed from the default corpus alone. A larger-corpus
  experiment with a root-caused failure mode is described in the README.
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
