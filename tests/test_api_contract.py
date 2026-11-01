"""HTTP contract coverage for the deterministic hosted-lite API boundary."""

import asyncio

import httpx

from src.api import app


async def _request(method: str, path: str, json: dict[str, object] | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://aegis.test") as client:
        return await client.request(method, path, json=json)


def test_health_ready_samples_and_demo_contract(monkeypatch) -> None:
    monkeypatch.setenv("AEGIS_DEPLOYMENT_PROFILE", "lite")
    monkeypatch.setenv("AEGIS_LLM", "local")
    monkeypatch.setenv("AEGIS_EMBEDDINGS", "local")

    health = asyncio.run(_request("GET", "/health"))
    ready = asyncio.run(_request("GET", "/ready"))
    samples = asyncio.run(_request("GET", "/samples"))
    demo = asyncio.run(_request("GET", "/demo/"))

    assert health.status_code == 200
    assert health.json() == {"status": "ok", "service": "AEGIS"}
    assert ready.status_code == 200
    assert ready.json()["ready"] is True
    assert samples.status_code == 200
    assert len(samples.json()) == 20
    assert {"scenario_id", "title", "domain", "question"} <= samples.json()[0].keys()
    assert demo.status_code == 200
    assert "AEGIS" in demo.text


def test_investigate_contract_is_grounded_and_provider_explicit(monkeypatch) -> None:
    monkeypatch.setenv("AEGIS_DEPLOYMENT_PROFILE", "lite")
    monkeypatch.setenv("AEGIS_LLM", "local")
    monkeypatch.setenv("AEGIS_EMBEDDINGS", "local")

    response = asyncio.run(
        _request(
            "POST",
            "/investigate",
            json={
                "scenario_id": "SCN-005",
                "question": "What evidence explains the webhook delivery symptoms?",
            },
        )
    )
    payload = response.json()
    report = payload["report"]

    assert response.status_code == 200
    assert payload["status"] == report["status"]
    assert report["provider"] == "local"
    assert report["retrieval_mode"] == "lexical"
    evidence_references = {
        reference
        for record in report["evidence"]
        for reference in (record["evidence_id"], record["source_id"])
    }
    assert payload["citations"]
    assert set(payload["citations"]) <= evidence_references
    assert [entry["step"] for entry in payload["agent_trace"]] == [
        "supervisor",
        "document_research",
        "operations_analysis",
        "investigation_synthesis",
        "evidence_verification",
    ]


def test_invalid_requests_are_rejected_without_provider_fallback(monkeypatch) -> None:
    monkeypatch.setenv("AEGIS_DEPLOYMENT_PROFILE", "lite")
    monkeypatch.setenv("AEGIS_LLM", "local")
    monkeypatch.setenv("AEGIS_EMBEDDINGS", "local")

    missing_question = asyncio.run(_request("POST", "/investigate", json={"scenario_id": "SCN-005"}))
    short_question = asyncio.run(_request("POST", "/investigate", json={"question": "why?"}))
    malformed_id = asyncio.run(
        _request(
            "POST",
            "/investigate",
            json={"scenario_id": "not-a-scenario", "question": "What happened?"},
        )
    )
    oversized = asyncio.run(_request("POST", "/investigate", json={"question": "x" * 1001}))

    assert missing_question.status_code == 422
    assert short_question.status_code == 422
    assert malformed_id.status_code == 422
    assert oversized.status_code == 422
