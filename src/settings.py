"""Validated, path-independent application configuration."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)


class Settings(BaseModel):
    root: Path = ROOT
    deployment_profile: str = "standard"
    dataset_path: Path = ROOT / "data" / "documents"
    database_path: Path = ROOT / "data" / "aegis.db"
    vector_store_path: Path = ROOT
    llm_mode: str = "local"
    embeddings_mode: str = "local"
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_local_files_only: bool = True
    gemini_model: str = "gemini-3.5-flash"
    aws_region: str = "us-east-2"
    bedrock_model_id: str = "amazon.nova-micro-v1:0"
    bedrock_inference_profile: str = "us.amazon.nova-micro-v1:0"
    bedrock_embedding_model_id: str = "amazon.titan-embed-text-v2:0"
    retrieval_k: int = Field(default=4, ge=1, le=20)
    retrieval_score_threshold: float = Field(default=0.0, ge=0.0, le=1.0)
    provider_timeout_seconds: int = Field(default=30, ge=1, le=300)
    max_output_tokens: int = Field(default=500, ge=32, le=4096)
    bedrock_max_tokens: int = Field(default=1200, ge=32, le=4096)
    max_agent_attempts: int = Field(default=2, ge=1, le=5)
    demo_max_concurrency: int = Field(default=2, ge=1, le=32)
    demo_requests_per_minute: int = Field(default=20, ge=1, le=1000)

    @field_validator("llm_mode")
    @classmethod
    def validate_llm_mode(cls, value: str) -> str:
        value = value.lower()
        if value not in {"local", "gemini", "bedrock"}:
            raise ValueError("llm_mode must be local, gemini, or bedrock")
        return value

    @field_validator("deployment_profile")
    @classmethod
    def validate_deployment_profile(cls, value: str) -> str:
        value = value.lower()
        if value not in {"standard", "lite"}:
            raise ValueError("deployment_profile must be standard or lite")
        return value

    @field_validator("embeddings_mode")
    @classmethod
    def validate_embeddings_mode(cls, value: str) -> str:
        value = value.lower()
        if value not in {"local", "bedrock"}:
            raise ValueError("embeddings_mode must be local or bedrock")
        return value

    @classmethod
    def from_environment(cls) -> "Settings":
        def boolean(name: str, default: bool) -> bool:
            value = os.getenv(name)
            return default if value is None else value.lower() in {"1", "true", "yes", "on"}

        def path(name: str, default: Path) -> Path:
            value = os.getenv(name)
            candidate = Path(value) if value else default
            return candidate if candidate.is_absolute() else ROOT / candidate

        return cls(
            deployment_profile=os.getenv("AEGIS_DEPLOYMENT_PROFILE", "standard"),
            dataset_path=path("AEGIS_DATASET_PATH", ROOT / "data" / "documents"),
            database_path=path("AEGIS_DATABASE_PATH", ROOT / "data" / "aegis.db"),
            vector_store_path=path("AEGIS_VECTOR_STORE_PATH", ROOT),
            llm_mode=os.getenv("AEGIS_LLM", "local"),
            embeddings_mode=os.getenv("AEGIS_EMBEDDINGS", "local"),
            embedding_model=os.getenv("AEGIS_EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
            embedding_local_files_only=boolean("AEGIS_EMBEDDING_LOCAL_FILES_ONLY", True),
            gemini_model=os.getenv("AEGIS_GEMINI_MODEL", "gemini-3.5-flash"),
            aws_region=os.getenv("AWS_REGION", "us-east-2"),
            bedrock_model_id=os.getenv("AEGIS_BEDROCK_MODEL_ID", "amazon.nova-micro-v1:0"),
            bedrock_inference_profile=os.getenv("AEGIS_BEDROCK_INFERENCE_PROFILE", "us.amazon.nova-micro-v1:0"),
            bedrock_embedding_model_id=os.getenv("AEGIS_BEDROCK_EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0"),
            retrieval_k=int(os.getenv("AEGIS_RETRIEVAL_K", "4")),
            retrieval_score_threshold=float(os.getenv("AEGIS_RETRIEVAL_SCORE_THRESHOLD", "0")),
            provider_timeout_seconds=int(os.getenv("AEGIS_PROVIDER_TIMEOUT_SECONDS", "30")),
            max_output_tokens=int(os.getenv("AEGIS_MAX_OUTPUT_TOKENS", "500")),
            bedrock_max_tokens=int(os.getenv("AEGIS_BEDROCK_MAX_TOKENS", "1200")),
            max_agent_attempts=int(os.getenv("AEGIS_MAX_AGENT_ATTEMPTS", "2")),
            demo_max_concurrency=int(os.getenv("AEGIS_DEMO_MAX_CONCURRENCY", "2")),
            demo_requests_per_minute=int(os.getenv("AEGIS_DEMO_REQUESTS_PER_MINUTE", "20")),
        )


def get_settings() -> Settings:
    return Settings.from_environment()


def provider_status() -> dict[str, str | bool]:
    configuration = get_settings()
    return {
        "llm_mode": configuration.llm_mode,
        "deployment_profile": configuration.deployment_profile,
        "retrieval_mode": "lexical" if configuration.deployment_profile == "lite" else "chroma",
        "embeddings_mode": configuration.embeddings_mode,
        "bedrock_model_id": configuration.bedrock_model_id,
        "bedrock_inference_profile": configuration.bedrock_inference_profile,
        "bedrock_max_tokens": configuration.bedrock_max_tokens,
        "bedrock_embedding_model_id": configuration.bedrock_embedding_model_id,
        "gemini_key_configured": bool(os.getenv("GEMINI_API_KEY")),
        "aws_region_configured": bool(configuration.aws_region),
    }
