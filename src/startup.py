"""Safe startup/readiness diagnostics; never prints credentials or account IDs."""

from __future__ import annotations

import json
import sqlite3

from src.dataset import generate_database, validate_database
from src.scenario_catalog import public_title
from src.settings import get_settings, provider_status


def ensure_resources() -> dict[str, bool]:
    """Create the deterministic SQLite resource when a fresh container starts."""
    configuration = get_settings()
    generated = False
    needs_generation = not configuration.database_path.exists()
    if not needs_generation:
        try:
            with sqlite3.connect(configuration.database_path) as connection:
                scenario_columns = {row[1] for row in connection.execute("PRAGMA table_info(scenarios)")}
                incident_columns = {row[1] for row in connection.execute("PRAGMA table_info(incidents)")}
                title_rows = connection.execute("SELECT scenario_id, title FROM scenarios").fetchall()
                titles_current = len(title_rows) == 20 and all(row[1] == public_title(row[0]) for row in title_rows)
            needs_generation = scenario_columns != {"scenario_id", "title", "domain", "created_at"} or incident_columns != {"incident_id", "scenario_id", "partner_id", "service", "opened_at", "resolved_at", "observed_status"} or not titles_current
        except sqlite3.Error:
            needs_generation = True
    if needs_generation:
        generate_database(configuration.database_path)
        generated = True
    return {"database_generated": generated}


def diagnostics() -> dict:
    configuration = get_settings()
    resources = ensure_resources()
    documents = configuration.dataset_path.exists() and any(configuration.dataset_path.glob("*.json"))
    database = configuration.database_path.exists()
    result = {
        "documents_present": documents,
        "database_present": database,
        "provider_configuration": provider_status(),
        "database_validation": None,
        "retrieval_mode": "lexical" if configuration.deployment_profile == "lite" else "chroma",
        "resource_actions": resources,
        "ready": documents and database,
    }
    if database:
        try:
            result["database_validation"] = validate_database(configuration.database_path)
        except (OSError, ValueError) as exc:
            result["ready"] = False
            result["database_validation"] = {"error_type": type(exc).__name__}
    result["resource_checks"] = {
        "dataset_documents": documents,
        "sqlite_database": database,
        "lite_profile_safe": configuration.deployment_profile != "lite" or result["retrieval_mode"] == "lexical",
    }
    result["ready"] = result["ready"] and all(result["resource_checks"].values())
    return result


if __name__ == "__main__":
    print(json.dumps(diagnostics(), indent=2))
