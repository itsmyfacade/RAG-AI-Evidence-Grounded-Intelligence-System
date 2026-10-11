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

## Required host settings

- Start command is already defined in `Dockerfile`.
- Health check: `GET /ready`.
- Set `AEGIS_LLM=local` for deterministic public sample mode. Gemini can be
  enabled only when its secret is stored in the host secret manager.
- Mount persistent storage for `AEGIS_DATABASE_PATH` and
  `AEGIS_VECTOR_STORE_PATH` if the host supports it. Without a volume, SQLite
  and Chroma are recreated when the container restarts.
- Keep concurrency, request length, and per-process investigation quotas at
  their configured defaults until load testing is complete.

## Provider and cost boundary

The public sample mode does not require Gemini or Bedrock. A Gemini deployment
requires `GEMINI_API_KEY` and explicit `AEGIS_LLM=gemini`; it should be quota
limited and monitored. Bedrock requires an AWS execution role, supported
region/model access, and separately authorized live verification. This repo does
not provision resources, change IAM, or claim successful Bedrock inference.

## Persistence and cold starts

The image includes deterministic dataset generation, but the local Sentence
Transformer model may be downloaded during first embedding initialization unless
the image build environment pre-caches it. For a reliable public demo, use a
build cache or bake the approved embedding model into the image, then verify
startup memory and cold-start duration on the selected host. Chroma and SQLite
are suitable for a small demo, not a horizontally scaled production service.
