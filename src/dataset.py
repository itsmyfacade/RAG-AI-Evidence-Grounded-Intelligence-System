"""Deterministic linked operational dataset for local demos and evaluation."""

from __future__ import annotations

import json
import hashlib
import sqlite3
from pathlib import Path

from src.data_schemas import (
    ApiLogRecord,
    ConfigurationChangeRecord,
    DeploymentRecord,
    EvidenceCatalogRecord,
    IncidentRecord,
    PartnerRecord,
    ScenarioRecord,
    SupportTicketRecord,
    WebhookEventRecord,
)
from src.scenario_catalog import public_title


VALIDATORS = {
    "scenario": ScenarioRecord,
    "partner": PartnerRecord,
    "incident": IncidentRecord,
    "deployment": DeploymentRecord,
    "config": ConfigurationChangeRecord,
    "log": ApiLogRecord,
    "ticket": SupportTicketRecord,
    "webhook": WebhookEventRecord,
}


SCENARIOS = [
    ("403_SCOPE", public_title("SCN-001"), "authorization"),
    ("401_TOKEN", public_title("SCN-002"), "authentication"),
    ("429_LIMIT", public_title("SCN-003"), "rate_limit"),
    ("WEBHOOK_DELAY", public_title("SCN-004"), "webhook"),
    ("DUP_EVENT", public_title("SCN-005"), "webhook"),
    ("API_VERSION", public_title("SCN-006"), "compatibility"),
    ("SECRET_ROTATION", public_title("SCN-007"), "credentials"),
    ("REPORTING_DRIFT", public_title("SCN-008"), "data_quality"),
    ("CONFIG_DRIFT", public_title("SCN-009"), "configuration"),
    ("DEPLOY_REGRESSION", public_title("SCN-010"), "deployment"),
    ("EVENT_DELAY", public_title("SCN-011"), "webhook"),
    ("RECONCILIATION", public_title("SCN-012"), "data_quality"),
    ("ONBOARDING", public_title("SCN-013"), "onboarding"),
    ("OAUTH_SCOPE", public_title("SCN-014"), "authorization"),
    ("DLQ_SCHEMA", public_title("SCN-015"), "compatibility"),
    ("ACCESS_AUDIT", public_title("SCN-016"), "security"),
    ("LATENCY", public_title("SCN-017"), "performance"),
    ("MISSING_LOGS", public_title("SCN-018"), "observability"),
    ("TICKET_CONFLICT", public_title("SCN-019"), "investigation"),
    ("PARTNER_REPLAY", public_title("SCN-020"), "recovery"),
]


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS scenarios (
  scenario_id TEXT PRIMARY KEY, title TEXT NOT NULL, domain TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS partners (
  partner_id TEXT PRIMARY KEY, name TEXT NOT NULL, environment TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS incidents (
  incident_id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL REFERENCES scenarios,
  partner_id TEXT NOT NULL REFERENCES partners, service TEXT NOT NULL,
  opened_at TEXT NOT NULL, resolved_at TEXT, observed_status INTEGER
);
CREATE TABLE IF NOT EXISTS deployments (
  deployment_id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL REFERENCES scenarios,
  service TEXT NOT NULL, environment TEXT NOT NULL, deployed_at TEXT NOT NULL,
  change_summary TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS configuration_changes (
  change_id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL REFERENCES scenarios,
  partner_id TEXT NOT NULL REFERENCES partners, changed_at TEXT NOT NULL,
  setting TEXT NOT NULL, before_value TEXT NOT NULL, after_value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS api_logs (
  log_id INTEGER PRIMARY KEY, scenario_id TEXT NOT NULL REFERENCES scenarios,
  request_id TEXT NOT NULL, partner_id TEXT NOT NULL REFERENCES partners,
  service TEXT NOT NULL, environment TEXT NOT NULL, occurred_at TEXT NOT NULL,
  endpoint TEXT NOT NULL, status_code INTEGER NOT NULL, error_code TEXT,
  deployment_id TEXT REFERENCES deployments, event_id TEXT, latency_ms INTEGER
);
CREATE TABLE IF NOT EXISTS support_tickets (
  ticket_id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL REFERENCES scenarios,
  partner_id TEXT NOT NULL REFERENCES partners, opened_at TEXT NOT NULL,
  summary TEXT NOT NULL, resolution TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS webhook_events (
  event_id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL REFERENCES scenarios,
  partner_id TEXT NOT NULL REFERENCES partners, created_at TEXT NOT NULL,
  event_type TEXT NOT NULL, delivery_status TEXT NOT NULL,
  attempt_count INTEGER NOT NULL, acknowledged_at TEXT
);
CREATE TABLE IF NOT EXISTS evidence_catalog (
  evidence_id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL REFERENCES scenarios,
  source_type TEXT NOT NULL, source_id TEXT NOT NULL, content_hash TEXT NOT NULL,
  lineage TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_logs_scenario ON api_logs(scenario_id);
CREATE INDEX IF NOT EXISTS idx_deployments_scenario ON deployments(scenario_id);
CREATE INDEX IF NOT EXISTS idx_webhook_scenario ON webhook_events(scenario_id);
"""


def _rows(scenario_number: int, code: str, title: str, domain: str):
    scenario_id = f"SCN-{scenario_number:03d}"
    partner_id = f"PARTNER-{scenario_number:03d}"
    incident_id = f"INC-SCN-{scenario_number:03d}"
    deployment_id = f"DEP-{scenario_number:03d}"
    changed_id = f"CFG-{scenario_number:03d}"
    observed_status = {"403_SCOPE": 403, "401_TOKEN": 401, "429_LIMIT": 429}.get(code, 500)
    yield "scenario", (scenario_id, title, domain, f"2026-01-{(scenario_number % 28) + 1:02d}T00:00:00Z")
    yield "partner", (partner_id, f"Northstar Partner {scenario_number:03d}", "production" if scenario_number % 2 else "sandbox")
    yield "incident", (incident_id, scenario_id, partner_id, "reporting-service", f"2026-01-{(scenario_number % 28) + 1:02d}T10:00:00Z", f"2026-01-{(scenario_number % 28) + 1:02d}T12:00:00Z", observed_status)
    deployment_time = f"2026-01-{(scenario_number % 28) + 1:02d}T10:45:00Z" if code == "TICKET_CONFLICT" else f"2026-01-{(scenario_number % 28) + 1:02d}T09:30:00Z"
    yield "deployment", (deployment_id, scenario_id, "reporting-service", "production", deployment_time, f"Changed integration behavior for {domain}")
    yield "config", (changed_id, scenario_id, partner_id, f"2026-01-{(scenario_number % 28) + 1:02d}T09:15:00Z", "integration_setting", "approved", "changed")
    for log_index in range(12):
        log_id = (scenario_number * 100) + log_index
        log_deployment_id = None if code == "MISSING_LOGS" and log_index >= 4 else deployment_id
        log_event_id = None if code == "MISSING_LOGS" and log_index >= 4 else f"EVT-{scenario_number:03d}-{log_index:02d}"
        yield "log", (log_id, scenario_id, f"REQ-{scenario_number:03d}-{log_index:02d}", partner_id, "reporting-service", "production", f"2026-01-{(scenario_number % 28) + 1:02d}T10:{log_index:02d}:00Z", "/v1/reporting", observed_status or 200, f"{domain.upper()}_ERROR", log_deployment_id, log_event_id, 120 + log_index * 10)
    yield "ticket", (f"TICKET-{scenario_number:03d}", scenario_id, partner_id, f"2026-01-{(scenario_number % 28) + 1:02d}T10:30:00Z", f"Support request for {domain} integration investigation", "Followed documented investigation procedure")
    for event_index in range(4):
        yield "webhook", (f"EVT-{scenario_number:03d}-{event_index:02d}", scenario_id, partner_id, f"2026-01-{(scenario_number % 28) + 1:02d}T10:{event_index:02d}:30Z", "report.updated", "delayed" if domain == "webhook" else "delivered", event_index + 1, None if domain == "webhook" else f"2026-01-{(scenario_number % 28) + 1:02d}T10:{event_index + 1:02d}:00Z")


def generate_database(path: str | Path) -> dict[str, int]:
    """Create the same database contents on every run using a transaction."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(target) as conn:
        for table in ("evidence_catalog", "webhook_events", "api_logs", "support_tickets", "configuration_changes", "deployments", "incidents", "partners", "scenarios"):
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.executescript(SCHEMA)
        for i, (code, title, domain) in enumerate(SCENARIOS, 1):
            for kind, row in _rows(i, code, title, domain):
                model = VALIDATORS[kind]
                model.model_validate(dict(zip(model.model_fields, row)))
                if kind == "scenario":
                    conn.execute("INSERT INTO scenarios VALUES (?,?,?,?)", row)
                elif kind == "partner":
                    conn.execute("INSERT INTO partners VALUES (?,?,?)", row)
                elif kind == "incident":
                    conn.execute("INSERT INTO incidents VALUES (?,?,?,?,?,?,?)", row)
                elif kind == "deployment":
                    conn.execute("INSERT INTO deployments VALUES (?,?,?,?,?,?)", row)
                elif kind == "config":
                    conn.execute("INSERT INTO configuration_changes VALUES (?,?,?,?,?,?,?)", row)
                elif kind == "log":
                    conn.execute("INSERT INTO api_logs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", row)
                elif kind == "ticket":
                    conn.execute("INSERT INTO support_tickets VALUES (?,?,?,?,?,?)", row)
                elif kind == "webhook":
                    conn.execute("INSERT INTO webhook_events VALUES (?,?,?,?,?,?,?,?)", row)
        document_dir = Path(__file__).resolve().parents[1] / "data" / "documents"
        for index, document_path in enumerate(sorted(document_dir.glob("*.json"))):
            content = document_path.read_text(encoding="utf-8")
            record = json.loads(content)
            scenario_id = f"SCN-{((index) % len(SCENARIOS)) + 1:03d}"
            EvidenceCatalogRecord(
                evidence_id=f"DOC-{record['document_id']}", scenario_id=scenario_id,
                source_type="technical_document", source_id=record["document_id"],
                content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                lineage=str(document_path).replace("\\", "/"),
            )
            conn.execute(
                "INSERT INTO evidence_catalog VALUES (?,?,?,?,?,?)",
                (f"DOC-{record['document_id']}", scenario_id, "technical_document", record["document_id"], hashlib.sha256(content.encode("utf-8")).hexdigest(), str(document_path).replace("\\", "/")),
            )
        counts = {}
        for table in ("scenarios", "partners", "incidents", "deployments", "configuration_changes", "api_logs", "webhook_events", "support_tickets", "evidence_catalog"):
            counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return counts


def validate_database(path: str | Path) -> dict[str, int]:
    """Validate row counts and foreign-key integrity without changing the DB."""
    with sqlite3.connect(path) as connection:
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise ValueError(f"Foreign-key violations detected: {len(violations)}")
        counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("scenarios", "incidents", "deployments", "configuration_changes", "api_logs", "webhook_events", "support_tickets", "evidence_catalog")}
    if counts["scenarios"] < 20 or counts["incidents"] != counts["scenarios"]:
        raise ValueError("Dataset scenario/incident counts are invalid")
    return counts


if __name__ == "__main__":
    from src.settings import get_settings
    print(json.dumps(generate_database(get_settings().database_path), indent=2))
