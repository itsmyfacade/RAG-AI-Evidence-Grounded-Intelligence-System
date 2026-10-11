"""Safe startup/readiness diagnostics; never prints credentials or account IDs."""

from __future__ import annotations

import json

from src.dataset import generate_database, validate_database
from src.settings import get_settings, provider_status


def ensure_resources() -> dict[str, bool]:
    """Create the deterministic SQLite resource when a fresh container starts."""
    configuration = get_settings()
    generated = False
    if not configuration.database_path.exists():
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
