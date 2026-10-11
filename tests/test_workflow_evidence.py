from unittest.mock import patch

from langchain_core.documents import Document

from src.agents import run_investigation, validate_evidence
from src.dataset import generate_database
from src.schemas import EvidenceRecord


def _doc(scenario_id: str) -> Document:
    number = scenario_id[-3:]
    return Document(
        page_content=f"Runbook for {scenario_id}: duplicate webhook delivery is correlated with request authorization and deployment evidence.",
        metadata={"document_id": f"INC-{number}", "chunk_index": 0, "title": "Synthetic incident", "category": "incident"},
    )


def test_scn005_accepts_sql_and_webhook_source_ids(tmp_path, monkeypatch):
    database = tmp_path / "aegis.db"
    generate_database(database)
    monkeypatch.setenv("AEGIS_DATABASE_PATH", str(database))
    monkeypatch.setenv("AEGIS_LLM", "local")
    with patch("src.agents.search", return_value=[_doc("SCN-005")]):
        result = run_investigation("Investigate duplicate webhook events in SCN-005", "SCN-005")
    assert result["report"].status == "completed"
    assert result["citations"]
    assert {"CFG-005", "DEP-005", "REQ-005-00", "EVT-005-00"}.issubset(set(result["citations"]))
    assert all(claim.support_status != "unsupported" for claim in result["report"].claims)


def test_unknown_citation_still_fails_validation():
    state = {
        "investigation_id": "INV-TEST",
        "question": "test",
        "answer": "Claim [UNKNOWN-999]",
        "evidence": [EvidenceRecord(evidence_id="DOC-INC-001-0", source_type="document", source_id="INC-001", excerpt="known evidence")],
        "documents": [],
        "operational_evidence": [],
        "mode": "local",
        "attempts": 1,
    }
    result = validate_evidence(state)
    assert result["report"].status == "failed"
    assert result["citations"] == []


def test_missing_and_conflicting_scenarios_route_to_safe_states(tmp_path, monkeypatch):
    database = tmp_path / "aegis.db"
    generate_database(database)
    monkeypatch.setenv("AEGIS_DATABASE_PATH", str(database))
    monkeypatch.setenv("AEGIS_LLM", "local")
    with patch("src.agents.search", return_value=[_doc("SCN-018")]):
        missing = run_investigation("Investigate SCN-018", "SCN-018")
    with patch("src.agents.search", return_value=[_doc("SCN-019")]):
        conflicting = run_investigation("Investigate SCN-019", "SCN-019")
    assert missing["report"].status == "insufficient_evidence"
    assert missing["report"].attempts <= 2
    assert conflicting["report"].status == "escalated"
    assert conflicting["report"].contradictions
