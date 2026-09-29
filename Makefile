# rag-gov-demo 开发快捷命令
# 用法：make <target>   （Windows Git Bash 下可用）

.PHONY: run run-legacy test eval eval-legacy eval-hybrid ui mcp mcp-demo clean

# 启动 API（开发模式，自动重载）
run:
	uvicorn api.main:app --reload --port 8000

# 同上，但知识库挂真实 dosgames 逆向语料（37 篇 / 1052 chunk）
run-legacy:
	CORPUS_PROFILE=legacy uvicorn api.main:app --reload --port 8000

# 启动 MCP server（stdio，供任意 MCP 客户端连接）
mcp:
	python mcp_server.py

# 四段治理剧情脚本化演示（无需 MCP 客户端，面试演示用）
mcp-demo:
	python mcp_server.py --selftest

# 启动演示 UI（需先 make run）
ui:
	streamlit run ui/streamlit_app.py

# 跑全部测试（含治理 schema 测试；v3 用例标记 skip）
test:
	python -m pytest tests/ -v

# 跑检索质量评估（治理教学语料 + golden_set.json）
eval:
	python evaluation/run_eval.py

# 跑真实语料评估：37 篇 dosgames 逆向文档 / 1052 chunk（BM25 基线）
# 实测（2026-09-30）：recall@5 = 29/31，top1 = 23/31
eval-legacy:
	python evaluation/run_eval.py --corpus-profile legacy --golden evaluation/golden_set_legacy.json

# 同上，但换成 BM25 ⊕ 向量（RRF 融合）后端——用于对照"词法检索的固有缺陷"
# 实测（2026-09-30）：recall@5 = 31/31，top1 = 26/31
eval-hybrid:
	RETRIEVAL_BACKEND=hybrid python evaluation/run_eval.py \
		--corpus-profile legacy --golden evaluation/golden_set_legacy.json

# 清理运行时产物
clean:
	rm -f data/audit/*.jsonl
	rm -rf .pytest_cache __pycache__ ragdemo/__pycache__
