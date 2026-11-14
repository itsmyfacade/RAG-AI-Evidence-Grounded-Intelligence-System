"""Create a deterministic, human-reviewable Phase 3 ground-truth packet."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.benchmark_engine import benchmark_corpus_records, generate_cases  # noqa: E402


def build_packet(cases: list[dict], corpus: dict[str, dict], per_category: int = 5) -> dict:
    selected: list[dict] = []
    category_counts: dict[str, int] = defaultdict(int)
    by_category: dict[str, list[dict]] = defaultdict(list)
    for case in cases:
        by_category[case["category"]].append(case)
    for category in sorted(by_category):
        candidates = sorted(by_category[category], key=lambda item: (item["split"], item["difficulty"], item["case_id"]))
        seen_splits: set[str] = set()
        for case in candidates:
            if case["split"] not in seen_splits:
                selected.append(case)
                seen_splits.add(case["split"])
                category_counts[category] += 1
        for case in candidates:
            if category_counts[category] >= per_category:
                break
            if case not in selected:
                selected.append(case)
                category_counts[category] += 1

    reviewed_cases = []
    for case in selected:
        expected = [
            {"document_id": document_id, "title": corpus[document_id]["title"], "excerpt": corpus[document_id]["content"][:700]}
            for document_id in case["relevant_document_ids"]
        ]
        distractors = [
            {"document_id": document_id, "title": corpus[document_id]["title"], "excerpt": corpus[document_id]["content"][:500]}
            for document_id in case["distractor_document_ids"] if document_id in corpus
        ]
        rationale = (
            "Answerable label expects the cited evidence to address the stated intent and relationship."
            if case["expected_answerable"]
            else "Unanswerable label expects abstention because the question asks for proof not present in the available evidence."
        )
        reviewed_cases.append({
            "case_id": case["case_id"],
            "split": case["split"],
            "category": case["category"],
            "difficulty": case["difficulty"],
            "question": case["question"],
            "answerability": case["answerability"],
            "expected_evidence": expected,
            "expected_citation_ids": case["expected_citation_ids"],
            "potential_distractors": distractors,
            "review_rationale": rationale,
            "review_status": "pending_independent_human_review",
        })
    return {
        "schema_version": "aegis-phase3-review-packet-v1",
        "dataset_version": "aegis-phase2-v1",
        "selection": "five deterministic cases per category with split and answerability coverage where available",
        "independent_human_reviewed": False,
        "cases": reviewed_cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "data/evaluation/results/phase3-ground-truth-review-packet.json")
    args = parser.parse_args()
    packet = build_packet(generate_cases(), benchmark_corpus_records())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"path": args.output.relative_to(ROOT).as_posix(), "case_count": len(packet["cases"]), "human_reviewed": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
