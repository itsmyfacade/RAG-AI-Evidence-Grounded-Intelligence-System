import sys
import types
from concurrent.futures import ThreadPoolExecutor
from typing import ClassVar

import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from src import rag
from src.rag import LocalEmbeddings, LocalVectorStore


class FakeEmbeddings(Embeddings):
    def _vector(self, text: str):
        return [float("403" in text), float("webhook" in text), float("scope" in text)]

    def embed_documents(self, texts):
        return [self._vector(text) for text in texts]

    def embed_query(self, text):
        return self._vector(text)


def test_local_vector_store_persists_ids_and_supports_metadata_filters(tmp_path):
    documents = [
        Document(page_content="HTTP 403 missing scope", metadata={"document_id": "INC-001", "category": "incident", "chunk_id": "INC-001:0"}),
        Document(page_content="Webhook retries", metadata={"document_id": "API-005", "category": "api", "chunk_id": "API-005:0"}),
    ]
    store = LocalVectorStore(tmp_path / "vectors.json", FakeEmbeddings())
    store.rebuild(documents, ["INC-001:0", "API-005:0"])
    results = store.similarity_search("403 scope", k=2, filter={"category": "incident"})
    assert [document.metadata["document_id"] for document in results] == ["INC-001"]

    reopened = LocalVectorStore(tmp_path / "vectors.json", FakeEmbeddings())
    stored = reopened.similarity_search("403 scope", k=2)
    assert stored[0].metadata["document_id"] == "INC-001"
    assert stored[0].metadata["chunk_id"] == "INC-001:0"


def test_standard_and_lite_paths_are_explicitly_separate(monkeypatch):
    document = Document(page_content="vector result", metadata={"document_id": "INC-001", "chunk_id": "INC-001:0"})

    class FakeStore:
        def similarity_search(self, question, k, filter=None):
            return [document]

    monkeypatch.setenv("AEGIS_DEPLOYMENT_PROFILE", "standard")
    monkeypatch.setenv("AEGIS_EMBEDDINGS", "local")
    monkeypatch.setattr(rag, "_store", lambda provider: FakeStore())
    monkeypatch.setattr(rag, "_lexical_search", lambda *args, **kwargs: [])
    assert rag.search("question", k=1)[0].metadata["document_id"] == "INC-001"

    monkeypatch.setenv("AEGIS_DEPLOYMENT_PROFILE", "lite")
    monkeypatch.setattr(rag, "_lexical_search", lambda *args, **kwargs: [document])
    assert rag.search("question", k=1)[0].metadata["document_id"] == "INC-001"


def test_standard_profile_uses_local_vector_store_without_chroma(monkeypatch, tmp_path):
    monkeypatch.setenv("AEGIS_DEPLOYMENT_PROFILE", "standard")
    monkeypatch.setattr(rag, "get_embeddings", lambda: object())
    monkeypatch.setattr(rag, "_vector_index_path", lambda provider: tmp_path / f"{provider}.json")
    rag._store.cache_clear()
    assert isinstance(rag._store("local"), rag.LocalVectorStore)
    assert "chromadb" not in sys.modules
    assert "langchain_chroma" not in sys.modules


def test_local_vector_store_orders_by_similarity(tmp_path):
    store = LocalVectorStore(tmp_path / "vectors.json", FakeEmbeddings())
    store.rebuild(
        [
            Document(page_content="HTTP 403 missing scope", metadata={"document_id": "INC-001"}),
            Document(page_content="Webhook retries", metadata={"document_id": "API-005"}),
        ],
        ["INC-001:0", "API-005:0"],
    )
    scored = store.similarity_search_with_relevance_scores("403 scope", k=2)
    assert scored[0][0].metadata["document_id"] == "INC-001"
    assert scored[0][1] > scored[1][1]


def test_local_vector_store_rejects_corrupt_and_incompatible_indexes(tmp_path):
    path = tmp_path / "vectors.json"
    path.write_text('{"schema_version": 2,', encoding="utf-8")
    with pytest.raises(rag.LocalVectorIndexError, match="corrupted"):
        LocalVectorStore(path, FakeEmbeddings())

    store = LocalVectorStore(path, FakeEmbeddings(), load_existing=False)
    store.rebuild(
        [Document(page_content="HTTP 403 missing scope", metadata={"document_id": "INC-001"})],
        ["INC-001:0"],
        {"provider": "local", "embedding_model": "model-a", "corpus_fingerprint": "corpus-a"},
    )
    with pytest.raises(rag.LocalVectorIndexError, match="stale"):
        LocalVectorStore(path, FakeEmbeddings(), {"provider": "local", "embedding_model": "model-b", "corpus_fingerprint": "corpus-a"})


def test_local_vector_store_handles_missing_index_and_concurrent_reads(tmp_path):
    store = LocalVectorStore(tmp_path / "vectors.json", FakeEmbeddings())
    assert store.similarity_search("403 scope", k=2) == []
    documents = [Document(page_content="HTTP 403 missing scope", metadata={"document_id": "INC-001"})]

    def rebuild():
        store.rebuild(documents, ["INC-001:0"])

    def read():
        return store.similarity_search("403 scope", k=1)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(rebuild if index % 2 == 0 else read) for index in range(8)]
        results = [future.result() for future in futures]
    assert any(results) or store.similarity_search("403 scope", k=1)
    assert not list(tmp_path.glob("*.tmp"))


def test_local_embeddings_use_configured_model_and_cache_policy(monkeypatch):
    monkeypatch.setenv("AEGIS_DEPLOYMENT_PROFILE", "standard")
    monkeypatch.setenv("AEGIS_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    monkeypatch.setenv("AEGIS_EMBEDDING_LOCAL_FILES_ONLY", "true")
    class FakeSentenceTransformer:
        instances: ClassVar[list["FakeSentenceTransformer"]] = []

        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.encode = lambda texts, normalize_embeddings: [[0.1, 0.2] for _ in texts]
            self.instances.append(self)

    fake_module = types.ModuleType("sentence_transformers")
    setattr(fake_module, "SentenceTransformer", FakeSentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    embeddings = LocalEmbeddings()

    model = FakeSentenceTransformer.instances[0]
    assert embeddings.model is model
    assert model.kwargs["local_files_only"] is True
    assert model.args[0] == "all-MiniLM-L6-v2"
