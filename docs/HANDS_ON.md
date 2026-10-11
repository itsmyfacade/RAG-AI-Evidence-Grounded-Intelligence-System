# AEGIS hands-on verification (10–15 minutes)

These exercises are local-first. They do not call Gemini, Bedrock, or change
AWS resources. Run from the repository root with the existing virtualenv.

## 1. ETL and SQLite correlation (3 minutes)

```powershell
.\.venv\Scripts\python.exe generate_data.py
.\.venv\Scripts\python.exe -c "from src.sql_tools import OperationalEvidenceStore; from src.settings import get_settings; s=OperationalEvidenceStore(get_settings().database_path); print(s.scenario_evidence('SCN-005')[0]); print(s.webhook_evidence('SCN-005')[0])"
```

This proves deterministic generation, linked records, and read-only parameterized
correlation across API logs and webhook evidence.

Interview question: Why keep raw logs in SQLite? Model answer: logs are
high-cardinality structured data best filtered and joined by time, status, and
request ID; only curated narrative evidence belongs in the vector index.

## 2. RAG retrieval and evidence identity (3 minutes)

```powershell
.\.venv\Scripts\python.exe -m src.rag
.\.venv\Scripts\python.exe -m src.retrieval_eval
```

This proves Chroma indexing and the evaluation harness. If the local embedding
model is unavailable, record that blocker rather than inventing metrics.

Interview question: What does Recall@k measure? Model answer: the fraction of
known relevant documents retrieved in the top k; it does not prove that the
generated answer is correct.

## 3. LangGraph routing (3 minutes)

```powershell
$env:AEGIS_LLM = "local"
.\.venv\Scripts\python.exe -c "from src.agents import run_investigation; r=run_investigation('Investigate duplicate webhook events in SCN-005','SCN-005'); print(r['report'].status); print([(x.step,x.status) for x in r['report'].agent_trace])"
```

This proves supervisor, document research, SQL analysis, synthesis, verification,
and bounded conditional routing. SCN-018 demonstrates insufficient evidence and
SCN-019 demonstrates escalation.

Interview question: Which graph behavior is deterministic? Model answer: citation
identity, evidence registry resolution, retry limits, and routing guards are
deterministic; synthesis may be provider-generated when Gemini or Bedrock is
explicitly selected.

## 4. FastAPI and frontend (3 minutes)

```powershell
.\.venv\Scripts\python.exe -m uvicorn src.api:app --reload
```

Open `http://127.0.0.1:8000/`, `/demo/`, `/ready`, and `/docs`. The UI exposes
all 20 allowlisted scenarios, report status, provider, evidence, gaps,
contradictions, and the sanitized trace.

Interview question: What is safe to expose in a public trace? Model answer:
step names, statuses, bounded counts, and sanitized details—not prompts,
credentials, stack traces, or raw private documents.

## 5. Boto3 and Bedrock boundary (2 minutes)

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_foundation.py -q --basetemp=.pytest_runtime
```

This proves mocked S3 synchronization, configured Nova Micro selection, and
access-denial classification without network calls. A live diagnostic or Gemini
smoke test requires explicit approval and credentials supplied only in the
process environment.

Interview question: Why is Bedrock not the default? Model answer: model access,
quota, region, and cost are account-dependent; local mode keeps the public sample
reproducible and never silently substitutes providers.
