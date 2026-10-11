import hashlib
import json
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.settings import get_settings


REQUIRED = {"document_id", "title", "category", "version", "classification", "content"}


def extract_documents(directory=None):
    directory = directory or get_settings().dataset_path
    documents = []
    for path in sorted(Path(directory).glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        missing = REQUIRED - record.keys()
        if missing:
            raise ValueError(f"{path.name} missing fields: {sorted(missing)}")
        if not isinstance(record["content"], str) or not record["content"].strip():
            raise ValueError(f"{path.name} has empty or invalid content")
        content = record["content"].strip()
        metadata = {
            "document_id": str(record["document_id"]),
            "title": str(record["title"]),
            "category": str(record["category"]).lower(),
            "version": str(record["version"]),
            "classification": str(record["classification"]).lower(),
            "source": str(path).replace("\\", "/"),
            "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        }
        documents.append(Document(page_content=content, metadata=metadata))
    ids = [doc.metadata["document_id"] for doc in documents]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate document_id values detected")
    return documents


def transform_documents(documents):
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=80)
    chunks = splitter.split_documents(documents)
    counts = {}
    for chunk in chunks:
        document_id = chunk.metadata["document_id"]
        index = counts.get(document_id, 0)
        counts[document_id] = index + 1
        chunk.metadata = {**chunk.metadata, "chunk_index": index, "chunk_count": 0, "chunk_id": f"{document_id}:{index}"}
    for chunk in chunks:
        chunk.metadata["chunk_count"] = counts[chunk.metadata["document_id"]]
    return chunks


if __name__ == "__main__":
    documents = extract_documents()
    chunks = transform_documents(documents)
    print(f"Extracted documents: {len(documents)}")
    print(f"Transformed chunks: {len(chunks)}")
    print("Sample metadata:", chunks[0].metadata)
