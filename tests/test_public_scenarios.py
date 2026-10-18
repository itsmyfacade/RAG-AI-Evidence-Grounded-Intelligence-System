from src.scenario_catalog import SCENARIO_PRESENTATION, public_question, public_title
from src.dataset import generate_database
from src.sql_tools import OperationalEvidenceStore


def test_public_scenario_catalog_is_complete_and_symptom_oriented():
    assert set(SCENARIO_PRESENTATION) == {f"SCN-{index:03d}" for index in range(1, 21)}
    for scenario_id, (title, _question) in SCENARIO_PRESENTATION.items():
        assert public_title(scenario_id) == title
        assert "caused by" not in title.lower()
        assert "because" not in title.lower()
        assert "root cause" not in title.lower()


def test_public_questions_are_shared_and_do_not_presuppose_diagnosis():
    questions = [public_question(scenario_id) for scenario_id in SCENARIO_PRESENTATION]
    assert len(set(questions)) == 20
    for question in questions:
        lowered = question.lower()
        assert "do not assume a root cause" in lowered
        assert "because" not in lowered
        assert "caused by" not in lowered
        assert "expected_status" not in lowered
        assert "root_cause" not in lowered


def test_scenario_ids_are_not_answer_keys():
    assert "missing idempotency" not in public_title("SCN-005").lower()
    assert "event_id" not in public_question("SCN-005").lower()


def test_serving_scenario_options_have_no_evaluator_fields(tmp_path):
    database = tmp_path / "serving.db"
    generate_database(database)
    options = OperationalEvidenceStore(database).scenario_options()
    assert len(options) == 20
    assert not any(set(item) & {"expected_status", "root_cause", "expected_outcome", "conflict_note"} for item in options)
    assert options[4]["title"] == "Duplicate downstream records followed repeated webhook deliveries"


def test_lite_retrieval_is_not_uniform_across_public_questions(monkeypatch):
    monkeypatch.setenv("AEGIS_DEPLOYMENT_PROFILE", "lite")
    monkeypatch.setenv("AEGIS_DATASET_PATH", "data/documents")
    from src.rag import search

    retrieved_sets = {
        tuple(document.metadata["document_id"] for document in search(public_question(scenario_id), k=4))
        for scenario_id in SCENARIO_PRESENTATION
    }
    assert len(retrieved_sets) >= 10
