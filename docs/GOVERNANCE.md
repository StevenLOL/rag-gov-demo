# GOVERNANCE.md

Governance documentation in the format of the **IMDA Model AI Governance
Framework for Agentic AI** (January 2026, updated May 2026): Agent Identity
Card + autonomy-level (L0–L4) statement. This repository *adopts* the format;
it is not affiliated with IMDA.

## 1. Agent Identity Cards

### Card 1 — Primary agent (rag-gov-demo assistant)

| Field | Value |
|---|---|
| Purpose | Question answering and report drafting over a **local corpus** |
| Permission boundary | Only the 5 tools declared in `tools/scopes.yaml`; data classes `internal` and below only |
| Data classification | Sensitive corpus is reasoned over locally; no outbound calls (aligned with `data/corpus/gov_ai_usage_rules.md`) |
| Accountability | Operator: the deployer; Deployer: the demo environment |
| Autonomy level | **L2** — the agent proposes actions; high-risk executions require human approval |

### Card 2 — Tool agent (MCP tool-lookup, read-only)

| Field | Value |
|---|---|
| Purpose | Look up technical component metadata over MCP |
| Permission boundary | Read-only tool scope |
| Autonomy level | L2 (inherits the primary agent's approval flow) |

## 2. Autonomy-level statement

This system operates at **L2**: every tool action marked `risk: high`
(e.g. `export_report`, `delete_record`, `call_cloud_llm`) is forcibly
suspended via LangGraph `interrupt()` before execution and requires a human
decision — approve / reject / edit / respond.

Preconditions for moving to L3 (not met, tracked as future work):
permission-violation tests green for 30 consecutive days, plus audit
spot-checks showing zero unauthorized executions.

## 3. NIST AI RMF function mapping

| Function | Implementation in this demo | Code |
|---|---|---|
| Govern | Agent Identity Card + L2 statement | this file + `agents/graph.py` |
| Map | Four data classes + per-corpus classification labels | `data/corpus/gov_ai_usage_rules.md` + `data_class` in `tools/scopes.yaml` |
| Measure | Permission-violation tests + interrupt/resume consistency + golden-set eval | `tests/test_governance.py` + `evaluation/` |
| Manage | Audit log (who / when / what was approved / rejection reason) | `ragdemo/audit.py` |

## 4. References

- IMDA Model AI Governance Framework for Agentic AI (Jan 2026; updated May 2026) — Agent Identity Cards, L0–L4 levels
- NIST AI RMF 1.0 (Jan 2023) + Generative AI Profile NIST AI 600-1 (Jul 2024)
