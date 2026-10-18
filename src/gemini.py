"""Backward-compatible Gemini function wrapper."""

from src.providers import GeminiProvider


def generate_answer(question: str, documents: list) -> str:
    evidence = [f"[{doc.metadata['document_id']}]\n{doc.page_content}" for doc in documents]
    return GeminiProvider().generate(question, evidence).text
