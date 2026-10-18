FROM python:3.12-slim

ARG AEGIS_DEPLOYMENT_PROFILE=lite

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AEGIS_LLM=local \
    AEGIS_EMBEDDINGS=local \
    AEGIS_DEPLOYMENT_PROFILE=${AEGIS_DEPLOYMENT_PROFILE}

WORKDIR /app
COPY requirements.txt requirements-lite.txt .
RUN if [ "$AEGIS_DEPLOYMENT_PROFILE" = "lite" ]; then pip install --no-cache-dir -r requirements-lite.txt; else pip install --no-cache-dir -r requirements.txt; fi
COPY . .
RUN python generate_data.py

EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn src.api:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
