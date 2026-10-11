import sqlite3

from langchain_core.documents import Document

from src.dataset import generate_database
from src.evidence import assess_claim_support, validate_citations
from src.aws_s3 import S3DocumentSource
from src.providers import BedrockProvider, ProviderError
from src.retrieval_eval import evaluate_cases
from src.schemas import Claim, EvidenceRecord
from src.settings import get_settings
from src.sql_tools import OperationalEvidenceStore


def test_dataset_is_linked_and_reproducible(tmp_path):
    first = tmp_path / "first.db"
    second = tmp_path / "second.db"
    assert generate_database(first) == generate_database(second)
    with sqlite3.connect(first) as connection:
        assert connection.execute("SELECT COUNT(*) FROM api_logs").fetchone()[0] == 240
        assert connection.execute("SELECT COUNT(*) FROM webhook_events").fetchone()[0] == 80
        assert connection.execute("SELECT COUNT(*) FROM incidents WHERE scenario_id NOT IN (SELECT scenario_id FROM scenarios)").fetchone()[0] == 0


def test_sql_tools_are_read_only_and_parameterized(tmp_path):
    database = tmp_path / "aegis.db"
    generate_database(database)
    records = OperationalEvidenceStore(database).scenario_evidence("SCN-001")
    assert len(records) == 12
    assert records[0].source_type == "log"
    assert len(OperationalEvidenceStore(database).webhook_evidence("SCN-001")) == 4


def test_citations_and_claim_support():
    evidence = [EvidenceRecord(evidence_id="E-1", source_type="document", source_id="INC-001", excerpt="HTTP 403 missing reports:read scope")]
    assert validate_citations("Finding [INC-001]", {"INC-001"}) == (["INC-001"], [])
    claim = assess_claim_support(Claim(claim_id="C-1", statement="HTTP 403 missing scope", evidence_refs=["E-1"]), evidence)
    assert claim.support_status == "supported"


def test_retrieval_metrics_are_reproducible():
    cases = [{"question": "403", "relevant_document_ids": ["INC-001"], "required_categories": ["incident"]}]
    docs = [Document(page_content="", metadata={"document_id": "INC-001", "category": "incident"})]
    result = evaluate_cases(cases, lambda question, k: docs, k=1)
    assert result == {"Recall@k": 1.0, "Hit@k": 1.0, "MRR": 1.0, "evidence_coverage": 1.0}


def test_settings_are_typed_and_path_independent(monkeypatch):
    monkeypatch.setenv("AEGIS_BEDROCK_MODEL_ID", "amazon.nova-micro-v1:0")
    configuration = get_settings()
    assert configuration.bedrock_model_id == "amazon.nova-micro-v1:0"
    assert configuration.dataset_path.is_absolute()


class FakeS3:
    def list_objects_v2(self, **kwargs):
        return {"Contents": [{"Key": "documents/INC-001.json"}], "IsTruncated": False}

    def get_object(self, **kwargs):
        return {"ETag": "safe-test-etag", "Body": type("Body", (), {"read": lambda self: b'{"document_id":"INC-001"}'})()}


def test_s3_sync_is_offline_mockable(tmp_path):
    source = S3DocumentSource("demo", client=FakeS3())
    result = source.sync_to_directory(tmp_path)
    assert result == {"seen": 1, "written": 1}
    assert (tmp_path / "INC-001.json").exists()


def test_bedrock_provider_uses_configured_model_without_network():
    class FakeBedrock:
        def converse(self, **kwargs):
            assert kwargs["modelId"] == "amazon.nova-micro-v1:0"
            return {"output": {"message": {"content": [{"text": "[INC-001] supported"}]}}}

    result = BedrockProvider(client=FakeBedrock()).generate("question", ["[INC-001] evidence"])
    assert result.provider == "bedrock"


def test_bedrock_access_errors_are_classified():
    class FakeError(Exception):
        response = {"Error": {"Code": "AccessDeniedException"}}

    class FailingBedrock:
        def converse(self, **kwargs):
            raise FakeError()

    try:
        BedrockProvider(client=FailingBedrock()).generate("question", [])
    except ProviderError as error:
        assert error.kind == "access_denied"
    else:
        raise AssertionError("Expected ProviderError")
