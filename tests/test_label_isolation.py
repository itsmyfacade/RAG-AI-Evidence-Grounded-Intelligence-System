"""Evaluator-only labels must not influence runtime investigation statuses.

These tests run the real investigation graph (supervisor -> retrieval -> SQL ->
synthesis -> verification) for all 20 public scenarios. They do not compare
static fixtures.
"""

import builtins
import io
import json
import os
import pathlib

import pytest

import src.scenario_eval as scenario_eval
from src.agents import run_investigation
from src.dataset import generate_database
from src.scenario_catalog import SCENARIO_PRESENTATION, public_question

LABEL_FILE = "scenario_labels.json"
ROTATE = {"completed": "escalated", "escalated": "insufficient_evidence", "insufficient_evidence": "completed"}


@pytest.fixture()
def runtime_env(tmp_path, monkeypatch):
    database = tmp_path / "aegis.db"
    generate_database(database)
    monkeypatch.setenv("AEGIS_DATABASE_PATH", str(database))
    monkeypatch.setenv("AEGIS_LLM", "local")
    monkeypatch.setenv("AEGIS_DEPLOYMENT_PROFILE", "lite")
    return tmp_path


def _runtime_statuses() -> dict[str, str]:
    return {sid: run_investigation(public_question(sid), sid)["report"].status for sid in SCENARIO_PRESENTATION}


def _redirect_label_reads(monkeypatch, content: str) -> None:
    """Serve `content` to ANY read of the label file, whatever path or API is used."""
    real_open, real_read_text = builtins.open, pathlib.Path.read_text

    def is_label(path) -> bool:
        return isinstance(path, (str, bytes, os.PathLike)) and os.fsdecode(os.fspath(path)).endswith(LABEL_FILE)

    def patched_open(file, mode="r", *args, **kwargs):
        if is_label(file) and "r" in mode and "b" not in mode:
            return io.StringIO(content)
        return real_open(file, mode, *args, **kwargs)

    def patched_read_text(self, *args, **kwargs):
        return content if is_label(self) else real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", patched_open)
    monkeypatch.setattr(io, "open", patched_open)
    monkeypatch.setattr(pathlib.Path, "read_text", patched_read_text)


def test_rotating_evaluator_labels_changes_zero_runtime_statuses(runtime_env, monkeypatch):
    original_labels = scenario_eval.load_labels()
    baseline = _runtime_statuses()

    rotated_labels = [{**label, "expected_status": ROTATE[label["expected_status"]]} for label in original_labels]
    _redirect_label_reads(monkeypatch, json.dumps(rotated_labels))

    # Every reader of the label file now sees different answers...
    assert [item["expected_status"] for item in scenario_eval.load_labels()] == [item["expected_status"] for item in rotated_labels]
    assert all(a["expected_status"] != b["expected_status"] for a, b in zip(original_labels, rotated_labels))
    # ...but the statuses produced by the investigation graph do not change.
    assert _runtime_statuses() == baseline
    # Non-trivial run: all three outcomes occur, so a constant status would fail this test.
    assert set(baseline.values()) == {"completed", "insufficient_evidence", "escalated"}


def test_runtime_never_opens_the_label_file(runtime_env, monkeypatch):
    opened = []
    real_open, real_read_text = builtins.open, pathlib.Path.read_text

    def guard(path):
        if os.fspath(path).endswith(LABEL_FILE):
            opened.append(os.fspath(path))
            raise PermissionError("evaluator-only label file read at runtime")

    def guarded_open(file, *args, **kwargs):
        if isinstance(file, (str, bytes, os.PathLike)):
            guard(file)
        return real_open(file, *args, **kwargs)

    def guarded_read_text(self, *args, **kwargs):
        guard(self)
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(io, "open", guarded_open)
    monkeypatch.setattr(pathlib.Path, "read_text", guarded_read_text)

    # The guard is live: the evaluator, which legitimately reads labels, is blocked.
    with pytest.raises(PermissionError):
        scenario_eval.load_labels()
    opened.clear()

    statuses = _runtime_statuses()
    assert opened == []
    assert len(statuses) == 20
    assert set(statuses.values()) == {"completed", "insufficient_evidence", "escalated"}


def test_evaluator_data_is_excluded_from_the_runtime_image():
    root = pathlib.Path(__file__).resolve().parents[1]
    ignored = [line.strip() for line in (root / ".dockerignore").read_text(encoding="utf-8").splitlines()]
    assert "data/evaluation/" in ignored
    # Only the offline evaluators may refer to evaluator data; serving modules must not need it.
    offline = {"scenario_eval.py", "retrieval_eval.py"}
    referencing = sorted(
        path.name for path in (root / "src").glob("*.py")
        if path.name not in offline and ("scenario_labels" in path.read_text(encoding="utf-8") or '"evaluation"' in path.read_text(encoding="utf-8"))
    )
    assert referencing == []
