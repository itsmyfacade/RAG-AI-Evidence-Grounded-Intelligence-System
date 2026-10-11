from unittest.mock import patch

from langchain_core.documents import Document

from src.agents import _evidence_brief, run_investigation, validate_evidence
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
    canonical_ids = {record.evidence_id for record in result["report"].evidence}
    assert result["report"].retrieval_mode in {"lexical", "chroma"}
    assert result["report"].summary.startswith("Assessment:")
    assert any(finding.status == "observation" for finding in result["report"].findings)
    assert all(reference in canonical_ids for finding in result["report"].findings for reference in finding.evidence_refs)


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


def test_structured_provider_findings_are_registry_validated():
    evidence = [EvidenceRecord(evidence_id="DOC-INC-001-0", source_type="document", source_id="INC-001", excerpt="HTTP 403 missing reports scope")]
    valid = validate_evidence({
        "investigation_id": "INV-STRUCTURED",
        "question": "test",
        "answer": "The evidence supports the observation [DOC-INC-001-0]",
        "evidence": evidence,
        "documents": [_doc("SCN-001")],
        "operational_evidence": [],
        "mode": "bedrock",
        "provider_model": "us.amazon.nova-micro-v1:0",
        "structured_output": {"findings": [{"statement": "HTTP 403 is observed", "status": "observation", "evidence_refs": ["DOC-INC-001-0"]}]},
        "attempts": 1,
    })
    invalid = validate_evidence({
        "investigation_id": "INV-STRUCTURED-BAD",
        "question": "test",
        "answer": "Unsupported [UNKNOWN-999]",
        "evidence": evidence,
        "documents": [_doc("SCN-001")],
        "operational_evidence": [],
        "mode": "bedrock",
        "structured_output": {"findings": [{"statement": "Unsupported", "status": "conclusion", "evidence_refs": ["UNKNOWN-999"]}]},
        "attempts": 1,
    })
    assert valid["report"].findings[0].evidence_refs == ["DOC-INC-001-0"]
    assert valid["report"].model == "us.amazon.nova-micro-v1:0"
    assert invalid["report"].status == "failed"


def test_scn005_documented_cause_is_assessed_without_claiming_operational_confirmation():
    evidence = [
        EvidenceRecord(
            evidence_id="DOC-INC-005-0",
            source_type="document",
            source_id="INC-005",
            excerpt="A consumer processed webhook retries as new transactions because it did not persist event_id values.",
        ),
        EvidenceRecord(
            evidence_id="WEBHOOK-SCN-005-001",
            source_type="webhook",
            source_id="EVT-005-00",
            excerpt="Webhook delivery was delayed after 1 attempt.",
        ),
    ]
    result = validate_evidence({
        "investigation_id": "INV-SCN005-CAUSE",
        "question": "Investigate duplicate webhook events in SCN-005",
        "answer": "Documented cause [DOC-INC-005-0]; operational confirmation remains uncertain [WEBHOOK-SCN-005-001]",
        "evidence": evidence,
        "documents": [_doc("SCN-005")],
        "operational_evidence": [evidence[1]],
        "mode": "bedrock",
        "structured_output": {"findings": [{
            "statement": "Documented cause: the consumer did not persist event_id values; operational confirmation is not established.",
            "status": "conclusion",
            "evidence_refs": ["DOC-INC-005-0"],
        }]},
        "attempts": 1,
    })
    assert result["report"].status == "completed"
    assert result["report"].claims[0].support_status == "supported"
    assert "operational confirmation" in result["report"].findings[0].statement


def test_scn005_evidence_brief_prioritizes_aligned_incident_and_surfaces_cause():
    state = {
        "scenario_id": "SCN-005",
        "evidence": [
            EvidenceRecord(evidence_id="DOC-INC-002-0", source_type="document", source_id="INC-002", excerpt="Webhook deliveries were delayed after consumers stopped acknowledging events.", metadata={"category": "incident"}),
            EvidenceRecord(evidence_id="DOC-API-005-0", source_type="document", source_id="API-005", excerpt="Repeated event IDs should be processed idempotently.", metadata={"category": "api"}),
            EvidenceRecord(evidence_id="DOC-INC-005-0", source_type="document", source_id="INC-005", excerpt="A consumer processed webhook retries as new transactions because it did not persist event_id values.", metadata={"category": "incident"}),
            EvidenceRecord(evidence_id="SQL-SCN-005-001", source_type="log", source_id="REQ-005-00", excerpt="HTTP 500 webhook error", scenario_id="SCN-005"),
        ],
    }
    brief = _evidence_brief(state)
    assert brief.index("DOC-INC-005-0") < brief.index("DOC-INC-002-0")
    assert "documented_causal_statements" in brief
    assert "did not persist event_id values" in brief
    assert "DOC-API-005-0" in brief
    assert "DOC-INC-002-0" in brief
    assert "OBSERVED OPERATIONAL RECORDS" in brief


def test_evidence_brief_does_not_promote_cross_incident_document():
    state = {
        "scenario_id": "SCN-018",
        "evidence": [EvidenceRecord(
            evidence_id="DOC-INC-005-0", source_type="document", source_id="INC-005",
            excerpt="A consumer processed webhook retries as new transactions.", metadata={"category": "incident"},
        )],
    }
    brief = _evidence_brief(state)
    assert "LOWER-CONFIDENCE OR CROSS-INCIDENT BACKGROUND" in brief
    assert "classification=not direct proof of this scenario" in brief


def test_evidence_brief_marks_incident_without_explicit_cause():
    state = {
        "scenario_id": "SCN-002",
        "evidence": [EvidenceRecord(
            evidence_id="DOC-INC-002-0", source_type="document", source_id="INC-002",
            excerpt="Webhook delivery issue observed. Engineers reviewed delivery logs and retry counts.", metadata={"category": "incident"},
        )],
    }
    brief = _evidence_brief(state)
    assert "DOC-INC-002-0" in brief
    assert "none explicitly detected" in brief


def test_scn005_symptom_only_output_gets_documented_cause_gap():
    evidence = [EvidenceRecord(
        evidence_id="DOC-INC-005-0", source_type="document", source_id="INC-005",
        excerpt="A consumer processed webhook retries as new transactions because it did not persist event_id values.",
        metadata={"category": "incident"},
    )]
    result = validate_evidence({
        "investigation_id": "INV-SCN005-SYMPTOMS",
        "question": "Investigate duplicate webhook events in SCN-005",
        "scenario_id": "SCN-005",
        "answer": "Duplicate downstream records were observed [DOC-INC-005-0]",
        "evidence": evidence,
        "documents": [_doc("SCN-005")],
        "operational_evidence": [],
        "mode": "bedrock",
        "structured_output": {"findings": [{"statement": "Duplicate downstream records and HTTP 500 errors were observed.", "status": "observation", "evidence_refs": ["DOC-INC-005-0"]}]},
        "attempts": 1,
    })
    assert any("Documented causal mechanism not addressed" in gap for gap in result["report"].evidence_gaps)
    assert any("DOC-INC-005-0" in gap and "persist event_id" in gap for gap in result["report"].evidence_gaps)


def test_scn005_output_addressing_documented_cause_has_no_coverage_gap():
    evidence = [EvidenceRecord(
        evidence_id="DOC-INC-005-0", source_type="document", source_id="INC-005",
        excerpt="A consumer processed webhook retries as new transactions because it did not persist event_id values.",
        metadata={"category": "incident"},
    )]
    result = validate_evidence({
        "investigation_id": "INV-SCN005-CAUSE-COVERED",
        "question": "Investigate duplicate webhook events in SCN-005",
        "scenario_id": "SCN-005",
        "answer": "The documented cause is missing event_id persistence, but operational confirmation is incomplete [DOC-INC-005-0]",
        "evidence": evidence,
        "documents": [_doc("SCN-005")],
        "operational_evidence": [],
        "mode": "bedrock",
        "structured_output": {"findings": [{"statement": "Documented cause: the consumer did not persist event_id values; this is not independently operationally confirmed.", "status": "conclusion", "evidence_refs": ["DOC-INC-005-0"]}]},
        "attempts": 1,
    })
    assert not any("Documented causal mechanism not addressed" in gap for gap in result["report"].evidence_gaps)


def test_documented_cause_coverage_ignores_uncertain_negated_and_cross_incident_records():
    evidence = [
        EvidenceRecord(evidence_id="DOC-INC-002-0", source_type="document", source_id="INC-002", excerpt="The issue was not caused by missing idempotency.", metadata={"category": "incident"}),
        EvidenceRecord(evidence_id="DOC-INC-003-0", source_type="document", source_id="INC-003", excerpt="A hypothesis might be caused by delayed ingestion.", metadata={"category": "incident"}),
        EvidenceRecord(evidence_id="DOC-INC-005-0", source_type="document", source_id="INC-005", excerpt="A consumer did not persist event_id values.", metadata={"category": "incident"}),
    ]
    result = validate_evidence({
        "investigation_id": "INV-COVERAGE-SAFETY",
        "question": "Investigate SCN-018",
        "answer": "Operational records are incomplete.",
        "evidence": evidence,
        "documents": [_doc("SCN-018")],
        "operational_evidence": [],
        "mode": "bedrock",
        "structured_output": {"findings": [{"statement": "Operational evidence is incomplete and no causal conclusion is established.", "status": "observation", "evidence_refs": []}]},
        "attempts": 1,
    })
    assert not any("DOC-INC-002-0" in gap or "DOC-INC-003-0" in gap or "DOC-INC-005-0" in gap for gap in result["report"].evidence_gaps)


def test_contrasting_document_does_not_support_an_unrelated_root_cause():
    evidence = [EvidenceRecord(
        evidence_id="DOC-INC-002-0",
        source_type="document",
        source_id="INC-002",
        excerpt="Webhook deliveries were delayed after downstream consumers stopped acknowledging events within the configured timeout.",
    )]
    result = validate_evidence({
        "investigation_id": "INV-CONTRAST",
        "question": "Investigate delayed webhook delivery",
        "answer": "The evidence is insufficient for a missing-idempotency root cause [DOC-INC-002-0]",
        "evidence": evidence,
        "documents": [_doc("SCN-002")],
        "operational_evidence": [],
        "mode": "bedrock",
        "structured_output": {"findings": [{
            "statement": "Confirmed root cause: missing idempotency caused duplicate processing.",
            "status": "conclusion",
            "evidence_refs": ["DOC-INC-002-0"],
        }]},
        "attempts": 1,
    })
    assert result["report"].claims[0].support_status in {"unsupported", "partially_supported"}
    assert any("weak lexical support" in gap for gap in result["report"].evidence_gaps)


def test_failed_report_preserves_provider_identity_usage_and_safe_diagnostics():
    result = validate_evidence({
        "investigation_id": "INV-BEDROCK-FAIL",
        "question": "Investigate SCN-005",
        "answer": "Investigation failed",
        "evidence": [],
        "documents": [],
        "operational_evidence": [],
        "mode": "bedrock",
        "provider_error": "bedrock:schema_mismatch",
        "provider_model": "us.amazon.nova-micro-v1:0",
        "token_usage": {"input_tokens": 2909, "output_tokens": 986, "total_tokens": 3895},
        "provider_diagnostics": {"parser_error": "findings.2.status:literal_error;received_status=documented_cause"},
        "attempts": 2,
    })
    report = result["report"]
    assert report.status == "failed"
    assert report.model == "us.amazon.nova-micro-v1:0"
    assert report.token_usage["total_tokens"] == 3895
    assert report.provider_diagnostics["parser_error"].endswith("received_status=documented_cause")


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
    assert missing["report"].evidence_gaps
    assert any("missing" in check.lower() or "correlation" in check.lower() for check in missing["report"].recommended_checks)
    assert conflicting["report"].status == "escalated"
    assert conflicting["report"].contradictions
