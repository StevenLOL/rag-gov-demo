# rag-gov-demo

> **治理优先（governance-first）的 agentic RAG 参考实现**——答案必带出处、答不出明说、
> 高风险动作必须经人批准、每一步留审计、每份权限有声明。

三层洋葱（每层独立可演示，独立 git tag）：

| 层 | 一句话 | 状态 |
|---|---|---|
| v1 可信检索基座 | 引用溯源 + 拒答机制，一条命令起 | ✅ 已落地（5 语料 / 20 题 eval：recall@5 20/20，top1 19/20） |
| v2 交付成熟层 | Docker 三容器 + CI + Postgres + Streamlit UI | 🟡 UI 已落地；容器实测/Postgres 进行中 |
| v3 可控自治层 | LangGraph interrupt 审批 + 最小权限 + IMDA 治理产物 | 🟡 **v3a 已落地**（高风险 interrupt 审批/越权拒绝/副作用恰执行，治理行为测试进 CI）；v3b 审批卡 UI + MCP、v3c Postgres checkpointer 进行中 |

## 为什么是这个定位

市面上 RAG demo 证明"我会调 API"，Dify/RAGFlow 证明"世界已经有产品了"。
本仓库证明的是第三件事：**我知道一个 agent 进企业前还差什么——并且把差的东西做出来了。**
详细论证见singapore 工作区 `docs/067`（详规格）、`docs/068`（复用 vs 自建判定）、`docs/069`（白盒讲解）。

## 快速开始（v1，零云依赖）

```bash
pip install -r requirements.txt
uvicorn api.main:app --reload          # 或者 make run
# 打开 http://localhost:8000/docs 试 POST /ask
```

无本地 LLM 时自动降级为**抽取式引用模式**（直接返回带出处的原文摘录）——demo 永远可跑。

## 本地 LLM（Ollama）——v1 收尾已实测接通

本机实测环境：Ollama 已装 + **granite4.2:3b**（3.7B，Q4_K_M，GTX 1060 6GB）。

| 能力 | 说明 |
|---|---|
| 模型自动发现 | 查 `/api/tags`；配置模型本机没有时自动回退同系列/第一个可用模型（不会傻等超时） |
| 启动预热 | 后台线程 `warmup()`，把模型载入常驻（`keep_alive=10m`） |
| 思考型模型处理 | `think=false` + `num_predict=256`——**实测从 >60s 降到 1.7s** |
| 降级 | 服务不可用/无模型时自动走抽取式引用模式，`/health` 里 `llm_available` 可见 |

```bash
curl -s localhost:8000/health
# {"status":"ok","chunks":15,"retrieval_backend":"bm25",
#  "llm_available":true,"llm_model":"granite4.2:3b"}
```
一键体检（含冷/热耗时与端到端问答）：`python scripts/009_检查Ollama与生成链路.py --api 8128`

## 检索后端（三选一，环境变量 `RETRIEVAL_BACKEND`）

| 后端 | 依赖 | 说明 |
|---|---|---|
| `bm25`（默认） | 零 | 纯 Python BM25，双语分词（拉丁词 + CJK 单字/二元组）；k1=1.5, b=0.75 |
| `vector` | faiss-cpu + sentence-transformers | FAISS `IndexFlatIP`；嵌入 `normalize_embeddings=True` → **内积 = 余弦** |
| `hybrid` | 同上 | BM25 ⊕ 向量，**RRF 融合**（k=60，按排名不看分数）；覆盖率闸仍用 BM25 |

```bash
RETRIEVAL_BACKEND=hybrid uvicorn api.main:app    # 切后端只需改环境变量
```
依赖缺失时自动回退 BM25 并打印提示。向量后端默认模型 `intfloat/multilingual-e5-small`（384 维，中英双语，~470MB）；
国内建议先 `export HF_ENDPOINT=https://hf-mirror.com`。

### 实测对比（20 题 golden set，语料 15 chunk）

| 后端 | recall@5 | top1 |
|---|---|---|
| bm25 | 20/20 | **19/20** |
| vector | 20/20 | **20/20** |
| hybrid（RRF） | 20/20 | 19/20 |

诚实解读：语料仅 15 个片段，三后端都已饱和——这组数字证明的是**工程管道打通**（后端可切换、指标可复跑），
**不是"混合检索更强"**。向量后端补上了 BM25 唯一漏掉的那道 top1；混合检索在小语料上被 BM25 的排名拉回。
语料扩到千级片段后对比才有分辨力——这是后续扩充方向（不夸大当前结论）。

## 组件与数据边界

- 本地闭环：FastAPI + 本地 LLM(Ollama 类) + 本地 embedding/检索 + Postgres（v2/v3）+ 审计日志
- 唯一远端必需：GitHub（托管 + Actions CI）
- 远端 LLM API 仅作对照实验与演示兜底；**明确不用** Pinecone 云 / LangSmith
- 完整组件表见 `docs/069` 同名文档（singapore 工作区）

## 治理（v3 目标形态）

- 每工具最小权限：`tools/scopes.yaml`（格式致敬 opencode/claude code permission config）
- 高风险动作：LangGraph `interrupt()` 强制人工批准（approve/reject/edit/respond 四决策）
- 越权测试进 CI：`tests/test_governance.py`
- 治理文档：`docs/GOVERNANCE.md`（IMDA MGF-Agentic 格式 Agent Identity Card + L0–L4 自治声明）

## 致谢与复用声明（防 NIH）

- 挂起/恢复原语：**LangGraph**（`interrupt()` / `Command`）——我们不重造
- 声明式权限模式：**致敬 opencode / claude code 的 permission config**——移植到企业 RAG 场景并补审计与数据分级
- 工具协议：**MCP**（devmap v0.4.1 作为首个工具源）

## Roadmap

- [x] v1 骨架：语料/分块/BM25 检索/引用/拒答/审计 JSONL/CI
- [x] v1 评估：5 份语料 + 20 题 golden set（recall@5 20/20，top1 19/20）
- [x] v3a：LangGraph 治理编排最小可运行（interrupt 审批 / 越权拒绝 / 副作用恰执行一次，行为测试进 CI）
- [x] v2 UI：Streamlit 演示界面（问答/引用/拒答/审计）
- [x] v2 检索：FAISS 向量后端 + RRF 混合检索（依赖可选，缺失自动回退 BM25）
- [ ] v1 收尾：Ollama 生成接通实测
- [ ] v2：Dockerfile+compose 实测、Postgres 会话库、RAI.md 充实
- [ ] v3b：Streamlit 审批卡（approve/reject/edit/respond）+ devmap MCP 工具接入
- [ ] v3c：PostgresSaver 替换 InMemorySaver + 审计表迁移
