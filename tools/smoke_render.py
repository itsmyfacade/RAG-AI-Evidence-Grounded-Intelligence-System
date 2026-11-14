"""Bounded, read-only smoke checks for an AEGIS Render deployment."""

from __future__ import annotations

import argparse
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request_json(url: str, method: str = "GET", body: dict | None = None, timeout: float = 15) -> dict:
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(url, data=payload, method=method, headers={"Content-Type": "application/json"})
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout) as response:
            content = response.read().decode("utf-8")
            return {
                "status": response.status,
                "seconds": round(time.perf_counter() - started, 3),
                "json": json.loads(content) if content else None,
            }
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {
            "status": None if not isinstance(exc, HTTPError) else exc.code,
            "seconds": round(time.perf_counter() - started, 3),
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://aegis-ai-y41k.onrender.com")
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    base = args.base_url.rstrip("/")
    checks = {
        "health": request_json(f"{base}/health", timeout=args.timeout),
        "ready": request_json(f"{base}/ready", timeout=args.timeout),
        "samples": request_json(f"{base}/samples", timeout=args.timeout),
        "investigate": request_json(
            f"{base}/investigate",
            method="POST",
            body={
                "scenario_id": "SCN-005",
                "question": "What evidence explains the webhook delivery symptoms?",
            },
            timeout=args.timeout,
        ),
    }
    print(json.dumps({"base_url": base, "checks": checks}, indent=2))
    return 0 if all(result["status"] == 200 for result in checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
