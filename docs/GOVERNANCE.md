# GOVERNANCE.md —— 治理文档（v3 目标形态，先立结构）

> 产物格式采用 **IMDA Model AI Governance Framework for Agentic AI**（2026-01 全球首发，2026-05 更新）
> 的官方格式：Agent Identity Card + 自治分级（L0–L4）声明。
> 采用（而非参与制定）——诚实红线见 singapore/docs/066 §7。

## 1. Agent Identity Card × 2（v3 完成时填写）

### 卡 1：主 agent（rag-gov-demo assistant）

| 字段 | 内容（v3 填写） |
|---|---|
| 用途 | 基于**本地语料**的资料问答与报告起草 |
| 权限边界 | 仅 scopes.yaml 声明的 5 个工具；仅 internal 及以下数据级 |
| 数据分级 | 敏感语料本地推理，禁止外发（对齐 gov_ai_usage_rules.md） |
| 责任方 | operator: 部署者（本人）；deployer: 面试演示环境 |
| 自治级别 | **L2**——agent 建议动作，高风险执行前需人工批准 |

### 卡 2：工具 agent（devmap MCP lookup）

| 字段 | 内容（v3 填写） |
|---|---|
| 用途 | 通过 MCP 查询技术组件图谱（devmap v0.4.1） |
| 权限边界 | devmap:read（只读） |
| 自治级别 | L2（依附主 agent 的审批流） |

## 2. 自治级别声明

本系统运行于 **L2**：所有 risk=high 的工具动作（export_report / delete_record / call_cloud_llm）
在执行前经 LangGraph `interrupt()` 强制挂起，由人工 approve/reject/edit/respond。
升级到 L3 的前置条件：越权测试全绿连续 30 天 + 审计抽查无未授权执行（TODO(v3) 制定细则）。

## 3. NIST AI RMF 四函数映射（v3 完成时逐条指向代码）

| 函数 | 本 demo 的实现 | 代码位置 |
|---|---|---|
| Govern | Agent Identity Card + L2 声明 | 本文件 + agents/graph.py |
| Map | 数据分级四类 + 语料分级标注 | data/corpus/gov_ai_usage_rules.md + scopes.yaml data_class |
| Measure | 越权测试 + interrupt-resume 一致性 + golden set eval | tests/test_governance.py + evaluation/ |
| Manage | 审计日志（谁/何时/批了什么/拒绝理由）+ 回滚（v3） | ragdemo/audit.py |

## 4. 引用

- IMDA MGF-Agentic（2026-01 / 2026-05 更新）：官方 Agent Identity Cards、L0–L4 分级
- NIST AI RMF 1.0（2023-01）+ GenAI Profile AI 600-1（2024-07）
- MDDI 国会答复（2026-05-07）：公共部门 AI 问责规则
