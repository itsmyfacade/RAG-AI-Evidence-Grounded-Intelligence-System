from langchain_aws import BedrockEmbeddings
from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings

from src.ingest import extract_documents, transform_documents
from src.settings import get_settings


class LocalEmbeddings(Embeddings):
    def __init__(self):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(get_settings().embedding_model)

    def embed_documents(self, texts):
        return self.model.encode(texts, normalize_embeddings=True).tolist()

    def embed_query(self, text):
        return self.model.encode([text], normalize_embeddings=True)[0].tolist()


def get_embeddings():
    provider = get_settings().embeddings_mode
    if provider == "bedrock":
        configuration = get_settings()
        return BedrockEmbeddings(model_id=configuration.bedrock_embedding_model_id, region_name=configuration.aws_region)
    if provider != "local":
        raise ValueError(f"Unsupported embedding provider: {provider}")
    return LocalEmbeddings()


def _store(provider: str):
    configuration = get_settings()
    return Chroma(collection_name="aegis_incidents", embedding_function=get_embeddings(), persist_directory=str(configuration.vector_store_path / f".chroma_{provider}"))


def build_vectorstore():
    chunks = transform_documents(extract_documents())
    provider = get_settings().embeddings_mode
    store = _store(provider)
    ids = [doc.metadata["chunk_id"] for doc in chunks]
    existing = store.get(include=[]).get("ids", [])
    # LangChain Chroma exposes add/delete rather than a stable cross-version
    # upsert method. Replacing the collection contents makes reindexing safe
    # for this small deterministic corpus and reconciles deletions.
    if existing:
        store.delete(ids=existing)
    store.add_documents(chunks, ids=ids)
    print(f"Indexed {len(chunks)} chunks using {provider} embeddings")
    return store


def search(question, k=None, metadata_filter=None):
    configuration = get_settings()
    provider = configuration.embeddings_mode
    requested_k = k or configuration.retrieval_k
    results = _store(provider).similarity_search(question, k=requested_k, filter=metadata_filter)
    unique = []
    seen = set()
    for document in results:
        identity = document.metadata.get("chunk_id") or document.metadata.get("document_id")
        if identity not in seen:
            unique.append(document)
            seen.add(identity)
    return unique


def search_with_scores(question, k=None, metadata_filter=None):
    configuration = get_settings()
    provider = configuration.embeddings_mode
    requested_k = k or configuration.retrieval_k
    results = _store(provider).similarity_search_with_relevance_scores(question, k=requested_k, filter=metadata_filter)
    return [(document, score) for document, score in results if score >= configuration.retrieval_score_threshold]


if __name__ == "__main__":
    build_vectorstore()
