import json
import math
import os
import re
import tempfile
from collections import Counter
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from threading import RLock

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


VECTOR_INDEX_SCHEMA_VERSION = 2
_VECTOR_INDEX_LOCK = RLock()


class LocalVectorIndexError(ValueError):
    """Raised when a persisted vector index cannot be trusted or loaded."""


class LocalVectorStore:
    """Small deterministic file-backed vector index for the optional local profile."""

    def __init__(self, index_path: Path, embedding_function: Embeddings, expected_metadata: dict[str, str] | None = None, *, load_existing: bool = True):
        self.index_path = index_path
        self.embedding_function = embedding_function
        self.expected_metadata = expected_metadata
        with _VECTOR_INDEX_LOCK:
            self._records = self._load() if load_existing else []

    def _load(self) -> list[dict]:
        if not self.index_path.exists():
            return []
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LocalVectorIndexError("Local vector index is corrupted; rebuild it") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != VECTOR_INDEX_SCHEMA_VERSION:
            raise LocalVectorIndexError("Unsupported local vector index schema; rebuild it")
        metadata = payload.get("index_metadata")
        if not isinstance(metadata, dict):
            raise LocalVectorIndexError("Local vector index metadata is missing; rebuild it")
        comparable_metadata = {key: value for key, value in metadata.items() if key != "dimension"}
        if self.expected_metadata and comparable_metadata != self.expected_metadata:
            raise LocalVectorIndexError("Local vector index is stale for the current model or corpus; rebuild it")
        records = payload.get("records", [])
        if not isinstance(records, list):
            raise LocalVectorIndexError("Local vector index records must be a list")
        try:
            dimension = int(metadata.get("dimension", 0))
        except (TypeError, ValueError) as exc:
            raise LocalVectorIndexError("Local vector index has an invalid embedding dimension") from exc
        self._validate_records(records, dimension)
        return records

    @staticmethod
    def _validate_records(records: list[dict], dimension: int) -> None:
        if dimension < 1:
            raise LocalVectorIndexError("Local vector index has an invalid embedding dimension")
        identifiers = []
        for record in records:
            embedding = record.get("embedding") if isinstance(record, dict) else None
            if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not record["id"] or not isinstance(record.get("content"), str) or not isinstance(record.get("metadata"), dict) or not isinstance(embedding, list) or len(embedding) != dimension or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in embedding):
                raise LocalVectorIndexError("Local vector index contains an invalid record")
            identifiers.append(record["id"])
        if len(identifiers) != len(set(identifiers)):
            raise LocalVectorIndexError("Local vector index contains duplicate document IDs")

    def rebuild(self, documents: list[Document], ids: list[str], index_metadata: dict[str, str] | None = None) -> None:
        if len(documents) != len(ids) or len(ids) != len(set(ids)):
            raise ValueError("Vector index documents and IDs must be aligned and unique")
        vectors = self.embedding_function.embed_documents([document.page_content for document in documents])
        if len(vectors) != len(documents):
            raise ValueError("Embedding provider returned an unexpected vector count")
        normalized_vectors = [list(vector) for vector in vectors]
        dimension = len(normalized_vectors[0]) if normalized_vectors else 0
        if dimension < 1 or any(len(vector) != dimension for vector in normalized_vectors):
            raise ValueError("Embedding provider returned inconsistent vector dimensions")
        metadata = index_metadata or self.expected_metadata or {}
        metadata = {**metadata, "dimension": str(dimension)}
        records = [
            {"id": identifier, "content": document.page_content, "metadata": document.metadata, "embedding": [float(value) for value in vector]}
            for identifier, document, vector in zip(ids, documents, normalized_vectors, strict=True)
        ]
        self._validate_records(records, dimension)
        payload = json.dumps({"schema_version": VECTOR_INDEX_SCHEMA_VERSION, "index_metadata": metadata, "records": records}, sort_keys=True)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        with _VECTOR_INDEX_LOCK:
            try:
                file_descriptor, temporary_name = tempfile.mkstemp(prefix=f".{self.index_path.name}.", suffix=".tmp", dir=self.index_path.parent)
                temporary_path = Path(temporary_name)
                with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary_path, self.index_path)
                self._records = records
            except (OSError, TypeError, ValueError) as exc:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)
                raise LocalVectorIndexError("Local vector index rebuild failed safely") from exc

    @staticmethod
    def _matches(metadata: dict, metadata_filter: dict | None) -> bool:
        return not metadata_filter or all(metadata.get(key) == value for key, value in metadata_filter.items())

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        numerator = sum(float(a) * float(b) for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(float(value) ** 2 for value in left))
        right_norm = math.sqrt(sum(float(value) ** 2 for value in right))
        return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0

    def similarity_search_with_relevance_scores(self, question: str, k: int, filter: dict | None = None):
        query_vector = self.embedding_function.embed_query(question)
        ranked = []
        with _VECTOR_INDEX_LOCK:
            records = tuple(self._records)
        for record in records:
            metadata = record.get("metadata", {})
            if self._matches(metadata, filter):
                score = self._cosine(query_vector, record["embedding"])
                ranked.append((score, record))
        ranked.sort(key=lambda item: (-item[0], item[1]["id"]))
        return [(self._document(record), score) for score, record in ranked[:k]]

    def similarity_search(self, question: str, k: int, filter: dict | None = None):
        return [document for document, _ in self.similarity_search_with_relevance_scores(question, k, filter)]

    @staticmethod
    def _document(record: dict) -> Document:
        return Document(page_content=record["content"], metadata=record["metadata"])


def _vector_index_path(provider: str) -> Path:
    return get_settings().vector_store_path / f".aegis_vectors_{provider}.json"


def _index_metadata(provider: str, chunks: list[Document]) -> dict[str, str]:
    configuration = get_settings()
    model = configuration.embedding_model if provider == "local" else configuration.bedrock_embedding_model_id
    corpus = [{"id": document.metadata.get("chunk_id", ""), "hash": document.metadata.get("content_hash", ""), "content": document.page_content} for document in chunks]
    fingerprint = sha256(json.dumps(corpus, sort_keys=True).encode("utf-8")).hexdigest()
    return {"provider": provider, "embedding_model": model, "corpus_fingerprint": fingerprint}


@lru_cache(maxsize=2)
def _store(provider: str):
    from src.ingest import extract_documents, transform_documents

    chunks = transform_documents(extract_documents())
    return LocalVectorStore(_vector_index_path(provider), get_embeddings(), _index_metadata(provider, chunks))


def build_vectorstore():
    from src.ingest import extract_documents, transform_documents

    chunks = transform_documents(extract_documents())
    provider = get_settings().embeddings_mode
    _store.cache_clear()
    store = LocalVectorStore(_vector_index_path(provider), get_embeddings(), _index_metadata(provider, chunks), load_existing=False)
    ids = [doc.metadata["chunk_id"] for doc in chunks]
    store.rebuild(chunks, ids, _index_metadata(provider, chunks))
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
    """Load small narrative documents without splitters or ML models."""
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
