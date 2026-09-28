"""集中配置：路径、阈值、外部服务地址。

设计原则：
1. 全部有默认值——clone 下来不配任何环境变量即可运行；
2. 数据面默认"不出域"——语料、索引、审计全部在仓库本地目录内；
3. 远端服务（Ollama 之外的 LLM API）一律不写死在代码里，v2 对照实验时经环境变量注入。
"""

import os
from pathlib import Path

# 仓库根目录（ragdemo/config.py 的上一级）
BASE_DIR = Path(__file__).resolve().parent.parent

# ---- 数据路径（全部本地闭环）----
CORPUS_DIR = Path(os.getenv("CORPUS_DIR", BASE_DIR / "data" / "corpus"))
AUDIT_LOG = Path(os.getenv("AUDIT_LOG", BASE_DIR / "data" / "audit" / "audit.jsonl"))

# ---- 拒答判定（双保险，见 citation.py 的说明）----
# 覆盖率：查询词元在语料中出现的比例低于该值 → 拒答
REFUSAL_COVERAGE = float(os.getenv("REFUSAL_COVERAGE", 0.5))
# BM25 top1 绝对分数低于该值 → 拒答
RETRIEVAL_MIN_SCORE = float(os.getenv("RETRIEVAL_MIN_SCORE", 2.0))

# ---- 本地 LLM（Ollama 兼容 HTTP API）----
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
# 生成超时（秒）：本地模型首 token 可能慢，但 demo 也不该挂死
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", 30))

# ---- v2/v3 预留 ----
POSTGRES_DSN = os.getenv("POSTGRES_DSN", "")  # v2: 会话库 + v3: durable checkpointer
