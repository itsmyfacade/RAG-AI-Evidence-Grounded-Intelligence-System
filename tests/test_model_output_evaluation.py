from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from tools.phase3_model_output import (
    DECISION_SCHEMA,
    DECISION_SCHEMA_CANONICAL,
    FINGERPRINT_CONTRACT,
    PROTECTED_ARTIFACTS,
    build_blinded_review_packet,
    canonical_fingerprint,
    canonical_json_v3,
    capture_one,
    decision_counts,
    display_path,
    legacy_browser_fingerprint,
    packet_fingerprint,
    report_decisions,
    sha256_json,
    validate_decision_export,
    write_json,
)


def _packet() -> dict:
    return {
        "dataset_version": "test-v1",
        "cases": [{"case_id": "RET-001", "question": "What happened?", "answerability": "answerable", "expected_evidence": [{"document_id": "DOC-1"}], "expected_citation_ids": ["DOC-1"], "review_rationale": "hidden"}],
    }


def test_capture_preserves_actual_output_and_failure_state() -> None:
    captured = capture_one(_packet()["cases"][0], lambda _question: {"answer": "actual", "citations": ["DOC-1"], "mode": "local", "provider_model": "deterministic-local", "report": {"status": "completed", "retrieval_mode": "lexical", "evidence": [{"evidence_id": "DOC-1", "excerpt": "real"}], "findings": []}, "trace": []})
    assert captured["status"] == "completed"
    assert captured["answer"] == "actual"
    assert captured["retrieved_evidence"][0]["rank"] == 1
    failed = capture_one(_packet()["cases"][0], lambda _question: (_ for _ in ()).throw(RuntimeError("provider unavailable")))
    assert failed["status"] == "failed"
    assert "provider unavailable" in failed["error"]


def test_blinded_packet_excludes_ground_truth_fields() -> None:
    capture = {"schema_version": "capture", "run_id": "run-1", "source_packet_fingerprint": "source", "cases": [capture_one(_packet()["cases"][0], lambda _question: {"answer": "actual", "citations": [], "report": {"status": "completed", "evidence": [], "findings": []}, "trace": []})]}
    review = build_blinded_review_packet(capture)
    def keys(value):
        if isinstance(value, dict):
            return set(value) | set().union(*(keys(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(keys(item) for item in value)) if value else set()
        return set()

    serialized_keys = keys(review)
    assert review["blinded"] is True
    assert "expected_evidence" not in serialized_keys
    assert "expected_citation_ids" not in serialized_keys
    assert "answerability" not in serialized_keys
    assert review["cases"][0]["actual_output"]["answer"] == "actual"


def test_fingerprint_is_deterministic_and_changes_with_cases() -> None:
    first = packet_fingerprint(_packet())
    assert first == packet_fingerprint(copy.deepcopy(_packet()))
    changed = _packet()
    changed["cases"][0]["question"] = "Changed"
    assert first != packet_fingerprint(changed)
    assert sha256_json({"a": 1}) == sha256_json({"a": 1})


def test_canonical_fingerprint_contract_preserves_unicode() -> None:
    assert canonical_fingerprint("run-1", [{"case_id": "RET-001", "question": "Résumé evidence"}]) == canonical_fingerprint("run-1", [{"question": "Résumé evidence", "case_id": "RET-001"}])


def test_python_and_actual_javascript_canonical_bytes_and_hash_match(tmp_path: Path) -> None:
    fixture = {
        "z": ["café", {"𐀀": 2.0, "￿": -0.0, "nested": [1, 1.25, {}]}],
        "a": {"empty": [], "decimal": -12.3456789014, "integer": 7},
    }
    fixture_path = tmp_path / "cross-runtime-fixture.json"
    fixture_path.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")
    script = """
const fs = require('fs');
const { canonicalJSONString, fingerprint } = require('./frontend/fingerprint.js');
const value = JSON.parse(fs.readFileSync(process.argv[1], 'utf8'));
Promise.resolve(fingerprint(value)).then((hash) => {
  process.stdout.write(Buffer.from(canonicalJSONString(value), 'utf8').toString('base64') + '\\n' + hash);
});
"""
    completed = subprocess.run(["node", "-e", script, str(fixture_path)], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, check=True)
    javascript_bytes, javascript_hash = completed.stdout.splitlines()
    import base64

    python_bytes = canonical_json_v3(fixture).encode("utf-8")
    assert base64.b64encode(python_bytes).decode("ascii") == javascript_bytes
    assert javascript_hash == hashlib.sha256(python_bytes).hexdigest()
    reordered = {"a": fixture["a"], "z": fixture["z"]}
    assert canonical_json_v3(reordered) == canonical_json_v3(fixture)
    rejected = subprocess.run(["node", "-e", "const { canonicalJSONString } = require('./frontend/fingerprint.js'); canonicalJSONString({bad: NaN});"], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert rejected.returncode != 0


def test_canonical_contract_rejects_unsupported_numbers() -> None:
    with pytest.raises(ValueError):
        canonical_json_v3(float("nan"))
    with pytest.raises(ValueError):
        canonical_json_v3(float("inf"))


def test_write_json_protects_historical_artifacts_and_requires_overwrite(tmp_path: Path) -> None:
    protected = next(iter(PROTECTED_ARTIFACTS))
    before = protected.read_bytes() if protected.exists() else None
    with pytest.raises(ValueError):
        write_json(protected, {"unexpected": True}, overwrite=True)
    if before is not None:
        assert protected.read_bytes() == before
    output = tmp_path / "output.json"
    write_json(output, {"version": 1})
    with pytest.raises(FileExistsError):
        write_json(output, {"version": 2})
    write_json(output, {"version": 2}, overwrite=True)
    assert json.loads(output.read_text(encoding="utf-8")) == {"version": 2}


def test_report_counts_decisions_and_exposes_incomplete_denominators() -> None:
    capture = {"run_id": "run-1"}
    review = {"review_packet_fingerprint": "fp", "cases": [{"case_id": "RET-001"}, {"case_id": "RET-002"}]}
    decisions = {"RET-001": {"overall_decision": "supported_correct", "answerability_judgment": "answerable"}}
    assert decision_counts(decisions, review["cases"])["pending"] == 1
    report = report_decisions(capture, review, decisions, {"cases": [{"case_id": "RET-001", "answerability": "answerable"}]})
    assert report["completed_cases"] == 1
    assert report["incomplete_cases"] == 1
    assert report["controlled_ground_truth_comparison"]["status"] == "post_judgment_only"


def _review_artifacts() -> tuple[dict, dict, dict, dict]:
    cases = [{"case_id": "RET-001", "question": "What happened?"}, {"case_id": "RET-002", "question": "Why?"}]
    capture = {"run_id": "run-1", "source_packet_fingerprint": "source", "cases": copy.deepcopy(cases)}
    review = {"schema_version": "aegis-phase3-model-output-review-packet-v1", "source_run_id": "run-1", "source_packet_fingerprint": "source", "cases": copy.deepcopy(cases), "review_packet_fingerprint": sha256_json(cases)}
    decisions = {case["case_id"]: {"overall_decision": "partially_supported", "notes": f"Reason for {case['case_id']}", "answerability_judgment": "unanswerable"} for case in cases}
    legacy = {"schema_version": DECISION_SCHEMA, "source_run_id": "run-1", "packet_fingerprint": legacy_browser_fingerprint("run-1", cases), "decisions": decisions}
    return capture, review, decisions, legacy


def test_valid_legacy_export_is_accepted() -> None:
    capture, review, _, legacy = _review_artifacts()
    assert validate_decision_export(capture, review, legacy) == legacy["decisions"]


def test_valid_canonical_export_is_accepted() -> None:
    capture, review, decisions, _ = _review_artifacts()
    review["fingerprint_contract"] = FINGERPRINT_CONTRACT
    review["review_packet_fingerprint"] = canonical_fingerprint("run-1", review["cases"])
    canonical = {"schema_version": DECISION_SCHEMA_CANONICAL, "fingerprint_contract": FINGERPRINT_CONTRACT, "source_run_id": "run-1", "packet_fingerprint": canonical_fingerprint("run-1", review["cases"]), "decisions": decisions}
    assert validate_decision_export(capture, review, canonical) == decisions


@pytest.mark.parametrize("mutation,expected", [
    (lambda payload: payload.update(packet_fingerprint="wrong"), "fingerprint"),
    (lambda payload: payload.update(source_run_id="run-2"), "run_id"),
    (lambda payload: payload["decisions"].pop("RET-002"), "case-ID"),
    (lambda payload: payload["decisions"].update({"RET-999": payload["decisions"]["RET-001"]}), "case-ID"),
    (lambda payload: payload["decisions"]["RET-001"].update(overall_decision="invalid"), "overall_decision"),
    (lambda payload: payload["decisions"]["RET-001"].pop("notes"), "reviewer notes"),
])
def test_invalid_exports_fail_safely(mutation, expected: str) -> None:
    capture, review, _, legacy = _review_artifacts()
    payload = copy.deepcopy(legacy)
    mutation(payload)
    with pytest.raises(ValueError, match=expected):
        validate_decision_export(capture, review, payload)


def test_duplicate_case_ids_are_rejected() -> None:
    capture, review, _, legacy = _review_artifacts()
    review["cases"].append(copy.deepcopy(review["cases"][0]))
    review["review_packet_fingerprint"] = sha256_json(review["cases"])
    legacy["packet_fingerprint"] = legacy_browser_fingerprint("run-1", review["cases"])
    with pytest.raises(ValueError, match="duplicate case IDs"):
        validate_decision_export(capture, review, legacy)


def test_ground_truth_comparison_distinguishes_disagreement_and_missing_fields() -> None:
    capture = {"run_id": "run-1"}
    review = {"review_packet_fingerprint": "fp", "cases": [{"case_id": "A"}, {"case_id": "B"}, {"case_id": "C"}, {"case_id": "D"}, {"case_id": "E"}]}
    decisions = {
        "A": {"overall_decision": "partially_supported", "answerability_judgment": "unanswerable"},
        "B": {"overall_decision": "partially_supported"},
        "C": {"overall_decision": "partially_supported", "answerability_judgment": "not_assessable"},
        "D": {"overall_decision": "partially_supported", "answerability_judgment": "answerable"},
        "E": {"overall_decision": "partially_supported", "answerability_judgment": "not_assessable"},
    }
    truth = {"cases": [{"case_id": "A", "answerability": "answerable"}, {"case_id": "B", "answerability": "answerable"}, {"case_id": "C"}, {"case_id": "D", "answerability": "answerable"}, {"case_id": "E", "answerability": "answerable"}]}
    counts = report_decisions(capture, review, decisions, truth)["controlled_ground_truth_comparison"]["counts"]
    assert counts == {"agreement": 1, "label_disagreement": 1, "missing_expected_label": 1, "missing_reviewer_judgment": 1, "not_assessable": 1}


def test_denominators_separate_missing_and_not_assessable() -> None:
    capture = {"run_id": "run-1"}
    review = {"review_packet_fingerprint": "fp", "cases": [{"case_id": "A"}, {"case_id": "B"}, {"case_id": "C"}]}
    decisions = {
        "A": {"overall_decision": "partially_supported", "uncertainty": "not_assessable"},
        "B": {"overall_decision": "partially_supported", "uncertainty": "partial"},
        "C": {"overall_decision": "partially_supported"},
    }
    metric = report_decisions(capture, review, decisions)["criteria"]["uncertainty"]
    assert metric["denominator"] == 2
    assert metric["substantive_denominator"] == 1
    assert metric["not_assessable"] == 1
    assert metric["excluded_missing"] == 1


def test_display_path_supports_relative_inside_and_absolute_outside_paths(tmp_path: Path) -> None:
    inside = display_path(Path(__file__).resolve())
    assert inside == "tests/test_model_output_evaluation.py"
    assert display_path(tmp_path / "report.json") == str((tmp_path / "report.json").resolve())
