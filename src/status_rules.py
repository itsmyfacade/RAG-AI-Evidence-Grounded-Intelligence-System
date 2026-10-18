"""Evidence-derived status rules used by the serving workflow."""

from __future__ import annotations

from datetime import UTC, datetime

from langchain_core.documents import Document

from src.schemas import EvidenceRecord

MIN_CORRELATED_FRACTION = 0.5


def _timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or UTC)
    except (TypeError, ValueError):
        return None


def _has_timestamp_conflict(logs: list[EvidenceRecord], deployments: list[EvidenceRecord]) -> bool:
    deployment_times = [_timestamp(record.metadata.get("occurred_at")) for record in deployments]
    deployment_times = [value for value in deployment_times if value is not None]
    if not deployment_times:
        return False
    earliest_deployment = min(deployment_times)
    log_times = [_timestamp(record.metadata.get("occurred_at")) for record in logs]
    return any(value is not None and value < earliest_deployment for value in log_times)


def classify_status(documents: list[Document], operational: list[EvidenceRecord]) -> tuple[str, list[str], list[str]]:
    """Return status, evidence gaps, and contradictions without evaluator labels."""
    gaps: list[str] = []
    contradictions: list[str] = []
    if not documents:
        return "insufficient_evidence", ["No narrative documents were retrieved."], contradictions
    if not operational:
        return "insufficient_evidence", ["No structured operational evidence was available."], contradictions

    logs = [record for record in operational if record.source_type == "log"]
    correlated = [record for record in logs if record.metadata.get("deployment_id") and record.metadata.get("event_id")]
    if logs and len(correlated) / len(logs) < MIN_CORRELATED_FRACTION:
        gaps.append("Required deployment and event correlation is missing for a material share of the affected logs.")
        return "insufficient_evidence", gaps, contradictions

    deployments = [record for record in operational if record.source_type == "deployment"]
    if _has_timestamp_conflict(logs, deployments):
        contradictions.append("Observed request timestamps precede the available deployment timestamp; reconcile source clocks and deployment records.")
        return "escalated", gaps, contradictions
    return "completed", gaps, contradictions
