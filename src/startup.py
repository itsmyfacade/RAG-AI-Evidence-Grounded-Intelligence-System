"""Safe startup/readiness diagnostics; never prints credentials or account IDs."""

from __future__ import annotations

import json

from src.dataset import validate_database
from src.settings import get_settings, provider_status


def diagnostics() -> dict:
    configuration = get_settings()
    documents = configuration.dataset_path.exists() and any(configuration.dataset_path.glob("*.json"))
    database = configuration.database_path.exists()
    result = {
        "documents_present": documents,
        "database_present": database,
        "provider_configuration": provider_status(),
        "database_validation": None,
        "ready": documents and database,
    }
    if database:
        try:
            result["database_validation"] = validate_database(configuration.database_path)
        except (OSError, ValueError) as exc:
            result["ready"] = False
            result["database_validation"] = {"error_type": type(exc).__name__}
    return result


if __name__ == "__main__":
    print(json.dumps(diagnostics(), indent=2))
