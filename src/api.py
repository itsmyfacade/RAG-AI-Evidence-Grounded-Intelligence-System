"""FastAPI boundary with safe errors, readiness, and demo safeguards."""

from __future__ import annotations

import threading
import time
from contextlib import asynccontextmanager
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from src.agents import run_investigation
from src.schemas import InvestigationRequest, InvestigationResponse
from src.settings import (
    get_settings,
)
from src.startup import diagnostics
from src.startup import ensure_resources
from src.sql_tools import OperationalEvidenceStore
from src.scenario_catalog import public_question


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_resources()
    yield


app = FastAPI(title="AEGIS", description="AI Evidence-Grounded Intelligence System", version="1.0.0", lifespan=lifespan)
_slots = threading.BoundedSemaphore(get_settings().demo_max_concurrency)
_rate_lock = threading.Lock()
_rate_history: dict[str, deque[float]] = defaultdict(deque)


@app.get("/health")
def health():
    return {"status": "ok", "service": "AEGIS"}


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/demo/")


@app.get("/ready")
def ready():
    result = diagnostics()
    result["status"] = "ready" if result["ready"] else "degraded"
    return result


@app.get("/samples")
def samples():
    database_path = get_settings().database_path
    if database_path.exists():
        return [
            {**item, "question": public_question(item["scenario_id"])}
            for item in OperationalEvidenceStore(database_path).scenario_options()
        ]
    return []


@app.post("/investigate", response_model=InvestigationResponse)
def investigate(request: InvestigationRequest, http_request: Request = None):
    if http_request is not None:
        client_key = http_request.client.host if http_request.client else "unknown"
        now = time.monotonic()
        with _rate_lock:
            history = _rate_history[client_key]
            while history and now - history[0] >= 60:
                history.popleft()
            if len(history) >= get_settings().demo_requests_per_minute:
                raise HTTPException(status_code=429, detail="Demo request quota reached")
            history.append(now)
    if not _slots.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="Investigation concurrency limit reached")
    try:
        result = run_investigation(request.question, request.scenario_id)
        report = result["report"]
        return InvestigationResponse(
            investigation_id=result["investigation_id"], question=request.question,
            status=report.status, answer=result["answer"], citations=result.get("citations", []),
            mode=result.get("mode", "local"), report=report, agent_trace=result.get("trace", []),
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Investigation service unavailable") from exc
    finally:
        _slots.release()


frontend = Path(__file__).resolve().parents[1] / "frontend"
if frontend.exists():
    app.mount("/demo", StaticFiles(directory=frontend, html=True), name="demo")
