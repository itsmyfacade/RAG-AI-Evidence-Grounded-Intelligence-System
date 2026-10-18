from langchain_core.documents import Document

from src.schemas import EvidenceRecord
from src.status_rules import classify_status


def _doc():
    return [Document(page_content="Relevant incident evidence", metadata={"document_id": "INC-001"})]


def _log(index, deployment="DEP-001", event="EVT-001"):
    return EvidenceRecord(evidence_id=f"SQL-{index}", source_type="log", source_id=f"REQ-{index}", excerpt="HTTP 500", metadata={"deployment_id": deployment or "", "event_id": event or "", "occurred_at": "2026-01-01T10:00:00Z"})


def test_status_rules_accept_correlated_records():
    status, gaps, contradictions = classify_status(_doc(), [_log(1), EvidenceRecord(evidence_id="OPS-1", source_type="deployment", source_id="DEP-001", excerpt="deploy", metadata={"occurred_at": "2026-01-01T09:30:00+00:00"})])
    assert status == "completed"
    assert not gaps
    assert not contradictions


def test_status_rules_return_insufficient_for_missing_correlation():
    records = [_log(index, deployment=None, event=None) for index in range(1, 7)] + [_log(7)]
    status, gaps, _ = classify_status(_doc(), records)
    assert status == "insufficient_evidence"
    assert gaps


def test_status_rules_return_escalated_for_offset_aware_timestamp_conflict():
    records = [_log(1), EvidenceRecord(evidence_id="OPS-1", source_type="deployment", source_id="DEP-001", excerpt="deploy", metadata={"occurred_at": "2026-01-01T10:45:00Z"})]
    status, _, contradictions = classify_status(_doc(), records)
    assert status == "escalated"
    assert contradictions


def test_status_rules_ignore_malformed_timestamps_conservatively():
    records = [_log(1), EvidenceRecord(evidence_id="OPS-1", source_type="deployment", source_id="DEP-001", excerpt="deploy", metadata={"occurred_at": "not-a-timestamp"})]
    status, _, contradictions = classify_status(_doc(), records)
    assert status == "completed"
    assert not contradictions
