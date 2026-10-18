from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from unittest.mock import patch

import src.rag as rag
from src.rag import LocalEmbeddings


class FakeEmbeddings(Embeddings):
    def _vector(self, text: str):
        return [float("403" in text), float("webhook" in text), float("scope" in text)]

    def embed_documents(self, texts):
        return [self._vector(text) for text in texts]

    def embed_query(self, text):
        return self._vector(text)


def test_chroma_retrieval_and_metadata_filter_are_offline(tmp_path):
    store = Chroma(collection_name="rag_test", embedding_function=FakeEmbeddings(), persist_directory=str(tmp_path / "chroma"))
    store.add_documents(
        documents=[
            Document(page_content="HTTP 403 missing scope", metadata={"document_id": "INC-001", "category": "incident", "chunk_id": "INC-001:0"}),
            Document(page_content="Webhook retries", metadata={"document_id": "API-005", "category": "api", "chunk_id": "API-005:0"}),
        ],
        ids=["INC-001:0", "API-005:0"],
    )
    results = store.similarity_search("403 scope", k=2, filter={"category": "incident"})
    assert [document.metadata["document_id"] for document in results] == ["INC-001"]

    reopened = Chroma(collection_name="rag_test", embedding_function=FakeEmbeddings(), persist_directory=str(tmp_path / "chroma"))
    stored = reopened.get(include=["metadatas"])
    assert "INC-001:0" in stored["ids"]
    metadata = stored["metadatas"][stored["ids"].index("INC-001:0")]
    assert metadata["document_id"] == "INC-001"
    assert metadata["chunk_id"] == "INC-001:0"


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


def test_local_embeddings_use_configured_model_and_cache_policy(monkeypatch):
    monkeypatch.setenv("AEGIS_DEPLOYMENT_PROFILE", "standard")
    monkeypatch.setenv("AEGIS_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    monkeypatch.setenv("AEGIS_EMBEDDING_LOCAL_FILES_ONLY", "true")
    with patch("sentence_transformers.SentenceTransformer") as constructor:
        constructor.return_value.encode.return_value = [[0.1, 0.2]]
        embeddings = LocalEmbeddings()
    assert embeddings.model is constructor.return_value
    assert constructor.call_args.kwargs["local_files_only"] is True
    assert constructor.call_args.args[0] == "all-MiniLM-L6-v2"
