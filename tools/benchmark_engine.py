"""Deterministic Phase 2 benchmark generation, validation, and metrics."""

from __future__ import annotations

import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
DATASET_VERSION = "aegis-phase2-v1"
GENERATOR_VERSION = "template-ontology-v1"
GENERATION_SEED = 20261114
SPLIT_TARGETS = {"development": 700, "validation": 200, "held_out": 300}
CATEGORY_TARGETS = {
    "api_authentication": 180,
    "incidents_failures": 180,
    "runbooks_operations": 150,
    "data_etl": 150,
    "security": 150,
    "architecture": 120,
    "mixed_source": 150,
    "ambiguous_insufficient": 120,
}
DIFFICULTIES = ("introductory", "intermediate", "advanced")
ID_PATTERN = re.compile(r"\b(?:API|INC|RUN|DATA|SEC|ARCH)-\d{3}\b", re.IGNORECASE)
STOPWORDS = {"about", "after", "available", "during", "evidence", "for", "from", "into", "review", "the", "this", "when", "while", "with"}


def _ids(prefix: str, count: int = 10) -> list[str]:
    return [f"B{prefix}-{index:03d}" for index in range(1, count + 1)]

SPECS: dict[str, dict[str, Any]] = {
    "api_authentication": {
        "documents": _ids("API"),
        "intents": [
            "distinguishing authentication failure from authorization denial",
            "handling request throttling and retry timing",
            "reasoning about cursor-based pagination",
            "preserving a structured API error contract",
        ],
    },
    "incidents_failures": {
        "documents": _ids("INC"),
        "intents": [
            "correlating an incident with a recent deployment",
            "separating observed symptoms from a documented cause",
            "identifying evidence that supports a failure hypothesis",
            "deciding when the available evidence is insufficient",
        ],
    },
    "runbooks_operations": {
        "documents": _ids("RUN"),
        "intents": [
            "triaging an API incident using correlation identifiers",
            "investigating webhook delivery and acknowledgement records",
            "reconciling source and destination data counts",
            "handling a suspected credential compromise",
        ],
    },
    "data_etl": {
        "documents": _ids("DATA"),
        "intents": [
            "checking ETL reconciliation across pipeline stages",
            "investigating missing or delayed records",
            "using metadata for traceability and filtering",
            "distinguishing legitimate retries from duplicate business records",
        ],
    },
    "security": {
        "documents": _ids("SEC"),
        "intents": [
            "applying least-privilege access controls",
            "handling secrets outside source control",
            "preserving useful audit-log fields without exposing sensitive data",
            "treating retrieved documents as untrusted inputs",
        ],
    },
    "architecture": {
        "documents": _ids("ARCH"),
        "intents": [
            "tracing a partner request through integrated services",
            "explaining authentication and authorization boundaries",
            "following operational data through ingestion and reporting",
            "locating correlation identifiers in a distributed workflow",
        ],
    },
    "mixed_source": {
        "documents": ["BAPI-001", "BINC-001", "BRUN-001", "BDATA-001", "BSEC-001", "BARCH-001"],
        "intents": [
            "combining API documentation with incident evidence",
            "correlating operational records with a runbook procedure",
            "connecting a security policy to an observed authorization failure",
            "reconciling architecture, deployment, and data evidence",
        ],
    },
    "ambiguous_insufficient": {
        "documents": ["BAPI-001", "BINC-001", "BRUN-001", "BDATA-001", "BSEC-001", "BARCH-001"],
        "intents": [
            "confirming a production root cause when only symptoms are available",
            "determining an exact customer impact without matching operational records",
            "proving that a deployment caused an unrelated failure",
            "identifying a credential value from sanitized evidence",
        ],
    },
}

SPLIT_PREFIXES = {
    "development": ("During an engineering investigation", "Review the available evidence and do not assume the root cause."),
    "validation": ("For a validation review", "Separate observations, documented guidance, and unsupported assumptions."),
    "held_out": ("In a new incident-analysis exercise", "Decide what the evidence supports and identify any missing proof."),
}
VARIANTS = (
    "after a configuration change",
    "during a release review",
    "while comparing successful and failing requests",
    "when examining a delayed operational record",
    "during an evidence handoff",
    "after a partner reports inconsistent behavior",
    "while checking timestamps and correlation identifiers",
    "when a runbook recommendation conflicts with an observed record",
)


def normalize_question(question: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", question.lower())).strip()


BENCHMARK_DOCUMENT_SPECS = {
    "api": ("BAPI", "API integration control", "API authentication, authorization, error handling, throttling, and request traceability."),
    "incident": ("BINC", "Operational incident", "Incident investigation requires symptom, timing, deployment, request, and downstream evidence before assigning a cause."),
    "runbook": ("BRUN", "Operations runbook", "Operational response should preserve correlation identifiers, compare successful and failed records, and document follow-up checks."),
    "data": ("BDATA", "Data reconciliation procedure", "Data workflows should compare source counts, transformations, destination records, duplicates, nulls, and schema versions."),
    "security": ("BSEC", "Security engineering control", "Security controls require least privilege, secret redaction, auditability, and careful treatment of retrieved content."),
    "architecture": ("BARCH", "Integration architecture note", "Distributed integrations connect gateways, services, queues, storage, and observability through stable contracts and correlation IDs."),
}


def corpus_records(documents_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    directory = documents_dir or ROOT / "data" / "documents"
    records = {}
    for path in sorted(directory.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        records[str(record["document_id"])] = record
    return records


def benchmark_corpus_records() -> dict[str, dict[str, Any]]:
    records = corpus_records()
    spec_by_category = {
        "api": "api_authentication",
        "incident": "incidents_failures",
        "runbook": "runbooks_operations",
        "data": "data_etl",
        "security": "security",
        "architecture": "architecture",
    }
    for category, (prefix, title_prefix, base_content) in BENCHMARK_DOCUMENT_SPECS.items():
        for index in range(1, 11):
            document_id = f"{prefix}-{index:03d}"
            spec = SPECS[spec_by_category[category]]
            intent = spec["intents"][(index - 1) % len(spec["intents"])]
            records[document_id] = {
                "document_id": document_id,
                "title": f"{title_prefix} {index:02d}: {intent}",
                "category": category,
                "version": f"{1 + (index % 3)}.{index % 10}",
                "classification": "synthetic-benchmark",
                "content": (
                    f"{base_content} This document addresses {intent}. Benchmark variant {index:02d} covers a distinct evidence family, "
                    f"service boundary, timestamp sequence, and verification path. Engineers should compare "
                    f"observed records with the documented contract for variant {index:02d}."
                ),
            }
    return records


def generate_benchmark_corpus(output_dir: Path) -> dict[str, dict[str, Any]]:
    records = benchmark_corpus_records()
    output_dir.mkdir(parents=True, exist_ok=True)
    for document_id, record in records.items():
        (output_dir / f"{document_id}.json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8"
        )
    return records


def _difficulty(index: int) -> str:
    return DIFFICULTIES[index % len(DIFFICULTIES)]


def _build_case(category: str, index: int, answerable: bool) -> dict[str, Any]:
    spec = SPECS[category]
    intent_index = index % len(spec["intents"])
    intent = spec["intents"][intent_index]
    question_body = f"{intent} {VARIANTS[index % len(VARIANTS)]} in evidence thread {index + 1:04d}"
    if answerable:
        relevant = [spec["documents"][intent_index % len(spec["documents"])]
                    ]
        if category == "mixed_source":
            relevant = [spec["documents"][intent_index % len(spec["documents"])]
                        , spec["documents"][(intent_index + 1) % len(spec["documents"])]
                        ]
        if category == "incidents_failures" and index % 3 == 0:
            relevant.append(spec["documents"][(intent_index + 2) % len(spec["documents"])] )
        relevant = list(dict.fromkeys(relevant))
        return {
            "question_body": question_body,
            "relevant_document_ids": relevant,
            "expected_citation_ids": relevant,
            "expected_answerable": True,
            "answerability": "answerable",
            "relevance": {doc_id: max(1, 3 - position) for position, doc_id in enumerate(relevant)},
        }
    return {
        "question_body": question_body,
        "relevant_document_ids": [],
        "expected_citation_ids": [],
        "expected_answerable": False,
        "answerability": "unanswerable",
        "relevance": {},
    }


def generate_cases() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    index = 0
    for category, count in CATEGORY_TARGETS.items():
        for _ in range(count):
            answerable = category != "ambiguous_insufficient"
            label = _build_case(category, index, answerable)
            records.append(
                {
                    "case_id": f"RET-{index + 1:04d}",
                    "dataset_version": DATASET_VERSION,
                    "generator_version": GENERATOR_VERSION,
                    "category": category,
                    "difficulty": _difficulty(index),
                    "question_body": label.pop("question_body"),
                    **label,
                    "generation_seed": GENERATION_SEED,
                    "template_family_id": f"{category}-family-{index % len(SPECS[category]['intents'])}",
                    "ground_truth_provenance": {
                        "label_method": "deterministic_template_ontology_v1",
                        "source_document_ids": SPECS[category]["documents"],
                        "independently_reviewed": False,
                    },
                }
            )
            index += 1

    random.Random(GENERATION_SEED).shuffle(records)
    split_sequence = ["development"] * SPLIT_TARGETS["development"]
    split_sequence += ["validation"] * SPLIT_TARGETS["validation"]
    split_sequence += ["held_out"] * SPLIT_TARGETS["held_out"]
    for record, split in zip(records, split_sequence, strict=True):
        record["split"] = split
        record["template_family_id"] = f"{split}:{record['category']}:{record['template_family_id'].rsplit(':', 1)[-1]}"
        prefix, closing = SPLIT_PREFIXES[split]
        record["question"] = f"{prefix}, {record.pop('question_body')}. {closing}"
        relevant = record["relevant_document_ids"]
        record["expected_evidence_relationships"] = [
            {"document_id": doc_id, "relationship": "primary" if position == 0 else "supporting"}
            for position, doc_id in enumerate(relevant)
        ]
        record["distractor_document_ids"] = [
            doc_id for doc_id in SPECS[record["category"]]["documents"] if doc_id not in relevant
        ][:2]
    return records


def validate_cases(cases: list[dict[str, Any]], documents: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    corpus = documents or benchmark_corpus_records()
    errors: list[str] = []
    ids = [case.get("case_id") for case in cases]
    normalized = [normalize_question(str(case.get("question", ""))) for case in cases]
    if len(cases) != sum(CATEGORY_TARGETS.values()):
        errors.append(f"expected 1200 cases, found {len(cases)}")
    if len(ids) != len(set(ids)):
        errors.append("duplicate case IDs")
    if len(normalized) != len(set(normalized)):
        errors.append("duplicate normalized questions")
    category_counts = Counter(case.get("category") for case in cases)
    split_counts = Counter(case.get("split") for case in cases)
    for category, expected in CATEGORY_TARGETS.items():
        if category_counts[category] != expected:
            errors.append(f"category {category}: expected {expected}, found {category_counts[category]}")
    for split, expected in SPLIT_TARGETS.items():
        if split_counts[split] != expected:
            errors.append(f"split {split}: expected {expected}, found {split_counts[split]}")
    family_by_split = defaultdict(set)
    for case in cases:
        family_by_split[case.get("split")].add(case.get("template_family_id"))
        question = str(case.get("question", ""))
        if not question.strip() or ID_PATTERN.search(question):
            errors.append(f"answer-bearing or empty question: {case.get('case_id')}")
        if case.get("difficulty") not in DIFFICULTIES:
            errors.append(f"invalid difficulty: {case.get('case_id')}")
        relevant = set(case.get("relevant_document_ids", []))
        citations = set(case.get("expected_citation_ids", []))
        relationships = {item.get("document_id") for item in case.get("expected_evidence_relationships", [])}
        if not relevant <= set(corpus):
            errors.append(f"missing relevant document: {case.get('case_id')}")
        if not citations <= relevant or relationships != relevant:
            errors.append(f"ground-truth relationship mismatch: {case.get('case_id')}")
        if case.get("expected_answerable") != bool(relevant):
            errors.append(f"answerability mismatch: {case.get('case_id')}")
        if relevant:
            question_terms = {
                token for token in re.findall(r"[a-z]{4,}", str(case.get("question", "")).lower())
                if token not in STOPWORDS
            }
            evidence_text = " ".join(str(corpus[doc_id].get("content", "")).lower() for doc_id in relevant)
            evidence_terms = set(re.findall(r"[a-z]{4,}", evidence_text))
            if not question_terms & evidence_terms:
                errors.append(f"ground truth has no textual support: {case.get('case_id')}")
    splits = list(family_by_split.values())
    for left_index, left in enumerate(splits):
        for right in splits[left_index + 1:]:
            if left & right:
                errors.append("template family leakage across splits")
    return {
        "valid": not errors,
        "errors": errors,
        "case_count": len(cases),
        "category_counts": dict(sorted(category_counts.items())),
        "split_counts": dict(sorted(split_counts.items())),
        "difficulty_counts": dict(sorted(Counter(case.get("difficulty") for case in cases).items())),
        "answerable_count": sum(bool(case.get("expected_answerable")) for case in cases),
        "unanswerable_count": sum(not bool(case.get("expected_answerable")) for case in cases),
        "document_count": len(corpus),
    }


def bootstrap_ci(values: list[float], seed: int = GENERATION_SEED, samples: int = 1000) -> dict[str, float | int | None]:
    if not values:
        return {"defined_cases": 0, "samples": samples, "low": None, "high": None}
    rng = random.Random(seed)
    means = [sum(rng.choice(values) for _ in values) / len(values) for _ in range(samples)]
    means.sort()
    low = means[int(samples * 0.025)]
    high = means[min(int(samples * 0.975), samples - 1)]
    return {"defined_cases": len(values), "samples": samples, "low": round(low, 6), "high": round(high, 6)}


def _ndcg(retrieved: list[str], relevance: dict[str, int], k: int) -> float | None:
    if not relevance:
        return None
    import math

    def gain(rank: int, score: int) -> float:
        return (2**score - 1) / math.log2(rank + 1)

    actual = sum(gain(rank, relevance[doc_id]) for rank, doc_id in enumerate(retrieved[:k], 1) if doc_id in relevance)
    ideal = sum(gain(rank, score) for rank, score in enumerate(sorted(relevance.values(), reverse=True)[:k], 1))
    return actual / ideal if ideal else None


def evaluate_cases(cases: list[dict[str, Any]], retriever: Callable[[str, int], list[Any]], k_values: tuple[int, ...] = (1, 4, 5, 8)) -> dict[str, Any]:
    per_case: list[dict[str, Any]] = []
    for case in cases:
        results = retriever(case["question"], k=max(k_values))
        ids = [item.metadata["document_id"] for item in results]
        relevant = set(case["relevant_document_ids"])
        metrics: dict[str, float | None] = {}
        for k in k_values:
            top = ids[:k]
            if relevant:
                overlap = relevant & set(top)
                metrics[f"recall_at_{k}"] = len(overlap) / len(relevant)
                metrics[f"precision_at_{k}"] = len(overlap) / len(top) if top else 0.0
                metrics[f"hit_at_{k}"] = float(bool(overlap))
                metrics[f"ndcg_at_{k}"] = _ndcg(top, case["relevance"], k)
            else:
                metrics[f"recall_at_{k}"] = None
                metrics[f"precision_at_{k}"] = None
                metrics[f"hit_at_{k}"] = None
                metrics[f"ndcg_at_{k}"] = None
        rank = next((position for position, doc_id in enumerate(ids, 1) if doc_id in relevant), None)
        metrics["mrr"] = 1 / rank if rank else (None if not relevant else 0.0)
        metrics["evidence_coverage"] = (
            len(relevant & set(ids)) / len(relevant) if relevant else None
        )
        predicted_answerable = bool(ids)
        metrics["correct_abstention"] = float(not predicted_answerable) if not relevant else None
        metrics["false_answer"] = float(predicted_answerable) if not relevant else None
        per_case.append({"case_id": case["case_id"], "metrics": metrics, "retrieved_ids": ids})

    def aggregate(items: list[dict[str, Any]]) -> dict[str, Any]:
        names = sorted({name for item in items for name in item["metrics"]})
        output: dict[str, Any] = {}
        for name in names:
            values = [item["metrics"][name] for item in items if item["metrics"][name] is not None]
            output[name] = {
                "value": round(sum(values) / len(values), 6) if values else None,
                "defined_cases": len(values),
                "total_cases": len(items),
                "confidence_interval_95": bootstrap_ci(values, seed=GENERATION_SEED + len(name)),
            }
        return output

    groups: dict[str, dict[str, list[dict[str, Any]]]] = {"overall": {"all": per_case}}
    for field in ("split", "category", "difficulty"):
        groups[field] = defaultdict(list)
        by_id = {case["case_id"]: case for case in cases}
        for item in per_case:
            groups[field][by_id[item["case_id"]][field]].append(item)
    return {
        "overall": aggregate(per_case),
        "by_split": {key: aggregate(value) for key, value in sorted(groups["split"].items())},
        "by_category": {key: aggregate(value) for key, value in sorted(groups["category"].items())},
        "by_difficulty": {key: aggregate(value) for key, value in sorted(groups["difficulty"].items())},
        "per_case": per_case,
        "methodology": {
            "retrieval_metrics": "Case-level macro averages; undefined negative-case retrieval metrics are excluded from their denominators.",
            "precision": "Relevant retrieved IDs divided by retrieved IDs at k; zero when no results exist for answerable cases.",
            "mrr": "Reciprocal rank of the first relevant document; zero when answerable but no relevant document is retrieved.",
            "ndcg": "Graded relevance from the case relevance map; undefined for unanswerable cases.",
            "abstention": "Retrieval abstention proxy based on whether any document was returned, not generated-answer correctness.",
            "citation": "Citation precision and recall are not claimed because this phase evaluates retrieval IDs, not generated responses.",
            "bootstrap": "1,000 deterministic case-level resamples using the generation seed plus metric-name offset.",
        },
    }


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
