# Demo 部署与运维

## 本地部署

系统支持完全离线部署：检索使用本地 BM25 索引，生成使用本地 Ollama 模型，
向量库与审计日志均存储在本地磁盘。全程无需公有云服务。

## Docker 部署

使用 docker compose 一键启动三个容器：app（FastAPI 服务）、
postgres（会话与审计数据库）、inference（本地推理服务）。
启动命令：`docker compose up -d`。

## 监控与审计

每次问答与审批事件写入审计日志，可通过 /audit 端点查询。
审计日志包含时间戳、事件类型、问题内容与处理方式。
