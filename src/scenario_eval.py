"""Offline scenario evaluation with answers kept outside serving data."""

from __future__ import annotations

import json
from pathlib import Path

from src.agents import run_investigation

LABEL_PATH = Path(__file__).resolve().parents[1] / "data" / "evaluation" / "scenario_labels.json"


def load_labels() -> list[dict[str, str]]:
    return json.loads(LABEL_PATH.read_text(encoding="utf-8"))


def evaluate_scenarios() -> list[dict[str, str]]:
    results = []
    for label in load_labels():
        scenario_id = label["scenario_id"]
        question = f"Investigate the available operational and documentation evidence for {scenario_id}. Do not assume a cause."
        report = run_investigation(question, scenario_id=scenario_id)["report"]
        results.append({"scenario_id": scenario_id, "expected_status": label["expected_status"], "actual_status": report.status})
    return results


if __name__ == "__main__":
    results = evaluate_scenarios()
    print(json.dumps({"matched": sum(item["expected_status"] == item["actual_status"] for item in results), "total": len(results), "results": results}, indent=2))
