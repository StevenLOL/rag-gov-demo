# rag-gov-demo

[![CI](https://github.com/StevenLOL/rag-gov-demo/actions/workflows/ci.yml/badge.svg)](https://github.com/StevenLOL/rag-gov-demo/actions/workflows/ci.yml)

> **治理优先（governance-first）的 agentic RAG 参考实现**——答案必带出处、答不出明说、
> 高风险动作必须经人批准、每一步留审计、每份权限有声明。
>
> 仓库：<https://github.com/StevenLOL/rag-gov-demo>（公开）

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

**环境用 conda（本机主力环境），不要另建 venv：**

```bash
conda activate ragdemo
python -m pytest -q          # 59 passed
uvicorn api.main:app --reload          # 或者 make run
# 打开 http://localhost:8000/docs 试 POST /ask
```

### `ragdemo` 是怎么来的（2026-09-30）

用 conda 的 `--clone` 从 `py312` 复制而来，**目的只有一个：零下载地拿到 torch**。

```
conda create -n ragdemo --clone py312    # ← 会失败，见下
```

⚠️ **本机 safe-delete shim 会拦 conda clone**：
conda 在收尾时清理 50 个临时文件，触发
`[safe-delete][SAFE_DELETE_BULK_CONFIRM_REQUIRED] {"count":50,"threshold":50}` 而失败，
留下 57,082 个文件的残骸（conda env list 里不认它）。

**绕过办法（已验证，19 秒完成）**：不做删除，直接用 robocopy 从 py312 补齐缺失文件：

```bash
MSYS_NO_PATHCONV=1 robocopy \
  "E:\Users\Administrator\miniconda3\envs\py312" \
  "E:\Users\Administrator\miniconda3\envs\ragdemo" /E /R:1 /W:1
# 结果：62,304 文件 / 6.77 GB / 19s（5,227 新复制，57,077 已存在）
```

<br>

> **环境约定（2026-09-29 用户明确要求）**：一律用 **conda**，环境名 `ragdemo`。
> 之前用过 `~/.workbuddy/binaries/python/envs/default` 这个托管 venv——
> 它不在 conda 管理范围内、路径又长，已弃用；脚本与文档中的硬编码路径已清除。
>
> **`ragdemo` 自带的能力**（继承自 py312，无需再装任何东西）：
> Python 3.12.13 / torch 2.7.1+cu128（**CUDA 可用**）/ transformers 5.17.0 /
> sentence-transformers 6.1.0 / faiss-cpu 1.15.1 / langgraph / fastapi / pytest / Pillow。
> 全量测试 **59 passed，0 skipped**（含向量检索与语料档位用例；2026-09-30 更新）。

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

### 实测对比 A（治理语料：5 篇 / 15 chunk / 20 题）

| 后端 | recall@5 | top1 |
|---|---|---|
| bm25 | 20/20 | **19/20** |
| vector | 20/20 | **20/20** |
| hybrid（RRF） | 20/20 | 19/20 |

诚实解读：语料仅 15 个片段，三后端都已饱和——这组数字证明的是**工程管道打通**（后端可切换、指标可复跑），
**不是"混合检索更强"**。

### 实测对比 B（真实逆向语料：37 篇 / 1052 chunk / 31 题，2026-09-30）

上一节我写过"语料扩到千级片段后对比才有分辨力——这是后续扩充方向"。**这一步已经做完了**，
语料换成 dosgames 的 37 篇真实逆向文档（1052 chunk），结果立刻有了分辨力：

| 后端 | recall@5 | top1 |
|---|---|---|
| bm25 | 29/31（93.5%） | 23/31（74.2%） |
| **hybrid（RRF）** | **31/31（100%）** | **26/31（83.9%）** |

```bash
make eval-legacy    # BM25 基线
make eval-hybrid    # BM25 ⊕ 向量（RRF）
```

**两道 BM25 漏掉的是什么，以及为什么**（`scripts/014_检索失败根因诊断.py` 取证，不猜）：

- 题面"DQ3 的 SHP 格式逆向探查结论"，top1 落在 `022_三国英雄` 的**「十二、参考文档」**片段——
  实测该文档里 `dq3` / `shp` 出现次数**均为 0**；
- 根因不是 bug，是**词法检索的固有缺陷**：BM25 的 tf 饱和 + 长度归一化下，
  一个 df=1 的稀有锚点词**最多只能贡献约 4–7 分**，敌不过"格式/图形/结论"这类通用词的累加；
- 再叠加 CJK 按字符切二元组，会产出 `查结`（"探查|结论"）、`形格`（"图形|格式"）这类
  **跨词边界的伪词**，它们 IDF 最高（6.9+），反而主导排序。

向量/混合后端正是补这个洞：语义相似不依赖字面共现。
**这也是"检索层为什么定位成教学实现"的量化依据**——见下一节。

## 检索层的定位：教学实现，不是产品级检索（重要）

**结论先说**：本仓库的 BM25 / 向量 / 混合检索是**教学实现（teaching implementation）**，
不是要拿去跟 RAGFlow、ElasticSearch 抢饭碗的东西。这么做是**故意的**，理由可量化。

### 为什么自己写了一遍，以及为什么不继续投入

| 项 | 数据 | 出处 |
|---|---|---|
| 本仓库检索相关代码 | 493 行（占全仓 1838 行的 27%） | `C:/src/RAG_LLM_agents/docs/014` |
| 元景万悟开源的企业知识库 `rag_open_source` | **25,566 行 / 98 文件** | 同上，已 clone 实证 |
| 比值 | **1.9%** | — |

自己写一遍的价值是**把接口与失败模式摸清楚**（所以才有了上面"伪词 IDF 主导排序"这种一手发现）；
但要把它做成产品级检索，等于用 1.9% 的投入去追 100% 的工程量——**不划算，也不是本仓库的主张**。

### 选型结论（可直接用于 COTS 评估）

> 生产环境选 RAGFlow / 成熟向量库做检索层；
> **治理层（权限闸 / 授权闸 / 风险闸 / 审计）没有现成开源件可用，才是本仓库的自建重点。**

依据：已实证元景万悟有**完整的企业级 IAM**（`iam-service`：全局角色 / 组织 / OAuth 应用 / 验证码），
但**全仓 `interrupt` 唯一命中是 `know_doc_parsing_interrupted`（文档解析中断，与 agent 动作审批无关，伪命中）**——
即：**传统治理（谁能登录、谁能看文档）是成熟的；agent 动作级治理（这个动作该不该让它执行）是空白的**。
这是第 4 次在同构项目上观察到同一结论。

## 语料档位（CORPUS_PROFILE）

同一套代码挂不同知识库，靠环境变量切换，API / UI / MCP 全链路生效：

| 档位 | 语料 | 规模 | 用途 |
|---|---|---|---|
| `gov`（默认） | `data/corpus` 治理教学语料 | 5 篇 / 15 chunk | 单元测试与 CI 依赖它，**不要改默认** |
| `legacy` | `data/corpus_legacy` dosgames 真实逆向文档 | 37 篇 / 1052 chunk | 演示与压测 |

```bash
CORPUS_PROFILE=legacy uvicorn api.main:app     # 或 make run-legacy
```

为什么用档位而不是直接换默认目录：`tests/test_retriever.py`、`test_citation.py`
断言的是治理语料的具体内容，默认目录一换这些用例全部失效。档位化让两套语料**并存且不互相破坏**
（由 `tests/test_corpus_profile.py` 断言：两套语料 chunk 来源交集为空）。

`legacy` 档位的 golden set 不是拍脑袋写的：先用 `scripts/012` 量化锚点歧义
（结论：`RLE` 出现在 24/38 篇、`调色板` 29 篇——拿它们出题 recall@5 必然虚高），
再用 `scripts/013` 逐篇挖 df=1 的区分性术语，最后每题都在 golden set 里留了 `anchor` 字段做证据。

## 组件与数据边界

- 本地闭环：FastAPI + 本地 LLM(Ollama 类) + 本地 embedding/检索 + Postgres（v2/v3）+ 审计日志
- 唯一远端必需：GitHub（托管 + Actions CI）——**2026-09-30 起这句话才真正成立**：
  此前仓库只有本地 git、没有 remote，CI 从未触发过。现已推送并跑绿（含 eval smoke），
  首次真跑还暴露了一个依赖缺失：`requirements.txt` 漏了 Pillow，
  导致 15 个治理用例在 CI 上 ERROR（本机 conda 自带 Pillow 掩盖了它），已修。
- 远端 LLM API 仅作对照实验与演示兜底；**明确不用** Pinecone 云 / LangSmith
- 完整组件表见 `docs/069` 同名文档（singapore 工作区）

## 治理（v3 目标形态）

- 每工具最小权限：`tools/scopes.yaml`（格式致敬 opencode/claude code permission config）
- 高风险动作：LangGraph `interrupt()` 强制人工批准（approve/reject/edit/respond 四决策）
- 越权测试进 CI：`tests/test_governance.py`
- 治理文档：`docs/GOVERNANCE.md`（IMDA MGF-Agentic 格式 Agent Identity Card + L0–L4 自治声明）

## v3b：受治理的 MCP server（零依赖手写）

`mcp_server.py` 是一个**手写**的 MCP stdio 服务端（JSON-RPC 2.0，无任何 SDK 依赖），
协议契约与 `C:/src/devinfo/devmap/src/mcp.ts`（269 行实证）一致：`initialize` /
`tools/list` / `tools/call` / `notifications/*` 无响应 / `-32601`。只声明 `tools`
能力——不吹 resources/prompts。

**与普通 MCP server 的唯一区别：它返回的不是执行结果，而是治理裁决。**

| 闸 | 数据源 | 触发条件 | 返回 |
|---|---|---|---|
| 权限闸 | `tools/scopes.yaml` | 工具不在白名单 | `blocked_unauthorized`（不给审批机会） |
| 授权闸 | `tools/asset_policy.yaml` | 用途超出授权（如把仅供参考的素材用于 ship） | `blocked_by_policy`（同样不给审批机会） |
| 风险闸 | `risk: high` | 高风险动作 | `awaiting_approval` + `thread_id` |

两阶段提交（把 HITL 塞进无状态协议）：

```jsonc
// 阶段一
{"name":"extract_game_assets","arguments":{"package":"tome-1.7.6-gfx","out_dir":"_out/ref","use":"reference"}}
→ {"status":"awaiting_approval","thread_id":"8d517188","payload":{...}}
// 阶段二
{"name":"extract_game_assets","arguments":{...,"_approval":{"thread_id":"8d517188","type":"approve","operator":"demo"}}}
→ {"status":"executed","output":{"written_count":26}}
```

**为什么授权闸要排在审批闸之前**：审批人并不比策略更懂 `COPYING-MEDIA` 写了什么，
"批准了"不等于"合法"。授权拒绝必须发生在挂起之前——由
`tests/test_assets.py::test_license_gate_blocks_denied_use` 与
`tests/test_mcp_server.py::test_policy_gate_blocks_before_approval` 断言。

### 真实素材实测（2026-09-29，`scripts/010` 取证，证据在 `_evidence/real_asset_scan.json`）

- 素材包：`tome-1.7.6-gfx.team`，**292.2 MB / 21161 张 PNG**，只读扫描 **0.67s**
- 授权：`TE4-COPYING-MEDIA` → 仅 `reference` 放行，`ship` / `commercial` 拒绝
- 四段剧情：`use=ship` → blocked；`use=reference` → 挂起；批准 → 落盘 26 张；改判 reject → `_out/never` 不存在

```bash
python mcp_server.py --selftest     # 四段剧情脚本化演示
python mcp_server.py                # stdio 模式，供任意 MCP 客户端连接
```

## 致谢与复用声明（防 NIH）

- 挂起/恢复原语：**LangGraph**（`interrupt()` / `Command`）——我们不重造
- 声明式权限模式：**致敬 opencode / claude code 的 permission config**——移植到企业 RAG 场景并补审计与数据分级
- 工具协议：**MCP**（devmap v0.4.1 作为首个工具源；本仓库的 server 为同契约手写实现）
- 素材抽取口径：**`C:/src/games/scripts/03`、`12` 号脚本**（分类关键词、分层抽样、保留 alpha）
  ——复用的是「怎么抽图」，自建的是「抽图这个动作怎么被治理」

## Roadmap

- [x] v1 骨架：语料/分块/BM25 检索/引用/拒答/审计 JSONL/CI
- [x] v1 评估：5 份语料 + 20 题 golden set（recall@5 20/20，top1 19/20）
- [x] v3a：LangGraph 治理编排最小可运行（interrupt 审批 / 越权拒绝 / 副作用恰执行一次，行为测试进 CI）
- [x] v2 UI：Streamlit 演示界面（问答/引用/拒答/审计）
- [x] v2 检索：FAISS 向量后端 + RRF 混合检索（依赖可选，缺失自动回退 BM25）
- [x] v1 收尾：Ollama 生成接通实测（模型自动发现/预热/思考型模型 `think=false`，>60s → 1.7s）
- [x] v3b（部分）：受治理 MCP server（手写 JSON-RPC 2.0）+ 三道闸（权限/授权/风险）
      + 游戏美术素材工具接入真实素材包（292MB / 21161 张实证）
- [x] 语料换真实数据：dosgames 37 篇逆向文档（1052 chunk）+ 31 题 golden set，
      BM25 29/31 → hybrid 31/31，根因取证见 `scripts/014`
- [ ] v2：Dockerfile+compose 实测、Postgres 会话库、RAI.md 充实
- [ ] v3b（剩余）：Streamlit 审批卡（approve/reject/edit/respond）+ devmap 工具接入
- [ ] v3c：PostgresSaver 替换 InMemorySaver + 审计表迁移
