from pathlib import Path
import json

documents = [
    ("API-001", "Reporting API Authentication", "api", "1.2",
     "Reporting API requests require a valid bearer token and the reports:read scope. HTTP 401 indicates missing or invalid authentication. HTTP 403 indicates authentication succeeded but authorization was denied. Check token scopes, partner role assignments, and endpoint permissions."),
    ("API-002", "Rate Limits and Retries", "api", "1.1",
     "The Reporting API enforces per-partner request limits. HTTP 429 indicates rate limiting. Clients should use exponential backoff and respect Retry-After headers. Retrying HTTP 403 without correcting authorization will not resolve the failure."),
    ("INC-001", "Post-Deployment 403 Incident", "incident", "1.0",
     "After a deployment, partner reporting requests returned HTTP 403. Investigation identified a missing reports:read scope in the updated partner role mapping. Restoring the required scope resolved the incident. The corrective action was to add authorization regression tests."),
    ("INC-002", "Webhook Delivery Delays", "incident", "1.0",
     "Webhook deliveries were delayed after downstream consumers stopped acknowledging events within the configured timeout. Events entered the retry queue. Engineers verified delivery logs, consumer response times, retry counts, and duplicate event handling."),
    ("INC-003", "Reporting Data Mismatch", "incident", "1.0",
     "A reporting discrepancy was traced to inconsistent UTC date boundaries between an ETL pipeline and the Reporting API. Engineers compared source records, transformation rules, timestamps, and aggregation windows before correcting the transformation."),
    ("RUN-001", "API Incident Triage", "runbook", "2.0",
     "Start with impact, affected partners, timestamps, recent changes, and correlation IDs. Reproduce the request safely. Compare successful and failing requests. Inspect HTTP status codes, authorization, configuration, logs, and downstream dependencies. Document evidence before escalation."),
    ("RUN-002", "Deployment Rollback", "runbook", "1.0",
     "If a deployment introduces a severe regression, confirm the affected release and business impact. Obtain the required approval, restore the last known-good deployment, verify critical API workflows, and document the rollback and follow-up actions."),
    ("SEC-001", "Access Control Policy", "security", "2.1",
     "Production systems must follow least-privilege access. Service credentials should have only necessary permissions. Secrets must not be committed to source control. Authorization failures must be investigated using audit logs and role assignments."),
    ("DATA-001", "ETL Reconciliation Procedure", "data", "1.3",
     "Reconciliation compares source record counts, transformed records, destination counts, identifiers, and monetary totals. Engineers must account for UTC timestamps, duplicates, missing records, schema changes, and delayed ingestion."),
    ("ARCH-001", "Integration Architecture", "architecture", "1.0",
     "The fictional Northstar Integration Cloud consists of a partner API gateway, authentication service, reporting service, webhook dispatcher, ETL jobs, and PostgreSQL storage. Each service emits structured logs with correlation IDs.")
]

output = Path(__file__).resolve().parent / "data" / "documents"
output.mkdir(parents=True, exist_ok=True)

for doc_id, title, category, version, content in documents:
    record = {
        "document_id": doc_id,
        "title": title,
        "category": category,
        "version": version,
        "classification": "internal",
        "content": content
    }
    (output / f"{doc_id}.json").write_text(
        json.dumps(record, indent=2), encoding="utf-8"
    )

print(f"AEGIS: Created {len(documents)} enterprise documents.")
