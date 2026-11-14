from __future__ import annotations

from tools.benchmark_engine import (
    CATEGORY_TARGETS,
    SPLIT_TARGETS,
    bootstrap_ci,
    evaluate_cases,
    generate_cases,
    normalize_question,
    validate_cases,
)


def test_generation_is_deterministic_and_balanced() -> None:
    first = generate_cases()
    second = generate_cases()
    assert first == second
    validation = validate_cases(first)
    assert validation["valid"] is True
    assert validation["case_count"] == 1200
    assert validation["category_counts"] == CATEGORY_TARGETS
    assert validation["split_counts"] == SPLIT_TARGETS


def test_questions_do_not_expose_document_ids_or_duplicate_normalized_text() -> None:
    cases = generate_cases()
    normalized = [normalize_question(case["question"]) for case in cases]
    assert len(normalized) == len(set(normalized))
    assert all("API-001" not in case["question"] for case in cases)
    assert all(case["question"].strip() for case in cases)


def test_ground_truth_contains_existing_evidence_relationships() -> None:
    validation = validate_cases(generate_cases())
    assert validation["errors"] == []
    assert validation["answerable_count"] > 0
    assert validation["unanswerable_count"] > 0


def test_bootstrap_is_reproducible_and_handles_empty_values() -> None:
    assert bootstrap_ci([])["low"] is None
    assert bootstrap_ci([0.0, 1.0], seed=10) == bootstrap_ci([0.0, 1.0], seed=10)


def test_metrics_handle_answerable_and_unanswerable_cases() -> None:
    cases = [
        {
            "case_id": "A",
            "question": "answerable",
            "relevant_document_ids": ["DOC-1"],
            "expected_answerable": True,
            "relevance": {"DOC-1": 3},
            "split": "development",
            "category": "test",
            "difficulty": "introductory",
        },
        {
            "case_id": "U",
            "question": "unanswerable",
            "relevant_document_ids": [],
            "expected_answerable": False,
            "relevance": {},
            "split": "development",
            "category": "test",
            "difficulty": "introductory",
        },
    ]

    class Result:
        def __init__(self, document_id: str) -> None:
            self.metadata = {"document_id": document_id}

    result = evaluate_cases(cases, lambda question, k: [Result("DOC-1")] if question == "answerable" else [])
    assert result["overall"]["recall_at_1"]["value"] == 1.0
    assert result["overall"]["hit_at_1"]["value"] == 1.0
    assert result["overall"]["correct_abstention"]["value"] == 1.0
    assert result["overall"]["false_answer"]["value"] == 0.0
