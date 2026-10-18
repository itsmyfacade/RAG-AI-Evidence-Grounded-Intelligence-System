from unittest.mock import patch

import pytest
from langchain_core.documents import Document
from pydantic import ValidationError

from src.agents import run_investigation, validate_evidence
from src.api import health, investigate
from src.schemas import InvestigationRequest


def sample_documents():
    return [Document(page_content="HTTP 403 after deployment was caused by a missing reports:read authorization scope.", metadata={"document_id": "INC-001", "title": "Post-Deployment 403 Incident"})]


def test_health():
    assert health()["status"] == "ok"


def test_invalid_question():
    with pytest.raises(ValidationError):
        InvestigationRequest(question="bad")


def test_investigation_returns_citations(monkeypatch):
    monkeypatch.setenv("AEGIS_LLM", "local")
    with patch("src.agents.search", return_value=sample_documents()):
        response = investigate(InvestigationRequest(question="Why did reporting return HTTP 403?"))
    assert response.mode == "local"
    assert "INC-001" in response.citations
    assert "INC-001" in response.answer


def test_langgraph_workflow(monkeypatch):
    monkeypatch.setenv("AEGIS_LLM", "local")
    with patch("src.agents.search", return_value=sample_documents()):
        result = run_investigation("Investigate the post-deployment authorization failure")
    assert result["citations"] == ["INC-001"]
    assert {step.step for step in result["trace"]} >= {"supervisor", "document_research", "operations_analysis", "evidence_verification"}


def test_unsupported_citation_is_rejected():
    result = validate_evidence({"documents": sample_documents(), "answer": "Unsupported claim [INC-999]", "question": "x", "investigation_id": "INV-x", "trace": [], "attempts": 1, "mode": "local"})
    assert result["citations"] == []
    assert "validation failed" in result["answer"].lower()
