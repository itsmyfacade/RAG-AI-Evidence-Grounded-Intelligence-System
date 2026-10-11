import subprocess
import sys
from pathlib import Path

from src.agents import run_investigation
from src.dataset import generate_database


def test_lite_import_does_not_load_ml_or_chroma():
    result = subprocess.run(
        [sys.executable, "-c", "import sys; import src.rag; print(any(name in sys.modules for name in ('torch', 'sentence_transformers', 'chromadb', 'langchain_chroma')))"],
        check=True,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.stdout.strip() == "False"


def test_lite_investigations_keep_graph_and_evidence(monkeypatch, tmp_path):
    database = tmp_path / "lite.db"
    generate_database(database)
    monkeypatch.setenv("AEGIS_DEPLOYMENT_PROFILE", "lite")
    monkeypatch.setenv("AEGIS_LLM", "local")
    monkeypatch.setenv("AEGIS_DATABASE_PATH", str(database))
    monkeypatch.setenv("AEGIS_DATASET_PATH", str(Path(__file__).resolve().parents[1] / "data" / "documents"))

    completed = run_investigation("Investigate duplicate webhook events in SCN-005", "SCN-005")
    insufficient = run_investigation("Investigate missing correlation logs in SCN-018", "SCN-018")

    assert completed["report"].status == "completed"
    assert completed["report"].provider == "local"
    assert len(completed["report"].evidence) >= 19
    assert insufficient["report"].status == "insufficient_evidence"
    assert insufficient["report"].attempts == 2
