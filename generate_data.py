"""Canonical deterministic AEGIS data-generation CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.dataset import generate_database, validate_database
from src.document_dataset import generate_documents, validate_documents
from src.settings import get_settings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate or validate the deterministic AEGIS corpus")
    parser.add_argument("--mode", choices=("documents", "database", "all", "validate"), default="database")
    parser.add_argument("--documents-dir", type=Path, default=None, help="Narrative document output directory")
    parser.add_argument("--database-path", type=Path, default=None, help="SQLite database output path")
    parser.add_argument("--replace-documents", action="store_true", help="Replace conflicting document files")
    parser.add_argument("--replace-database", action="store_true", help="Replace an existing SQLite database")
    return parser


def _database_result(path: Path, documents_dir: Path, replace: bool) -> dict[str, int | str]:
    if path.exists() and not replace:
        result = validate_database(path)
        return {"database": "unchanged", **result}
    if path.exists() and replace:
        path.unlink()
    return {"database": "generated", **generate_database(path, documents_path=documents_dir)}


def run(args: argparse.Namespace) -> dict[str, object]:
    configuration = get_settings()
    documents_dir = args.documents_dir or configuration.dataset_path
    database_path = args.database_path or configuration.database_path
    if args.mode == "documents":
        return {"documents": generate_documents(documents_dir, replace=args.replace_documents)}
    if args.mode == "database":
        return {"database": _database_result(database_path, documents_dir, args.replace_database)}
    if args.mode == "all":
        documents = generate_documents(documents_dir, replace=args.replace_documents)
        database = _database_result(database_path, documents_dir, args.replace_database)
        return {"documents": documents, "database": database}
    return {"documents": validate_documents(documents_dir), "database": validate_database(database_path)}


def main() -> int:
    print(json.dumps(run(_parser().parse_args()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
