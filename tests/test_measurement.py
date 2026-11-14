from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.measure_baseline import latency_summary, percentile, sha256_files


def test_percentile_is_interpolated_and_deterministic() -> None:
    values = [4.0, 1.0, 3.0, 2.0]
    assert percentile(values, 50) == 2.5
    assert percentile(values, 95) == pytest.approx(3.85)
    assert latency_summary(values)["p50_ms"] == 2500.0


def test_percentile_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="at least one"):
        percentile([], 50)
    with pytest.raises(ValueError, match="between"):
        percentile([1.0], 101)


def test_latency_summary_handles_empty_samples() -> None:
    assert latency_summary([]) == {"count": 0, "p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0, "mean_ms": 0.0}


def test_dataset_checksum_changes_when_content_changes(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(json.dumps({"value": 1}), encoding="utf-8")
    second.write_text(json.dumps({"value": 2}), encoding="utf-8")
    original = sha256_files([first, second])
    second.write_text(json.dumps({"value": 3}), encoding="utf-8")
    assert sha256_files([first, second]) != original


def test_baseline_fixture_is_compatible_with_existing_retriever() -> None:
    cases = json.loads(Path("data/evaluation/retrieval_cases.json").read_text(encoding="utf-8"))
    assert len(cases) == 5
    assert all(case["question"].strip() for case in cases)
    assert all(case["relevant_document_ids"] for case in cases)
