from pathlib import Path
import json

root = Path(__file__).resolve().parent / "data" / "documents"

additional = [
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
    ("ARCH-003", "Reporting Data Flow", "architecture", "Operational records flow through ingestion, validation, transformation, PostgreSQL storage, and reporting APIs.", "Reconciliation checks each stage to isolate missing or inconsistent records.")
]

for doc_id, title, category, content, resolution in additional:
    record = {
        "document_id": doc_id,
        "title": title,
        "category": category,
        "version": "1.0",
        "classification": "internal",
        "content": (
            f"Purpose: {title}.\n\n"
            f"Technical details: {content}\n\n"
            f"Operational guidance: {resolution}\n\n"
            "Investigation evidence: Record affected services, timestamps, "
            "correlation identifiers, observed behavior, expected behavior, "
            "recent changes, and reproducible diagnostic steps.\n\n"
            "Verification: Compare outcomes against documented requirements. "
            "Do not claim a root cause without supporting evidence. "
            "Document unresolved uncertainty and recommended follow-up."
        )
    }
    (root / f"{doc_id}.json").write_text(
        json.dumps(record, indent=2), encoding="utf-8"
    )

print(f"AEGIS dataset: {len(list(root.glob('*.json')))} documents")
