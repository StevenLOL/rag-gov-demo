# v1 image: lightweight starting point; v2 will add an ollama service container orchestrated by compose
FROM python:3.12-slim

WORKDIR /app

# Install dependencies before copying code to maximize layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ragdemo/ ragdemo/
COPY api/ api/
COPY tools/ tools/
COPY data/corpus/ data/corpus/

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
