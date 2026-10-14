# rag-gov-demo developer quick commands
# Usage: make <target>   (works under Git Bash on Windows)

.PHONY: run run-legacy test eval eval-legacy eval-hybrid eval-json eval-json-legacy ui monitor mcp mcp-demo clean

# Start the API (dev mode with auto-reload)
run:
	uvicorn api.main:app --reload --port 8000

# Same as above, but the knowledge base mounts the larger real-world corpus
# (37 docs / 1052 chunks; not shipped in this repo — mount your own at data/corpus_legacy)
run-legacy:
	CORPUS_PROFILE=legacy uvicorn api.main:app --reload --port 8000

# Start the MCP server (stdio, for connecting any MCP client)
mcp:
	python mcp_server.py

# Scripted demo of the four-act governance storyline (no MCP client needed, good for a live walkthrough)
mcp-demo:
	python mcp_server.py --selftest

# Start the demo UI (requires `make run` first)
ui:
	streamlit run ui/streamlit_app.py

# Run the full test suite (including governance schema tests; v3 cases marked skip)
test:
	python -m pytest tests/ -v

# Run the retrieval quality evaluation (governance teaching corpus + golden_set.json)
eval:
	python evaluation/run_eval.py

# Run evaluation on the larger real-world corpus (37 docs / 1052 chunks, not shipped here; BM25 baseline)
# Measured (2026-09-30): recall@5 = 29/31, top1 = 23/31
eval-legacy:
	python evaluation/run_eval.py --corpus-profile legacy --golden evaluation/golden_set_legacy.json

# Same as above, but with the BM25 ⊕ vector (RRF fusion) backend — used to contrast "inherent lexical retrieval flaws"
# Measured (2026-09-30): recall@5 = 31/31, top1 = 26/31
eval-hybrid:
	RETRIEVAL_BACKEND=hybrid python evaluation/run_eval.py \
		--corpus-profile legacy --golden evaluation/golden_set_legacy.json

# Write the evaluation result as JSON — the machine-readable baseline the monitoring
# dashboard reads. Without this the dashboard has nothing to compare against and
# reports "not measured" rather than inventing a number.
# Re-measured 2026-10-13 (this corpus, 63 golden cases): bm25 recall@5 = 59/63, top1 = 39/63, MRR 0.735
eval-json:
	python evaluation/run_eval.py --json _out/eval_baseline.json

# Same for the 37-document scale corpus. Takes ~5 minutes because the fused backend
# spends 282s building the index — that cost is part of the finding, not a nuisance.
# Re-measured 2026-10-13: bm25 29/31 / top1 23/31 · hybrid 31/31 / top1 26/31, MRR 0.899
eval-json-legacy:
	python evaluation/run_eval.py --corpus-profile legacy --golden evaluation/golden_set_legacy.json \
		--backends bm25 hybrid --json _out/eval_baseline_legacy.json

# Monitoring dashboard (read-only view over /audit + the JSON baseline above).
# Requires the API to be running (make run) and streamlit installed locally —
# deliberately NOT in requirements.txt: CI does not run the UI.
monitor:
	streamlit run ui/monitoring_dashboard.py

# Clean up runtime artifacts
clean:
	rm -f data/audit/*.jsonl
	rm -rf .pytest_cache __pycache__ ragdemo/__pycache__
