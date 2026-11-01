# QA automation

AEGIS uses layered offline checks so API contracts, application behavior, and the
static workbench are validated separately.

## Local commands

```powershell
$env:AEGIS_DEPLOYMENT_PROFILE="lite"
$env:AEGIS_LLM="local"
$env:AEGIS_EMBEDDINGS="local"
python -m pytest tests -q
python -m pytest tests/test_api_contract.py -q
python -m ruff check .
node --check frontend/app.js
npm audit --audit-level=high
npm ci
npx playwright install chromium
npm run test:e2e
```

The blocking Python audit targets `requirements.txt`, the secure
lite-compatible CI/development set. The Render/Docker lite image uses the
smaller `requirements-lite.txt`. Standard local vector retrieval is installed
separately with `requirements-standard.txt`:

```powershell
python -m pip install -r requirements-standard.txt
$env:AEGIS_DEPLOYMENT_PROFILE="standard"
python -m pytest tests/test_rag.py -q
```

The API contract tests use HTTPX with FastAPI's ASGI application. They validate
health, readiness, samples, the static demo, request validation, and a completed
SCN-005 response without calling Bedrock, Gemini, or other external providers.
Playwright starts a local hosted-lite Uvicorn server and uses Chromium for real
browser interactions. Its trace, screenshot, and HTML report outputs are local
artifacts and are uploaded by CI only when the browser job runs.

## CI quality gates

GitHub Actions runs on every push and pull request on the explicitly pinned
Ubuntu 24.04 runner. The official checkout, Python, Node, and artifact actions
are configured for the Node 24 action runtime; the npm/Playwright job separately
installs and uses Node 24. The Python job compiles the
application, runs the full offline pytest suite, checks Ruff, validates frontend
JavaScript syntax, and runs `pip check` plus a blocking `pip-audit` against the
lite-compatible manifest. A separate Chromium job
installs the lite runtime, starts the local server through Playwright's
`webServer`, and runs the end-to-end suite. Browser reports, screenshots, and
traces are retained as workflow artifacts when available.

The separately named `standard-profile-security-report` job installs the
optional standard dependencies, runs the Chroma regression tests, and uploads
the complete standard-profile `pip-audit` output. Its audit is informational
only because current ChromaDB advisories have no reported fixed version; the
job visibly warns and records the nonzero audit result rather than suppressing
it. A successful lite gate does not certify standard semantic-RAG security.

A failed Python gate indicates a source, contract, regression, or dependency
problem. A failed browser gate should first be classified as server startup,
locator/interaction, responsive layout, or browser-environment failure. The
workflow does not invoke paid inference or use the public Render service.

## Regression example

The API contract test verifies that SCN-005 returns `provider=local`,
`retrieval_mode=lexical`, five ordered trace stages, and citations that resolve
to returned evidence IDs. This prevents a hosted-lite change from silently
claiming a different provider or emitting ungrounded citation references.

## Deployment boundary

GitHub Actions is continuous integration and quality gating only. Render remains
the separately managed deployment boundary described in
[`DEPLOYMENT.md`](DEPLOYMENT.md); this repository does not configure a Render
deployment to wait for Actions and does not deploy from the workflow.
