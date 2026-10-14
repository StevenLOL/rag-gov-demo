---
acl: ["*"]
sensitivity: internal
---

# Agent 治理基础

## 人在回路（Human-in-the-loop）

高风险动作（删除数据、外发报告、资金操作）在执行前必须暂停并获得人工批准。
批准决定分为四类：approve（批准）、reject（拒绝）、edit（修改参数后批准）、respond（补充信息）。
每次批准或拒绝都应记录：操作人、时间、动作内容、参数快照。

## 最小权限（Least-privilege）

每个 agent 与每个工具只应获得完成其任务所必需的最小权限。
权限以声明式白名单表达：工具名、权限范围（scope）、风险等级（low/high）。
越权调用必须被运行时拒绝，并在测试中覆盖（越权测试进 CI）。

## 自治级别（Autonomy levels L0-L4）

- L0：仅人工操作，agent 只提供建议。
- L1：agent 起草，人工逐字确认。
- L2：agent 建议动作，执行前需人工批准（本 demo 目标级别）。
- L3：agent 在授权范围内自主执行，事后审计。
- L4：agent 完全自治，仅限非敏感、可回滚场景。
