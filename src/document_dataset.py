"""Deterministic narrative-document generation for the AEGIS demo corpus."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DocumentSeed:
    document_id: str
    title: str
    category: str
    version: str
    content: str


BASE_DOCUMENTS = (
    DocumentSeed("API-001", "Reporting API Authentication", "api", "1.2", "Reporting API requests require a valid bearer token and the reports:read scope. HTTP 401 indicates missing or invalid authentication. HTTP 403 indicates authentication succeeded but authorization was denied. Check token scopes, partner role assignments, and endpoint permissions."),
    DocumentSeed("API-002", "Rate Limits and Retries", "api", "1.1", "The Reporting API enforces per-partner request limits. HTTP 429 indicates rate limiting. Clients should use exponential backoff and respect Retry-After headers. Retrying HTTP 403 without correcting authorization will not resolve the failure."),
    DocumentSeed("INC-001", "Post-Deployment 403 Incident", "incident", "1.0", "After a deployment, partner reporting requests returned HTTP 403. Investigation identified a missing reports:read scope in the updated partner role mapping. Restoring the required scope resolved the incident. The corrective action was to add authorization regression tests."),
    DocumentSeed("INC-002", "Webhook Delivery Delays", "incident", "1.0", "Webhook deliveries were delayed after downstream consumers stopped acknowledging events within the configured timeout. Events entered the retry queue. Engineers verified delivery logs, consumer response times, retry counts, and duplicate event handling."),
    DocumentSeed("INC-003", "Reporting Data Mismatch", "incident", "1.0", "A reporting discrepancy was traced to inconsistent UTC date boundaries between an ETL pipeline and the Reporting API. Engineers compared source records, transformation rules, timestamps, and aggregation windows before correcting the transformation."),
    DocumentSeed("RUN-001", "API Incident Triage", "runbook", "2.0", "Start with impact, affected partners, timestamps, recent changes, and correlation IDs. Reproduce the request safely. Compare successful and failing requests. Inspect HTTP status codes, authorization, configuration, logs, and downstream dependencies. Document evidence before escalation."),
    DocumentSeed("RUN-002", "Deployment Rollback", "runbook", "1.0", "If a deployment introduces a severe regression, confirm the affected release and business impact. Obtain the required approval, restore the last known-good deployment, verify critical API workflows, and document the rollback and follow-up actions."),
    DocumentSeed("SEC-001", "Access Control Policy", "security", "2.1", "Production systems must follow least-privilege access. Service credentials should have only necessary permissions. Secrets must not be committed to source control. Authorization failures must be investigated using audit logs and role assignments."),
    DocumentSeed("DATA-001", "ETL Reconciliation Procedure", "data", "1.3", "Reconciliation compares source record counts, transformed records, destination counts, identifiers, and monetary totals. Engineers must account for UTC timestamps, duplicates, missing records, schema changes, and delayed ingestion."),
    DocumentSeed("ARCH-001", "Integration Architecture", "architecture", "1.0", "The fictional Northstar Integration Cloud consists of a partner API gateway, authentication service, reporting service, webhook dispatcher, ETL jobs, and PostgreSQL storage. Each service emits structured logs with correlation IDs."),
)


ADDITIONAL_DOCUMENTS = (
    ("API-003", "API Pagination", "api", "Cursor-based pagination uses an opaque next_cursor token. Clients must not invent cursor values. Empty pages do not necessarily mean the export is complete when a next_cursor is present.", "Pagination incidents should compare request parameters, cursor history, response headers, and dataset consistency."),
    ("API-004", "API Error Contract", "api", "The API returns structured errors containing code, message, request_id, and timestamp. HTTP 400 indicates invalid input, 401 authentication failure, 403 authorization failure, 429 throttling, and 5xx server errors.", "Troubleshooting should preserve request_id, status code, endpoint, time, and a sanitized request sample."),
    ("API-005", "Webhook Delivery Contract", "api", "Webhook events contain event_id, event_type, created_at, and payload. Consumers should acknowledge successful receipt with HTTP 2xx and process repeated event_id values idempotently.", "Retries can deliver duplicate events. Use event identifiers and processing records to prevent duplicate side effects."),
    ("API-006", "Partner Configuration", "api", "Partner integrations have separate sandbox and production credentials, allowed endpoints, scopes, and webhook destinations. Changes require validation before deployment.", "Compare environment-specific configuration and audit history when a previously working integration fails."),
    ("INC-004", "Expired Signing Secret", "incident", "Webhook signature verification failed after a secret rotation because a consumer retained the previous signing secret. Delivery attempts were rejected despite valid payloads.", "The team synchronized secrets, verified signatures, and added a rotation checklist."),
    ("INC-005", "Duplicate Order Processing", "incident", "A consumer processed webhook retries as new transactions because it did not persist event_id values. Duplicate downstream records were created.", "The remediation introduced idempotency checks, unique event constraints, and replay testing."),
    ("INC-006", "API Latency Regression", "incident", "A reporting deployment increased query latency after an index was removed from a frequently filtered database column. Requests began timing out.", "Engineers compared query plans, database metrics, and release changes before restoring the index."),
    ("INC-007", "Schema Version Mismatch", "incident", "An ETL job failed when the source API added a nullable field and the destination schema rejected the payload. Records accumulated in a dead-letter queue.", "The team updated schema validation, replayed failed records, and added contract tests."),
    ("INC-008", "Credential Scope Regression", "incident", "A partner's read-only token lost its reporting scope after a configuration deployment. Authentication succeeded but reporting requests returned HTTP 403.", "The incident was resolved by restoring the approved scope and testing role mappings."),
    ("RUN-003", "Webhook Troubleshooting", "runbook", "Check event creation, delivery attempts, destination availability, signature verification, acknowledgment status, retries, and idempotency records.", "Collect event_id, response status, attempt timestamps, and sanitized payload metadata."),
    ("RUN-004", "Data Quality Investigation", "runbook", "Compare source and destination counts, transformations, timestamps, null values, duplicates, and schema versions.", "Use SQL aggregation and reconciliation reports to identify the earliest divergence."),
    ("RUN-005", "Security Escalation", "runbook", "Suspected credential compromise requires containment, security notification, evidence preservation, and approved credential rotation.", "Never paste secrets into tickets, logs, or external AI prompts."),
    ("SEC-002", "Secrets Management", "security", "Credentials and API tokens must be stored outside source code. Applications should use environment-based configuration or approved secret management services.", "Logs must redact authorization headers, access tokens, passwords, and signing secrets."),
    ("SEC-003", "Audit Logging", "security", "Audit records should capture actor, action, resource, timestamp, outcome, and correlation identifier.", "Investigators should preserve relevant evidence while avoiding unnecessary sensitive data exposure."),
    ("SEC-004", "AI Retrieval Security", "security", "Retrieved documents are untrusted inputs. Instructions embedded inside documents must not override system-level rules.", "Retrieval must enforce document access restrictions before content reaches the language model."),
    ("DATA-002", "Schema Evolution", "data", "Schema changes should preserve compatibility where possible. Producers and consumers must validate field types, optionality, and version expectations.", "Use contract tests and controlled rollout procedures."),
    ("DATA-003", "Metadata Catalog", "data", "Documents are indexed by document_id, category, version, classification, and source path. Metadata supports filtering and evidence traceability.", "Catalog entries must be validated and consistently normalized."),
    ("DATA-004", "Duplicate Detection", "data", "Duplicate records can be identified using stable business identifiers, event identifiers, and controlled uniqueness rules.", "Reconciliation should distinguish legitimate retries from duplicated business transactions."),
    ("ARCH-002", "Authentication Architecture", "architecture", "API Gateway validates requests and delegates authorization to a service that evaluates token scopes and partner roles.", "Authorization decisions are logged with correlation IDs and sanitized metadata."),
    ("ARCH-003", "Reporting Data Flow", "architecture", "Operational records flow through ingestion, validation, transformation, PostgreSQL storage, and reporting APIs.", "Reconciliation checks each stage to isolate missing or inconsistent records."),
)


def additional_document_seeds() -> tuple[DocumentSeed, ...]:
    """Return the stable 20-document extension used by the legacy wrapper."""
    return tuple(
        DocumentSeed(
            document_id=document_id,
            title=title,
            category=category,
            version="1.0",
            content=(
                f"Purpose: {title}.\n\nTechnical details: {technical}\n\n"
                f"Operational guidance: {guidance}\n\nInvestigation evidence: Record affected services, timestamps, "
                "correlation identifiers, observed behavior, expected behavior, recent changes, and reproducible diagnostic steps.\n\n"
                "Verification: Compare outcomes against documented requirements. Do not claim a root cause without supporting evidence. "
                "Document unresolved uncertainty and recommended follow-up."
            ),
        )
        for document_id, title, category, technical, guidance in ADDITIONAL_DOCUMENTS
    )


def all_document_seeds() -> tuple[DocumentSeed, ...]:
    """Return the stable 30-document corpus in generation order."""
    return BASE_DOCUMENTS + additional_document_seeds()


def _payload(seed: DocumentSeed) -> str:
    return json.dumps(
        {
            "document_id": seed.document_id,
            "title": seed.title,
            "category": seed.category,
            "version": seed.version,
            "classification": "internal",
            "content": seed.content,
        },
        indent=2,
    )


def generate_documents(output_dir: str | Path, *, records: tuple[DocumentSeed, ...] | None = None, replace: bool = False) -> dict[str, int]:
    """Create missing documents and refuse conflicting existing files by default."""
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    seeds = records or all_document_seeds()
    created = 0
    unchanged = 0
    for seed in seeds:
        path = target / f"{seed.document_id}.json"
        payload = _payload(seed)
        if path.exists():
            if path.read_text(encoding="utf-8") == payload:
                unchanged += 1
                continue
            if not replace:
                raise FileExistsError(f"Existing document differs; use --replace-documents: {path}")
        path.write_text(payload, encoding="utf-8")
        created += 1
    return {"expected": len(seeds), "created": created, "unchanged": unchanged}


def validate_documents(output_dir: str | Path, *, expected_count: int = 30) -> dict[str, int]:
    """Validate document structure and stable identifiers without changing files."""
    target = Path(output_dir)
    paths = sorted(target.glob("*.json"))
    expected_ids = {seed.document_id for seed in all_document_seeds()}
    actual_ids = set()
    for path in paths:
        record = json.loads(path.read_text(encoding="utf-8"))
        required = {"document_id", "title", "category", "version", "classification", "content"}
        if set(record) != required:
            raise ValueError(f"Invalid document schema: {path}")
        actual_ids.add(record["document_id"])
    if len(paths) != expected_count or actual_ids != expected_ids:
        raise ValueError(f"Document corpus mismatch: expected {expected_count} files and stable IDs")
    return {"documents": len(paths), "identifiers": len(actual_ids)}
