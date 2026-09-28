# rag-gov-demo 开发快捷命令
# 用法：make <target>   （Windows Git Bash 下可用）

.PHONY: run test eval ui mcp mcp-demo clean

# 启动 API（开发模式，自动重载）
run:
	uvicorn api.main:app --reload --port 8000

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

# 跑检索质量评估（golden set，报 recall@5）
eval:
	python evaluation/run_eval.py

# 清理运行时产物
clean:
	rm -f data/audit/*.jsonl
	rm -rf .pytest_cache __pycache__ ragdemo/__pycache__
