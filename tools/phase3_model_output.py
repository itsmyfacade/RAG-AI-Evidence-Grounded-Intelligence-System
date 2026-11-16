"""Capture and review actual AEGIS outputs for the Phase 3 review sample.

This module deliberately keeps the ground-truth packet separate from captured
model outputs. The review packet produced from a capture contains no expected
labels, evidence IDs, or review rationales.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
GROUND_TRUTH_PACKET = ROOT / "data/evaluation/results/phase3-ground-truth-review-packet.json"
DEFAULT_RESULTS = ROOT / "data/evaluation/results"
CAPTURE_SCHEMA = "aegis-phase3-model-output-run-v1"
REVIEW_SCHEMA = "aegis-phase3-model-output-review-packet-v1"
DECISION_SCHEMA = "aegis-phase3-model-output-decisions-v1"
DECISION_SCHEMA_CANONICAL = "aegis-phase3-model-output-decisions-v3"
REPORT_SCHEMA = "aegis-phase3-model-output-report-v2"
FINGERPRINT_CONTRACT = "aegis-phase3-fingerprint-v3"
CANONICAL_NUMBER_SCALE = 1_000_000_000
CANONICAL_NUMBER_LIMIT = 1_000_000
PROTECTED_ARTIFACTS = {
    (ROOT / "data/evaluation/results/phase3-model-output-20261115T175728Z-542a10f8.json").resolve(),
    (ROOT / "data/evaluation/results/phase3-model-output-20261115T175728Z-542a10f8-review-packet.json").resolve(),
    (ROOT / "data/evaluation/results/phase3-ground-truth-review-packet.json").resolve(),
    (ROOT / "data/evaluation/results/phase3-model-output-report.json").resolve(),
    Path(r"D:\Download$\aegis-model-output-review-decisions.json").resolve(),
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _utf16_sort_key(value: str) -> bytes:
    return value.encode("utf-16-be", "surrogatepass")


def _canonical_string(value: str) -> str:
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise ValueError("Canonical fingerprints reject unpaired UTF-16 surrogate characters.")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _canonical_number(value: int | float) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("Canonical fingerprints support only JSON integer and floating-point numbers.")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Canonical fingerprints reject non-finite numbers.")
    if abs(value) > CANONICAL_NUMBER_LIMIT:
        raise ValueError(f"Canonical fingerprints support numbers with absolute value <= {CANONICAL_NUMBER_LIMIT}.")
    if value == 0:
        return "0"
    scaled = math.floor(abs(value) * CANONICAL_NUMBER_SCALE + 0.5)
    whole, fraction = divmod(scaled, CANONICAL_NUMBER_SCALE)
    number = str(whole)
    if fraction:
        number += "." + f"{fraction:09d}".rstrip("0")
    return ("-" if value < 0 else "") + number


def canonical_json_v3(value: Any) -> str:
    """Serialize the restricted v3 fingerprint value schema deterministically.

    Supported values are null, booleans, strings containing Unicode scalar
    values, arrays, objects with string keys, and finite numbers in the range
    +/- 1,000,000. Numbers are rounded half-up to nine fractional digits.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return _canonical_string(value)
    if isinstance(value, (int, float)):
        return _canonical_number(value)
    if isinstance(value, list):
        return "[" + ",".join(canonical_json_v3(item) for item in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("Canonical fingerprint object keys must be strings.")
        fields = [f"{_canonical_string(key)}:{canonical_json_v3(value[key])}" for key in sorted(value, key=_utf16_sort_key)]
        return "{" + ",".join(fields) + "}"
    raise TypeError(f"Unsupported canonical fingerprint value: {type(value).__name__}")


def packet_fingerprint(packet: dict[str, Any]) -> str:
    return sha256_json({"dataset_version": packet.get("dataset_version", "unknown"), "cases": packet.get("cases", [])})


def canonical_fingerprint(source_run_id: str, cases: list[dict[str, Any]]) -> str:
    """Hash the restricted v3 contract with stable cross-runtime ordering."""
    payload = canonical_json_v3({"cases": cases, "source_run_id": source_run_id})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def legacy_browser_fingerprint(source_run_id: str, cases: list[dict[str, Any]]) -> str:
    """Reproduce the v1 browser JSON.stringify fingerprint exactly."""
    payload = json.dumps({"source_run_id": source_run_id, "cases": cases}, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def display_path(path: Path) -> str:
    """Prefer repository-relative output while supporting external absolute paths."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(resolved)


def git_revision() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=5, check=True
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() or None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON object key '{key}' in {path}")
            result[key] = value
        return result

    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle, object_pairs_hook=reject_duplicate_keys)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def safe_settings_snapshot() -> dict[str, Any]:
    from src.settings import get_settings

    settings = get_settings()
    return {
        "deployment_profile": settings.deployment_profile,
        "llm_mode": settings.llm_mode,
        "embeddings_mode": settings.embeddings_mode,
        "embedding_model": settings.embedding_model if settings.llm_mode == "local" else "configured",
        "retrieval_profile": settings.retrieval_profile,
        "retrieval_k": settings.retrieval_k,
        "retrieval_score_threshold": settings.retrieval_score_threshold,
        "retrieval_abstention": settings.retrieval_abstention,
        "retrieval_abstention_threshold": settings.retrieval_abstention_threshold,
        "max_agent_attempts": settings.max_agent_attempts,
        "provider_timeout_seconds": settings.provider_timeout_seconds,
    }


def _model_dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _evidence_with_rank(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"rank": index, **record} for index, record in enumerate(records, 1)]


def capture_one(case: dict[str, Any], invoke: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
    started = time.perf_counter()
    captured: dict[str, Any] = {
        "case_id": case["case_id"],
        "question": case["question"],
        "started_at": utc_now(),
        "status": "failed",
        "answer": None,
        "findings": [],
        "retrieved_evidence": [],
        "citations": [],
        "abstention": {"status": "unknown", "report_status": None},
        "provider": None,
        "model": None,
        "retrieval_mode": None,
        "agent_trace": [],
        "error": None,
    }
    try:
        result = invoke(case["question"])
        report = _model_dump(result.get("report", {})) or {}
        evidence = report.get("evidence", result.get("evidence", []))
        report_status = report.get("status")
        captured.update(
            {
                "status": "completed",
                "answer": result.get("answer"),
                "findings": report.get("findings", []),
                "retrieved_evidence": _evidence_with_rank(evidence if isinstance(evidence, list) else []),
                "citations": result.get("citations", []),
                "abstention": {
                    "status": "abstained" if report_status in {"insufficient_evidence", "failed", "escalated"} else "not_abstained",
                    "report_status": report_status,
                },
                "provider": result.get("mode") or report.get("provider"),
                "model": result.get("provider_model") or report.get("model"),
                "retrieval_mode": report.get("retrieval_mode"),
                "agent_trace": [_model_dump(item) for item in result.get("trace", report.get("agent_trace", []))],
            }
        )
        if report.get("provider_error"):
            captured["status"] = "incomplete"
            captured["error"] = report["provider_error"]
    except Exception as exc:  # noqa: BLE001 - one case must not abort the batch.
        captured["error"] = f"{type(exc).__name__}: {exc}"
    captured["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
    captured["finished_at"] = utc_now()
    return captured


def capture_run(packet: dict[str, Any], *, invoke: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
    started = time.perf_counter()
    cases = [capture_one(case, invoke) for case in packet.get("cases", [])]
    configuration = safe_settings_snapshot()
    return {
        "schema_version": CAPTURE_SCHEMA,
        "run_id": f"phase3-model-output-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}",
        "created_at": utc_now(),
        "git_revision": git_revision(),
        "source_packet": GROUND_TRUTH_PACKET.relative_to(ROOT).as_posix(),
        "source_packet_fingerprint": packet_fingerprint(packet),
        "case_count": len(cases),
        "configuration": configuration,
        "execution": {
            "measurement": "per-case monotonic wall-clock time around the existing run_investigation graph",
            "run_latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "completed": sum(item["status"] == "completed" for item in cases),
            "incomplete": sum(item["status"] == "incomplete" for item in cases),
            "failed": sum(item["status"] == "failed" for item in cases),
        },
        "limitations": [
            "This is a local capture using the selected provider and retrieval configuration, not a production accuracy result.",
            "Expected evidence and labels are intentionally absent from this output artifact.",
            "Provider failures remain explicit and are not converted into successful outputs.",
        ],
        "cases": cases,
    }


def build_blinded_review_packet(capture: dict[str, Any]) -> dict[str, Any]:
    cases = []
    for item in capture.get("cases", []):
        cases.append(
            {
                "case_id": item["case_id"],
                "question": item["question"],
                "output_status": item["status"],
                "actual_output": {
                    "answer": item.get("answer"),
                    "findings": item.get("findings", []),
                    "retrieved_evidence": item.get("retrieved_evidence", []),
                    "citations": item.get("citations", []),
                    "abstention": item.get("abstention", {}),
                    "agent_trace": item.get("agent_trace", []),
                },
                "run_metadata": {
                    "provider": item.get("provider"),
                    "model": item.get("model"),
                    "retrieval_mode": item.get("retrieval_mode"),
                    "latency_ms": item.get("latency_ms"),
                    "error": item.get("error"),
                },
            }
        )
    return {
        "schema_version": REVIEW_SCHEMA,
        "source_run_id": capture.get("run_id"),
        "source_run_schema_version": capture.get("schema_version"),
        "source_packet_fingerprint": capture.get("source_packet_fingerprint"),
        "fingerprint_contract": FINGERPRINT_CONTRACT,
        "review_packet_fingerprint": canonical_fingerprint(str(capture.get("run_id")), cases),
        "blinded": True,
        "review_mode": "model_output_blinded_initial_judgment",
        "independent_reviewed": False,
        "cases": cases,
        "limitations": [
            "No expected answerability, expected citations, expected evidence, or review rationale is included.",
            "A controlled comparison requires a later report step using the original ground-truth packet.",
        ],
    }


def decision_counts(decisions: dict[str, Any], cases: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"supported_correct": 0, "partially_supported": 0, "unsupported_incorrect": 0, "not_assessable": 0, "pending": 0}
    for case in cases:
        decision = decisions.get(case["case_id"], {}).get("overall_decision", "pending")
        counts[decision] = counts.get(decision, 0) + 1
    return counts


VALID_DECISION_VALUES = {
    "overall_decision": {"supported_correct", "partially_supported", "unsupported_incorrect", "not_assessable"},
    "evidence_relevance": {"strong", "partial", "weak", "not_assessable"},
    "citation_support": {"supported", "partial", "unsupported", "not_assessable"},
    "answer_correctness": {"correct", "partial", "incorrect", "not_assessable"},
    "abstention": {"appropriate", "inappropriate", "not_applicable", "not_assessable"},
    "uncertainty": {"appropriate", "partial", "missing", "not_assessable"},
    "answerability_judgment": {"answerable", "unanswerable", "not_assessable"},
}


def _case_ids(cases: list[dict[str, Any]], label: str) -> set[str]:
    ids = [case.get("case_id") for case in cases]
    if any(not isinstance(case_id, str) or not case_id for case_id in ids):
        raise ValueError(f"{label} contains a case without a valid case_id")
    duplicates = sorted({case_id for case_id in ids if ids.count(case_id) > 1})
    if duplicates:
        raise ValueError(f"{label} contains duplicate case IDs: {', '.join(duplicates)}")
    return set(ids)


def _validate_exact_case_ids(actual: set[str], expected: set[str], label: str) -> None:
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing={','.join(missing)}")
        if extra:
            details.append(f"unexpected={','.join(extra)}")
        raise ValueError(f"{label} case-ID set does not match the review packet ({'; '.join(details)})")


def _review_fingerprint_is_valid(review_packet: dict[str, Any]) -> bool:
    source_run_id = review_packet.get("source_run_id")
    cases = review_packet.get("cases")
    if not isinstance(source_run_id, str) or not isinstance(cases, list):
        return False
    stored = review_packet.get("review_packet_fingerprint")
    if review_packet.get("fingerprint_contract") == FINGERPRINT_CONTRACT:
        return stored == canonical_fingerprint(source_run_id, cases)
    return stored == sha256_json(cases)


def validate_decision_export(capture: dict[str, Any], review_packet: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Validate provenance and return the decision map only after all checks pass."""
    capture_run_id = capture.get("run_id")
    review_run_id = review_packet.get("source_run_id")
    decision_run_id = payload.get("source_run_id")
    if not isinstance(capture_run_id, str) or capture_run_id != review_run_id:
        raise ValueError("Capture and review packet run IDs do not match.")
    if decision_run_id != capture_run_id:
        raise ValueError("Decision export source_run_id does not match the capture run.")
    if review_packet.get("source_packet_fingerprint") != capture.get("source_packet_fingerprint"):
        raise ValueError("Review packet source fingerprint does not match the capture artifact.")
    if not _review_fingerprint_is_valid(review_packet):
        raise ValueError("Review packet content fingerprint is invalid.")
    if payload.get("schema_version") == DECISION_SCHEMA:
        expected_fingerprint = legacy_browser_fingerprint(capture_run_id, review_packet.get("cases", []))
        if payload.get("packet_fingerprint") != expected_fingerprint:
            raise ValueError("Legacy decision fingerprint does not match the review packet.")
    elif payload.get("schema_version") == DECISION_SCHEMA_CANONICAL:
        if payload.get("fingerprint_contract") != FINGERPRINT_CONTRACT:
            raise ValueError("Canonical decision export is missing its fingerprint contract.")
        expected_fingerprint = canonical_fingerprint(capture_run_id, review_packet.get("cases", []))
        if payload.get("packet_fingerprint") != expected_fingerprint:
            raise ValueError("Canonical decision fingerprint does not match the review packet.")
    else:
        raise ValueError("Unsupported model-output decision schema version.")
    capture_ids = _case_ids(capture.get("cases", []), "Capture")
    review_ids = _case_ids(review_packet.get("cases", []), "Review packet")
    _validate_exact_case_ids(review_ids, capture_ids, "Review packet")
    decisions = payload.get("decisions")
    if not isinstance(decisions, dict):
        raise ValueError("Decision export must contain a decisions object.")
    decision_ids = set(decisions)
    _validate_exact_case_ids(decision_ids, review_ids, "Decision export")
    for case_id, decision in decisions.items():
        if not isinstance(decision, dict):
            raise ValueError(f"Decision for {case_id} is not an object.")
        if decision.get("overall_decision") not in VALID_DECISION_VALUES["overall_decision"]:
            raise ValueError(f"Decision for {case_id} has an invalid overall_decision.")
        if not isinstance(decision.get("notes"), str) or not decision["notes"].strip():
            raise ValueError(f"Decision for {case_id} is missing reviewer notes.")
        for field, allowed in VALID_DECISION_VALUES.items():
            if field in decision and decision[field] not in allowed:
                raise ValueError(f"Decision for {case_id} has invalid {field}={decision[field]!r}.")
    return decisions


def report_decisions(capture: dict[str, Any], review_packet: dict[str, Any], decisions: dict[str, Any], ground_truth: dict[str, Any] | None = None) -> dict[str, Any]:
    cases = review_packet.get("cases", [])
    counts = decision_counts(decisions, cases)
    complete_ids = {case["case_id"] for case in cases if decisions.get(case["case_id"], {}).get("overall_decision") not in {None, "pending"}}
    criteria = {}
    for name in ("evidence_relevance", "citation_support", "answer_correctness", "abstention", "uncertainty", "answerability_judgment"):
        values = {}
        for value in decisions.values():
            choice = value.get(name)
            if choice:
                values[choice] = values.get(choice, 0) + 1
        recorded = sum(values.values())
        criteria[name] = {
            "counts": values,
            "denominator": recorded,
            "substantive_denominator": recorded - values.get("not_assessable", 0) - values.get("not_applicable", 0),
            "excluded_missing": len(cases) - recorded,
            "not_assessable": values.get("not_assessable", 0),
            "not_applicable": values.get("not_applicable", 0),
        }
    result: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA,
        "source_run_id": capture.get("run_id"),
        "source_review_packet_fingerprint": review_packet.get("review_packet_fingerprint"),
        "reviewer_count": 1,
        "review_mode": "blinded_initial_judgment",
        "decision_counts": counts,
        "completed_cases": len(complete_ids),
        "incomplete_cases": len(cases) - len(complete_ids),
        "criteria": criteria,
        "limitations": [
            "Metrics summarize recorded human decisions and do not establish production accuracy.",
            "A single reviewer cannot support inter-rater reliability claims.",
            "The data is synthetic and provider configuration is run-specific.",
        ],
    }
    if ground_truth is not None:
        expected_by_id = {case["case_id"]: case for case in ground_truth.get("cases", [])}
        comparisons = {"agreement": 0, "label_disagreement": 0, "missing_expected_label": 0, "missing_reviewer_judgment": 0, "not_assessable": 0}
        agreement_by_label = {"answerable": 0, "unanswerable": 0}
        legacy_counts = {"answerable": 0, "unanswerable": 0, "not_assessable": 0, "missing": 0}
        for case in cases:
            case_id = case["case_id"]
            decision = decisions.get(case_id, {})
            expected = expected_by_id.get(case_id, {}).get("answerability")
            judgment = decision.get("answerability_judgment")
            if expected not in {"answerable", "unanswerable"}:
                comparisons["missing_expected_label"] += 1
                legacy_counts["not_assessable"] += 1
            elif not judgment:
                comparisons["missing_reviewer_judgment"] += 1
                legacy_counts["not_assessable"] += 1
            elif judgment == "not_assessable":
                comparisons["not_assessable"] += 1
                legacy_counts["not_assessable"] += 1
            elif judgment == expected:
                comparisons["agreement"] += 1
                agreement_by_label[expected] += 1
                legacy_counts[expected] += 1
            else:
                comparisons["label_disagreement"] += 1
                legacy_counts["missing"] += 1
        result["controlled_ground_truth_comparison"] = {
            "status": "post_judgment_only",
            "counts": comparisons,
            "agreement_by_label": agreement_by_label,
            "legacy_counts": legacy_counts,
            "interpretation": "Reviewer agreement with labels is not model accuracy. Retrieval evidence availability and investigation conclusion sufficiency are separate constructs.",
        }
    return result


def _resolved_output_path(path: Path) -> Path:
    return path.expanduser().resolve()


def write_json(path: Path, value: dict[str, Any], *, overwrite: bool = False) -> None:
    """Write JSON atomically without silently replacing evaluation evidence."""
    target = _resolved_output_path(path)
    if target in PROTECTED_ARTIFACTS:
        raise ValueError(f"Refusing to overwrite protected historical artifact: {target}")
    if target.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing output without --overwrite: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if target in PROTECTED_ARTIFACTS:
            raise ValueError(f"Refusing to overwrite protected historical artifact: {target}")
        if target.exists() and not overwrite:
            raise FileExistsError(f"Refusing to overwrite existing output without --overwrite: {target}")
        temporary.replace(target)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def capture_command(args: argparse.Namespace) -> int:
    packet = load_json(args.ground_truth)
    if packet_fingerprint(packet) != packet_fingerprint(load_json(GROUND_TRUTH_PACKET)):
        raise ValueError("The supplied packet does not match the canonical Phase 3 ground-truth packet.")
    os.environ.setdefault("AEGIS_DEPLOYMENT_PROFILE", args.profile)
    os.environ.setdefault("AEGIS_LLM", args.llm)
    from src.agents import run_investigation

    capture = capture_run(packet, invoke=run_investigation)
    output = args.output or DEFAULT_RESULTS / f"{capture['run_id']}.json"
    write_json(output, capture, overwrite=args.overwrite)
    review = build_blinded_review_packet(capture)
    review_output = args.review_output or output.with_name(f"{capture['run_id']}-review-packet.json")
    write_json(review_output, review, overwrite=args.overwrite)
    print(json.dumps({"capture": display_path(output), "review_packet": display_path(review_output), "cases": len(capture["cases"]), "completed": capture["execution"]["completed"], "failed": capture["execution"]["failed"]}, indent=2))
    return 0


def report_command(args: argparse.Namespace) -> int:
    capture = load_json(args.capture)
    review = load_json(args.review_packet)
    decision_payload = load_json(args.decisions)
    decisions = validate_decision_export(capture, review, decision_payload)
    ground_truth = load_json(args.ground_truth) if args.ground_truth else None
    report = report_decisions(capture, review, decisions, ground_truth)
    write_json(args.output, report, overwrite=args.overwrite)
    print(json.dumps({"report": display_path(args.output), "completed_cases": report["completed_cases"], "incomplete_cases": report["incomplete_cases"]}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture = subparsers.add_parser("capture")
    capture.add_argument("--ground-truth", type=Path, default=GROUND_TRUTH_PACKET)
    capture.add_argument("--output", type=Path)
    capture.add_argument("--review-output", type=Path)
    capture.add_argument("--overwrite", action="store_true", help="Replace an existing nonprotected output file.")
    capture.add_argument("--profile", choices=("lite", "standard"), default="lite")
    capture.add_argument("--llm", choices=("local", "gemini", "bedrock"), default="local")
    capture.set_defaults(func=capture_command)
    report = subparsers.add_parser("report")
    report.add_argument("--capture", type=Path, required=True)
    report.add_argument("--review-packet", type=Path, required=True)
    report.add_argument("--decisions", type=Path, required=True)
    report.add_argument("--ground-truth", type=Path)
    report.add_argument("--output", type=Path, required=True)
    report.add_argument("--overwrite", action="store_true", help="Replace an existing nonprotected output file.")
    report.set_defaults(func=report_command)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
