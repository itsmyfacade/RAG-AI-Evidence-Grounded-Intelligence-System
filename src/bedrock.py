"""Backward-compatible Bedrock function wrapper."""

from src.providers import BedrockProvider


def generate_answer(question: str, documents: list) -> str:
    evidence = [f"[{doc.metadata['document_id']}]\n{doc.page_content}" for doc in documents]
    return BedrockProvider().generate(question, evidence).text
