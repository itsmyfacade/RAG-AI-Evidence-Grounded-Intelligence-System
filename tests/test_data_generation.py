import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.dataset import generate_database, validate_database
from src.document_dataset import all_document_seeds, generate_documents, validate_documents

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = ROOT / "data" / "documents"


def test_existing_document_corpus_matches_canonical_seeds(tmp_path):
    output = tmp_path / "documents"
    result = generate_documents(output)

    assert result == {"expected": 30, "created": 30, "unchanged": 0}
    assert validate_documents(DOCUMENTS) == {"documents": 30, "identifiers": 30}
    for seed in all_document_seeds():
        assert (DOCUMENTS / f"{seed.document_id}.json").read_bytes() == (output / f"{seed.document_id}.json").read_bytes()


def test_database_schema_and_counts_are_reproducible(tmp_path):
    documents = tmp_path / "documents"
    database = tmp_path / "aegis.db"
    generate_documents(documents)
    counts = generate_database(database, documents_path=documents)

    assert counts == {
        "scenarios": 20,
        "partners": 20,
        "incidents": 20,
        "deployments": 20,
        "configuration_changes": 20,
        "api_logs": 240,
        "webhook_events": 80,
        "support_tickets": 20,
        "evidence_catalog": 30,
    }
    validated = validate_database(database)
    assert {key: counts[key] for key in validated} == validated


def test_generation_refuses_conflicting_existing_document(tmp_path):
    documents = tmp_path / "documents"
    generate_documents(documents)
    path = documents / "API-001.json"
    path.write_text(json.dumps({"document_id": "API-001"}), encoding="utf-8")

    with pytest.raises(FileExistsError, match="Existing document differs"):
        generate_documents(documents)


@pytest.mark.parametrize("mode", ["documents", "database", "all", "validate"])
def test_canonical_cli_modes_use_explicit_temporary_outputs(tmp_path, mode):
    documents = tmp_path / "documents"
    database = tmp_path / "aegis.db"
    command = [
        sys.executable,
        str(ROOT / "generate_data.py"),
        "--mode",
        mode,
        "--documents-dir",
        str(documents),
        "--database-path",
        str(database),
    ]
    if mode == "validate":
        setup = [
            sys.executable,
            str(ROOT / "generate_data.py"),
            "--mode",
            "all",
            "--documents-dir",
            str(documents),
            "--database-path",
            str(database),
        ]
        subprocess.run(setup, cwd=ROOT, check=True, capture_output=True, text=True)
    completed = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    assert completed.returncode == 0
