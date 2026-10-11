from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings


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
