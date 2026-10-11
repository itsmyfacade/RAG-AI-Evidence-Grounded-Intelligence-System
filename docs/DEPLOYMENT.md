# Deployment preparation

AEGIS is prepared for a small Docker-based FastAPI host such as Render, Railway,
Fly.io, or an equivalent managed container service. The recommended first host
is a low-maintenance Docker web service with HTTPS, a persistent volume, and
environment variables managed by the host. No deployment has been performed
from this repository.

## Local container check

```powershell
docker build -t aegis:local .
docker run --rm -p 8000:8000 -e AEGIS_LLM=local aegis:local
```

Open `http://localhost:8000/` and confirm `/ready` reports `ready: true`.

## Render Free settings (512 MB)

Use the Docker runtime. The default Docker build installs `requirements-lite.txt`
and sets the profile to `lite`; it does not install Sentence Transformers,
PyTorch, Chroma, Boto3, or provider SDKs that are not needed by the public local
demo. Set these environment variables in Render:

```text
AEGIS_DEPLOYMENT_PROFILE=lite
AEGIS_LLM=local
AEGIS_EMBEDDINGS=local
AEGIS_DATASET_PATH=data/documents
AEGIS_DATABASE_PATH=data/aegis.db
AEGIS_VECTOR_STORE_PATH=.
AEGIS_MAX_AGENT_ATTEMPTS=2
AEGIS_DEMO_MAX_CONCURRENCY=1
AEGIS_DEMO_REQUESTS_PER_MINUTE=10
AEGIS_PROVIDER_TIMEOUT_SECONDS=30
AEGIS_MAX_OUTPUT_TOKENS=500
```

Do not set `PORT`; Render supplies it. The container binds to `0.0.0.0`, uses
Render's `PORT`, and starts one Uvicorn worker. Do not set `GEMINI_API_KEY` for
the deterministic public profile.

The hosted retrieval mode is explicitly reported as `lexical`. It loads the
small narrative corpus from JSON, ranks token overlap, and applies metadata
filters without importing ML models or Chroma. This is a real lightweight
retrieval implementation, not a claim of embedding-quality retrieval. Full
Sentence Transformer + Chroma RAG remains available through the standard local
profile and the full `requirements.txt` installation.

## Required host settings

- Start command is already defined in `Dockerfile`.
- Health check: `GET /ready`.
- Set `AEGIS_LLM=local` for deterministic public sample mode. Gemini can be
  enabled only when its secret is stored in the host secret manager.
- The deterministic SQLite dataset is generated automatically during container
  startup if it is missing. Without a persistent volume, SQLite is recreated on
  restart, which is acceptable for this synthetic demo. A persistent volume is
  needed only if hosted data is later allowed to become mutable.
- Keep concurrency, request length, and per-process investigation quotas at
  their configured defaults until load testing is complete.

## Provider and cost boundary

The public sample mode does not require Gemini or Bedrock. A Gemini deployment
requires `GEMINI_API_KEY` and explicit `AEGIS_LLM=gemini`; it should be quota
limited and monitored. Bedrock requires an AWS execution role, supported
region/model access, and separately authorized live verification. This repo does
not provision resources, change IAM, or claim successful Bedrock inference.

## Memory and cold starts

The lite image avoids the known memory-heavy request path: Sentence Transformer
model loading, PyTorch initialization, and Chroma client/telemetry initialization.
The 512 MB Render target has not been measured on Render from this repository;
local process memory and provider cold-start behavior are environment-specific.
If standard local RAG is enabled on a 512 MB instance, memory exhaustion remains
expected and is outside the supported hosted profile.
