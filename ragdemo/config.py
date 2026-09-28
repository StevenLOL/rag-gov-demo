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

# ---- 检索后端（v2）：bm25（默认，零依赖）| vector（FAISS）| hybrid（RRF 融合）----
RETRIEVAL_BACKEND = os.getenv("RETRIEVAL_BACKEND", "bm25")

# 嵌入模型（本地 sentence-transformers；国内下载建议 HF_ENDPOINT=https://hf-mirror.com）
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "cpu")
# 向量模式的拒答阈值（归一化后内积 = 余弦，范围 -1~1）
VECTOR_MIN_SCORE = float(os.getenv("VECTOR_MIN_SCORE", 0.35))

# ---- 本地 LLM（Ollama 兼容 HTTP API）----
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
# 生成超时（秒）：本机实测 granite4.2:3b 冷启动（2.2GB 载入 GPU）约 34s，
# 因此默认放宽到 60s 并配合启动预热——预热后单次生成降到数秒
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", 60))
# 预热超时（秒）：仅用于启动时把模型载入常驻，允许更久
OLLAMA_WARMUP_TIMEOUT = float(os.getenv("OLLAMA_WARMUP_TIMEOUT", 180))
# 模型常驻时长（Ollama keep_alive）：默认 10m，避免每次请求重新载入
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "10m")
# 单次生成最大 token 数：不设上限时思考型模型（如本机 granite4.2）会一直生成到超时
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", 256))
# 是否允许模型"思考"（thinking 模式）：关闭后本机的 granite4.2 从 >60s 降到 ~1.7s
OLLAMA_THINK = os.getenv("OLLAMA_THINK", "false").lower() == "true"

# ---- v2/v3 预留 ----
POSTGRES_DSN = os.getenv("POSTGRES_DSN", "")  # v2: 会话库 + v3: durable checkpointer
