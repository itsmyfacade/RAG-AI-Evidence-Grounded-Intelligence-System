import math
import re
from collections import Counter
from functools import lru_cache

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from src.settings import get_settings


class LocalEmbeddings(Embeddings):
    def __init__(self):
        from sentence_transformers import SentenceTransformer
        configuration = get_settings()
        self.model = SentenceTransformer(configuration.embedding_model, local_files_only=configuration.embedding_local_files_only)

    def embed_documents(self, texts):
        return self.model.encode(texts, normalize_embeddings=True).tolist()

    def embed_query(self, text):
        return self.model.encode([text], normalize_embeddings=True)[0].tolist()


def get_embeddings():
    if get_settings().deployment_profile == "lite":
        raise RuntimeError("Embedding models are unavailable in the lite deployment profile")
    provider = get_settings().embeddings_mode
    if provider == "bedrock":
        from langchain_aws import BedrockEmbeddings

        configuration = get_settings()
        return BedrockEmbeddings(model_id=configuration.bedrock_embedding_model_id, region_name=configuration.aws_region)
    if provider != "local":
        raise ValueError(f"Unsupported embedding provider: {provider}")
    return LocalEmbeddings()


def _store(provider: str):
    from langchain_chroma import Chroma

    configuration = get_settings()
    return Chroma(collection_name="aegis_incidents", embedding_function=get_embeddings(), persist_directory=str(configuration.vector_store_path / f".chroma_{provider}"))


def build_vectorstore():
    from src.ingest import extract_documents, transform_documents

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
    if configuration.deployment_profile == "lite":
        if not configuration.retrieval_abstention:
            return _lexical_search(question, k=k, metadata_filter=metadata_filter)
        ranked = _lexical_search_with_scores(question, k=k, metadata_filter=metadata_filter)
        if not retrieval_is_sufficient(ranked, minimum_score=configuration.retrieval_abstention_threshold):
            return []
        return [document for document, _ in ranked]
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
    if configuration.deployment_profile == "lite":
        return [(document, score) for document, score in _lexical_search_with_scores(question, k=k, metadata_filter=metadata_filter)]
    provider = configuration.embeddings_mode
    requested_k = k or configuration.retrieval_k
    results = _store(provider).similarity_search_with_relevance_scores(question, k=requested_k, filter=metadata_filter)
    return [(document, score) for document, score in results if score >= configuration.retrieval_score_threshold]


def retrieval_mode() -> str:
    return "lexical" if get_settings().deployment_profile == "lite" else "chroma"


def _lexical_documents():
    """Load small narrative documents without splitters, Chroma, or ML models."""
    return list(_cached_lexical_documents(str(get_settings().dataset_path)))


@lru_cache(maxsize=8)
def _cached_lexical_documents(dataset_path: str):
    import hashlib
    import json
    from pathlib import Path

    documents = []
    for path in sorted(Path(dataset_path).glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        content = str(record["content"]).strip()
        documents.append(Document(
            page_content=content,
            metadata={
                "document_id": str(record["document_id"]),
                "title": str(record["title"]),
                "category": str(record["category"]).lower(),
                "version": str(record["version"]),
                "classification": str(record["classification"]).lower(),
                "source": str(path).replace("\\", "/"),
                "chunk_index": 0,
                "chunk_id": f"{record['document_id']}:0",
                "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            },
        ))
    return documents


def _tokenize(text: str) -> list[str]:
    return [term for term in re.findall(r"[a-z0-9_:-]+", text.lower()) if len(term) >= 3]


def _legacy_lexical_search_with_scores(question, k=None, metadata_filter=None):
    requested_k = k or get_settings().retrieval_k
    query_terms = set(_tokenize(question))
    ranked = []
    for document in _lexical_documents():
        if metadata_filter and any(document.metadata.get(key) != value for key, value in metadata_filter.items()):
            continue
        text = f"{document.metadata.get('title', '')} {document.metadata.get('category', '')} {document.page_content}".lower()
        text_terms = set(_tokenize(text))
        overlap = len(query_terms & text_terms)
        score = overlap / max(len(query_terms), 1)
        if overlap:
            ranked.append((document, score))
    ranked.sort(key=lambda pair: (-pair[1], pair[0].metadata.get("document_id", "")))
    return ranked[:requested_k]


def _bm25_lexical_search_with_scores(question, k=None, metadata_filter=None):
    """Deterministic BM25-style ranking with lightweight field weighting."""
    requested_k = k or get_settings().retrieval_k
    documents = [
        document for document in _lexical_documents()
        if not metadata_filter or not any(document.metadata.get(key) != value for key, value in metadata_filter.items())
    ]
    if not documents:
        return []
    query_terms = _tokenize(question)
    if not query_terms:
        return []
    tokenized: list[list[str]] = []
    for document in documents:
        title = str(document.metadata.get("title", ""))
        category = str(document.metadata.get("category", ""))
        # Repeating title and category gives metadata a modest, deterministic boost.
        tokenized.append(_tokenize(f"{title} {title} {category} {document.page_content}"))
    document_frequency = Counter(term for terms in tokenized for term in set(terms))
    average_length = sum(len(terms) for terms in tokenized) / len(tokenized)
    query_phrase = " ".join(query_terms)
    scores: list[tuple[Document, float]] = []
    k1, b = 1.2, 0.75
    for document, terms in zip(documents, tokenized, strict=True):
        frequencies = Counter(terms)
        length = len(terms) or 1
        score = 0.0
        for term in query_terms:
            frequency = frequencies.get(term, 0)
            if not frequency:
                continue
            idf = math.log(1 + (len(documents) - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5))
            score += idf * ((frequency * (k1 + 1)) / (frequency + k1 * (1 - b + b * length / max(average_length, 1))))
        if query_phrase and query_phrase in document.page_content.lower():
            score += 0.75
        if score > 0:
            scores.append((document, score))
    scores.sort(key=lambda pair: (-pair[1], pair[0].metadata.get("document_id", "")))
    return scores[:requested_k]


def _lexical_search_with_scores(question, k=None, metadata_filter=None):
    configuration = get_settings()
    if configuration.retrieval_profile == "legacy":
        return _legacy_lexical_search_with_scores(question, k=k, metadata_filter=metadata_filter)
    return _bm25_lexical_search_with_scores(question, k=k, metadata_filter=metadata_filter)


def retrieval_is_sufficient(ranked_results: list[tuple[Document, float]], *, minimum_score: float | None = None) -> bool:
    """Return whether lexical evidence clears a calibrated, label-free score gate."""
    if not ranked_results:
        return False
    threshold = minimum_score if minimum_score is not None else get_settings().retrieval_abstention_threshold
    top_score = ranked_results[0][1]
    return top_score >= threshold


def _lexical_search(question, k=None, metadata_filter=None):
    return [document for document, _ in _lexical_search_with_scores(question, k=k, metadata_filter=metadata_filter)]


if __name__ == "__main__":
    build_vectorstore()
