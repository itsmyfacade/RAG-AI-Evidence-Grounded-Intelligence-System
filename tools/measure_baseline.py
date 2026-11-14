"""Local Phase 1 baseline measurements for AEGIS.

This tool intentionally stays outside the serving path. It exercises the existing
lite-profile retrieval and investigation functions and writes reproducible JSON
and Markdown artifacts under the ignored evaluation-results directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA_VERSION = "aegis-baseline-v1"
DEFAULT_CASES = ROOT / "data" / "evaluation" / "retrieval_cases.json"


def percentile(values: list[float], percentage: float) -> float:
    """Return a linearly interpolated percentile for a non-empty sample."""
    if not values:
        raise ValueError("percentile requires at least one value")
    if not 0 <= percentage <= 100:
        raise ValueError("percentage must be between 0 and 100")
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentage / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def latency_summary(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"count": 0, "p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0, "mean_ms": 0.0}
    milliseconds = [value * 1000 for value in values]
    return {
        "count": len(milliseconds),
        "p50_ms": round(percentile(milliseconds, 50), 3),
        "p95_ms": round(percentile(milliseconds, 95), 3),
        "p99_ms": round(percentile(milliseconds, 99), 3),
        "mean_ms": round(statistics.fmean(milliseconds), 3),
    }


def sha256_files(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def process_memory_bytes() -> dict[str, int | None]:
    """Return process working-set metrics without adding a dependency."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(Counters),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        process = kernel32.GetCurrentProcess()
        ok = psapi.GetProcessMemoryInfo(
            process, ctypes.byref(counters), counters.cb
        )
        if ok:
            return {
                "working_set_bytes": int(counters.WorkingSetSize),
                "peak_working_set_bytes": int(counters.PeakWorkingSetSize),
            }
    return {"working_set_bytes": None, "peak_working_set_bytes": None}


def timed(function: Callable[[], Any]) -> tuple[Any, float]:
    started = time.perf_counter()
    result = function()
    return result, time.perf_counter() - started


def load_cases(path: Path) -> list[dict[str, Any]]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, list) or not loaded:
        raise ValueError(f"evaluation fixture must be a non-empty list: {path}")
    return loaded


def run_measurement(case_path: Path, warm_samples: int) -> dict[str, Any]:
    os.environ.setdefault("AEGIS_DEPLOYMENT_PROFILE", "lite")
    os.environ.setdefault("AEGIS_LLM", "local")
    os.environ.setdefault("AEGIS_EMBEDDINGS", "local")
    os.environ.setdefault("AEGIS_EMBEDDING_LOCAL_FILES_ONLY", "true")

    from src.agents import run_investigation
    from src.dataset import validate_database
    from src.rag import search
    from src.retrieval_eval import evaluate_cases
    from src.settings import get_settings
    from src.startup import ensure_resources

    configuration = get_settings()
    if configuration.deployment_profile != "lite" or configuration.llm_mode != "local":
        raise ValueError("Phase 1 baseline requires AEGIS_DEPLOYMENT_PROFILE=lite and AEGIS_LLM=local")
    document_paths = list(configuration.dataset_path.glob("*.json"))
    checksum_paths = [*document_paths, case_path]
    memory_before = process_memory_bytes()
    tracemalloc.start()

    _, initialization_seconds = timed(ensure_resources)
    _, retrieval_cold_seconds = timed(lambda: search("HTTP 403 after deployment", k=4))

    retrieval_samples: list[float] = []
    for index in range(max(warm_samples, 1)):
        question = "HTTP 403 after deployment" if index % 2 == 0 else "reconcile data mismatch"
        _, elapsed = timed(lambda question=question: search(question, k=4))
        retrieval_samples.append(elapsed)

    evaluation, evaluation_seconds = timed(
        lambda: evaluate_cases(load_cases(case_path), search, k=4)
    )

    cases = load_cases(case_path)
    e2e_samples: list[float] = []
    e2e_errors = 0
    for case in cases:
        try:
            _, elapsed = timed(
                lambda case=case: run_investigation(case["question"], scenario_id="SCN-001")
            )
            e2e_samples.append(elapsed)
        except (OSError, RuntimeError, TypeError, ValueError):
            e2e_errors += 1

    def investigate_once() -> bool:
        run_investigation(cases[0]["question"], scenario_id="SCN-001")
        return True

    concurrency_started = time.perf_counter()
    concurrency_errors = 0
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(investigate_once) for _ in range(2)]
        for future in futures:
            try:
                future.result(timeout=60)
            except (OSError, RuntimeError, TypeError, TimeoutError, ValueError):
                concurrency_errors += 1
    concurrency_seconds = time.perf_counter() - concurrency_started

    current_allocations, peak_allocations = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    memory_after = process_memory_bytes()

    return {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "profile": configuration.deployment_profile,
            "retrieval_mode": "lexical",
            "llm_mode": configuration.llm_mode,
            "embeddings_mode": configuration.embeddings_mode,
        },
        "dataset": {
            "evaluation_fixture": case_path.relative_to(ROOT).as_posix(),
            "evaluation_cases": len(cases),
            "document_count": len(document_paths),
            "sha256": sha256_files(checksum_paths),
            "database_validation": validate_database(configuration.database_path),
        },
        "methodology": {
            "timer": "time.perf_counter",
            "retrieval_cold": "first lite lexical search after resource initialization",
            "retrieval_warm_samples": warm_samples,
            "end_to_end_samples": len(cases),
            "provider": "deterministic local mode",
            "concurrency_workers": 2,
            "timeout_seconds": 60,
        },
        "initialization": {"seconds": round(initialization_seconds, 6)},
        "retrieval": {
            "cold_start_seconds": round(retrieval_cold_seconds, 6),
            "warm_latency": latency_summary(retrieval_samples),
            "evaluation_seconds": round(evaluation_seconds, 6),
            "metrics": evaluation,
        },
        "end_to_end": {
            "latency": latency_summary(e2e_samples),
            "failed_requests": e2e_errors,
            "timeouts": 0,
        },
        "concurrency": {
            "workers": 2,
            "wall_seconds": round(concurrency_seconds, 6),
            "failed_requests": concurrency_errors,
            "timeouts": 0,
        },
        "memory": {
            "process_before": memory_before,
            "process_after": memory_after,
            "tracemalloc_current_bytes": current_allocations,
            "tracemalloc_peak_bytes": peak_allocations,
        },
        "limitations": [
            "This is a local deterministic lite-profile measurement.",
            "It is not a Render measurement.",
            "It does not measure external provider latency or semantic vector retrieval.",
            "The evaluation fixture is the existing five-case synthetic baseline.",
        ],
    }


def markdown_summary(result: dict[str, Any]) -> str:
    retrieval = result["retrieval"]
    warm = retrieval["warm_latency"]
    end_to_end = result["end_to_end"]["latency"]
    memory = result["memory"]
    lines = [
        "# AEGIS Phase 1 baseline measurement",
        "",
        f"- Schema: `{result['schema_version']}`",
        f"- Commit: `{result.get('git_commit') or 'unavailable'}`",
        f"- Profile: `{result['environment']['profile']}`",
        f"- Retrieval mode: `{result['environment']['retrieval_mode']}`",
        f"- Evaluation cases: `{result['dataset']['evaluation_cases']}`",
        "",
        "## Retrieval",
        "",
        f"- Cold start: `{retrieval['cold_start_seconds']} seconds`",
        f"- Warm p50/p95/p99: `{warm['p50_ms']}/{warm['p95_ms']}/{warm['p99_ms']} ms`",
        f"- Recall@4: `{retrieval['metrics']['Recall@k']:.4f}`",
        f"- Hit@4: `{retrieval['metrics']['Hit@k']:.4f}`",
        f"- MRR: `{retrieval['metrics']['MRR']:.4f}`",
        f"- Evidence coverage: `{retrieval['metrics']['evidence_coverage']:.4f}`",
        "",
        "## End to end",
        "",
        f"- p50/p95/p99: `{end_to_end['p50_ms']}/{end_to_end['p95_ms']}/{end_to_end['p99_ms']} ms`",
        f"- Failed requests: `{result['end_to_end']['failed_requests']}`",
        f"- Concurrent failures: `{result['concurrency']['failed_requests']}`",
        "",
        "## Memory",
        "",
        f"- Working set before/after: `{memory['process_before']['working_set_bytes']}/{memory['process_after']['working_set_bytes']} bytes`",
        f"- Tracemalloc peak: `{memory['tracemalloc_peak_bytes']} bytes`",
        "",
        "These results are local deterministic measurements against the existing synthetic five-case fixture. They are not production accuracy or hosted performance claims.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-file", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--warm-samples", type=int, default=20)
    args = parser.parse_args()
    if args.warm_samples < 1:
        parser.error("--warm-samples must be positive")
    result = run_measurement(args.case_file.resolve(), args.warm_samples)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    args.summary.write_text(markdown_summary(result), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
