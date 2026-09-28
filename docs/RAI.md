# RAI.md —— Responsible AI 节（v2 完成时充实）

## 声明

本 demo 的 RAI 实践不是装饰，是可运行代码：

1. **诚实边界**：答不出就拒答（覆盖率 + 分数双闸），拒绝编造——见 `ragdemo/citation.py`。
2. **数据不出域**：主路径本地推理，零公有云依赖——`docker-compose.yml` 可验证。
3. **留痕**：每次问答（含拒答）落审计 JSONL——`ragdemo/audit.py`。
4. **最小权限**：每工具声明式 scope + 风险分级——`tools/scopes.yaml`。
5. **可测**：治理行为进 CI——`tests/test_governance.py`。

## 与既有资产的映射（v2 充实）

- J511 / CISP 认证知识 → 本文件的措辞与控制项选择
- SQLCipher / edge_v 密码研究 → "静态数据加密"节的素材来源
- ISO 21434 参与经历 → 生命周期安全思维的对应描述

## 已知局限（诚实清单）

- v1 未接 LLM 时为抽取式答案，无生成流畅性可言；
- BM25 对长问题召回有限（golden set 当前 6 题，v2 扩 20 题并引入本地 embedding）；
- 审计为单机 JSONL，v3 迁移 Postgres 并加签名防篡改（TODO）。
