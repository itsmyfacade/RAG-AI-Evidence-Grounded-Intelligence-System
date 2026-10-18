"""Reproducible retrieval metrics; live embedding execution is opt-in via CLI."""

from __future__ import annotations

import json
from pathlib import Path


def reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
    for index, item in enumerate(retrieved, 1):
        if item in relevant:
            return 1 / index
    return 0.0


def evaluate_cases(cases: list[dict], retriever, k: int = 4) -> dict[str, float]:
    recalls, hits, mrrs, coverage = [], [], [], []
    for case in cases:
        relevant = set(case["relevant_document_ids"])
        results = retriever(case["question"], k=k)
        ids = [item.metadata["document_id"] for item in results]
        hits.append(float(bool(relevant & set(ids))))
        recalls.append(len(relevant & set(ids)) / max(len(relevant), 1))
        mrrs.append(reciprocal_rank(ids, relevant))
        required_categories = set(case.get("required_categories", []))
        actual_categories = {item.metadata.get("category") for item in results}
        coverage.append(len(required_categories & actual_categories) / max(len(required_categories), 1) if required_categories else 1.0)
    count = max(len(cases), 1)
    return {"Recall@k": sum(recalls) / count, "Hit@k": sum(hits) / count, "MRR": sum(mrrs) / count, "evidence_coverage": sum(coverage) / count}


if __name__ == "__main__":
    import argparse
    from src.rag import search
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=4)
    args = parser.parse_args()
    cases = json.loads((Path(__file__).resolve().parents[1] / "data" / "evaluation" / "retrieval_cases.json").read_text(encoding="utf-8"))
    print(json.dumps(evaluate_cases(cases, search, k=args.k), indent=2))
