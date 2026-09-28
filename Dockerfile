# v1 镜像：轻量起步；v2 将加入 ollama 服务容器由 compose 编排
FROM python:3.12-slim

WORKDIR /app

# 先装依赖再拷代码，最大化层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ragdemo/ ragdemo/
COPY api/ api/
COPY tools/ tools/
COPY data/corpus/ data/corpus/

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
