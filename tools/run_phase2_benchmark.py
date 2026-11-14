"""Generate and evaluate the deterministic Phase 2 AEGIS benchmark."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.settings import get_settings  # noqa: E402
from tools.benchmark_engine import (  # noqa: E402
    DATASET_VERSION,
    GENERATION_SEED,
    evaluate_cases,
    generate_benchmark_corpus,
    generate_cases,
    sha256_path,
    validate_cases,
)  # noqa: E402
from tools.measure_baseline import (  # noqa: E402
    git_commit,
    latency_summary,
    process_memory_bytes,
    sha256_files,
)  # noqa: E402

DEFAULT_OUTPUT = ROOT / "data" / "evaluation" / "results" / "phase2-expanded-cases.json"
DEFAULT_RESULT_OUTPUT = ROOT / "data" / "evaluation" / "results" / "phase2-expanded-result.json"


def summary_markdown(result: dict) -> str:
    validation = result["validation"]
    retrieval = result["evaluation"]["overall"]
    latency = result["runtime"]["retrieval_latency"]
    lines = [
        "# AEGIS retrieval benchmark",
        "",
        f"- Dataset version: `{result['dataset_version']}`",
        f"- Git commit: `{result.get('git_commit') or 'unavailable'}`",
        f"- Cases: `{validation['case_count']}`",
        f"- Documents: `{validation['document_count']}`",
        f"- Split counts: `{validation['split_counts']}`",
        f"- Category counts: `{validation['category_counts']}`",
        f"- Difficulty counts: `{validation['difficulty_counts']}`",
        f"- Retrieval profile: `{result['environment'].get('retrieval_profile', 'legacy')}`",
        f"- Retrieval abstention: `{result['environment'].get('retrieval_abstention', False)}`",
        "",
        "## Overall retrieval",
        "",
    ]
    for name in ("recall_at_1", "recall_at_4", "recall_at_5", "recall_at_8", "hit_at_1", "hit_at_4", "hit_at_5", "hit_at_8", "mrr", "ndcg_at_5", "evidence_coverage", "correct_abstention", "false_answer"):
        metric = retrieval.get(name)
        if metric:
            interval = metric["confidence_interval_95"]
            lines.append(f"- {name}: `{metric['value']}` over `{metric['defined_cases']}` cases, 95% CI `{interval['low']}` to `{interval['high']}`")
    lines.extend(
        [
            "",
            "## Runtime",
            "",
            f"- Evaluation runtime: `{result['runtime']['evaluation_seconds']} seconds`",
            f"- Retrieval p50/p95/p99: `{latency['p50_ms']}/{latency['p95_ms']}/{latency['p99_ms']} ms`",
            f"- Process working set before/after: `{result['runtime']['memory_before']['working_set_bytes']}/{result['runtime']['memory_after']['working_set_bytes']} bytes`",
            "",
            "The benchmark uses deterministic synthetic labels generated from the current corpus. The quality-audit sample has not received independent human review, so these results are evaluation evidence rather than production accuracy claims.",
            "",
        ]
    )
    return "\n".join(lines)


def run(output: Path, audit_output: Path, summary_output: Path, result_output: Path, latency_samples: int) -> dict:
    os.environ["AEGIS_DEPLOYMENT_PROFILE"] = "lite"
    os.environ["AEGIS_LLM"] = "local"
    os.environ["AEGIS_EMBEDDINGS"] = "local"
    os.environ["AEGIS_EMBEDDING_LOCAL_FILES_ONLY"] = "true"

    cases = generate_cases()
    corpus_output = output.parent / "phase2-benchmark-corpus"
    documents = generate_benchmark_corpus(corpus_output)
    validation = validate_cases(cases, documents)
    if not validation["valid"]:
        raise ValueError(json.dumps(validation, indent=2))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(cases, indent=2) + "\n", encoding="utf-8")

    audit_cases = []
    category_seen: dict[str, int] = {}
    for case in cases:
        category_seen.setdefault(case["category"], 0)
        if category_seen[case["category"]] < 5:
            audit_cases.append(case)
            category_seen[case["category"]] += 1
    audit_payload = {
        "dataset_version": DATASET_VERSION,
        "generation_seed": GENERATION_SEED,
        "review_status": "not_independently_human_reviewed",
        "sample_method": "first five deterministic cases per category after seeded generation",
        "cases": audit_cases,
    }
    audit_output.write_text(json.dumps(audit_payload, indent=2) + "\n", encoding="utf-8")

    from src.rag import search

    os.environ["AEGIS_DATASET_PATH"] = str(corpus_output)

    memory_before = process_memory_bytes()
    started = time.perf_counter()
    evaluation = evaluate_cases(cases, search)
    evaluation_seconds = time.perf_counter() - started
    retrieval_times = []
    for index in range(max(1, latency_samples)):
        question = cases[index % len(cases)]["question"]
        request_started = time.perf_counter()
        search(question, k=8)
        retrieval_times.append(time.perf_counter() - request_started)
    memory_after = process_memory_bytes()
    dataset_checksum = sha256_path(output)
    corpus_checksum = sha256_files(list(corpus_output.glob("*.json")))
    result = {
        "schema_version": "aegis-phase2-benchmark-v1",
        "dataset_version": DATASET_VERSION,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_commit": git_commit(),
        "generation_seed": GENERATION_SEED,
        "dataset_path": output.relative_to(ROOT).as_posix(),
        "corpus_path": corpus_output.relative_to(ROOT).as_posix(),
        "dataset_checksum": dataset_checksum,
        "corpus_checksum": corpus_checksum,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "deployment_profile": "lite",
            "retrieval_mode": "lexical",
            "retrieval_profile": get_settings().retrieval_profile,
            "retrieval_abstention": get_settings().retrieval_abstention,
            "retrieval_abstention_threshold": get_settings().retrieval_abstention_threshold,
            "llm_mode": "local",
        },
        "validation": validation,
        "quality_audit": {
            "path": audit_output.relative_to(ROOT).as_posix(),
            "sample_count": len(audit_cases),
            "independent_human_reviewed": False,
        },
        "evaluation": evaluation,
        "runtime": {
            "evaluation_seconds": round(evaluation_seconds, 6),
            "retrieval_latency": latency_summary(retrieval_times),
            "retrieval_latency_samples": len(retrieval_times),
            "memory_before": memory_before,
            "memory_after": memory_after,
            "errors": 0,
            "timeouts": 0,
        },
        "reproduction": {
            "command": "python tools/run_phase2_benchmark.py --output data/evaluation/results/phase2-expanded-cases.json --audit-output data/evaluation/results/phase2-quality-audit.json --summary data/evaluation/results/phase2-expanded-summary.md",
            "provider_calls": "none; deterministic local mode",
        },
        "limitations": [
            "The generated labels are deterministic ontology labels and have not received independent human review.",
            "The benchmark corpus contains the original 30 documents plus 60 generated documents; evidence families are reused across splits, so full corpus independence is limited.",
            "The benchmark measures lite lexical retrieval, not production diagnosis accuracy or semantic entailment.",
            "Citation precision and recall are not claimed for generated answers in this retrieval-only phase.",
        ],
        "abstention_calibration": {
            "method": "fixed score threshold selected from development and validation score trade-offs; held-out cases were not used for selection",
            "threshold": get_settings().retrieval_abstention_threshold,
            "selection_splits": ["development", "validation"],
            "human_review_required": True,
        },
    }
    summary_output.write_text(summary_markdown(result), encoding="utf-8")
    result_output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--audit-output", type=Path, default=DEFAULT_OUTPUT.with_name("phase2-quality-audit.json"))
    parser.add_argument("--summary", type=Path, default=DEFAULT_OUTPUT.with_name("phase2-expanded-summary.md"))
    parser.add_argument("--result-output", type=Path, default=DEFAULT_RESULT_OUTPUT)
    parser.add_argument("--latency-samples", type=int, default=100)
    args = parser.parse_args()
    if args.latency_samples < 1:
        parser.error("--latency-samples must be positive")
    result = run(args.output.resolve(), args.audit_output.resolve(), args.summary.resolve(), args.result_output.resolve(), args.latency_samples)
    print(json.dumps({key: result[key] for key in ("schema_version", "dataset_checksum", "corpus_checksum", "validation", "runtime")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
