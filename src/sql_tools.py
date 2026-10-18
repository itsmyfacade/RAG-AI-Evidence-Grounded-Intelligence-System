"""Approved, read-only operational evidence tools."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.schemas import EvidenceRecord


class OperationalEvidenceStore:
    def __init__(self, database_path: str | Path):
        self.database_path = str(database_path)

    def _connect(self):
        connection = sqlite3.connect(f"file:{self.database_path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def scenario_evidence(self, scenario_id: str) -> list[EvidenceRecord]:
        if not scenario_id.startswith("SCN-"):
            raise ValueError("scenario_id must use the SCN-### format")
        query = """
        SELECT request_id, occurred_at, service, status_code, error_code, deployment_id, event_id
        FROM api_logs WHERE scenario_id = ? ORDER BY occurred_at LIMIT 25
        """
        with self._connect() as conn:
            rows = conn.execute(query, (scenario_id,)).fetchall()
        return [
            EvidenceRecord(
                evidence_id=f"SQL-{scenario_id}-{index:03d}",
                source_type="log",
                source_id=row["request_id"],
                scenario_id=scenario_id,
                excerpt=(f"{row['occurred_at']} {row['service']} returned HTTP {row['status_code']} "
                         f"({row['error_code']}) for {row['request_id']}; deployment={row['deployment_id']}; event={row['event_id']}"),
                metadata={"status_code": str(row["status_code"]), "error_code": row["error_code"] or "", "occurred_at": row["occurred_at"], "deployment_id": row["deployment_id"] or "", "event_id": row["event_id"] or ""},
            )
            for index, row in enumerate(rows, 1)
        ]

    def deployment_and_configuration(self, scenario_id: str) -> list[EvidenceRecord]:
        query = """
        SELECT deployment_id, deployed_at, change_summary FROM deployments WHERE scenario_id = ?
        UNION ALL
        SELECT change_id, changed_at, setting || ': ' || before_value || ' -> ' || after_value
        FROM configuration_changes WHERE scenario_id = ?
        ORDER BY 2
        """
        with self._connect() as conn:
            rows = conn.execute(query, (scenario_id, scenario_id)).fetchall()
        return [
            EvidenceRecord(
                evidence_id=f"OPS-{scenario_id}-{index:03d}",
                source_type="deployment" if row[0].startswith("DEP-") else "configuration",
                source_id=row[0], scenario_id=scenario_id,
                excerpt=f"{row[1]} {row[2]}", metadata={"occurred_at": row[1]},
            )
            for index, row in enumerate(rows, 1)
        ]

    def webhook_evidence(self, scenario_id: str) -> list[EvidenceRecord]:
        query = """
        SELECT event_id, created_at, event_type, delivery_status, attempt_count
        FROM webhook_events WHERE scenario_id = ? ORDER BY created_at
        """
        with self._connect() as conn:
            rows = conn.execute(query, (scenario_id,)).fetchall()
        return [
            EvidenceRecord(
                evidence_id=f"WEBHOOK-{scenario_id}-{index:03d}", source_type="webhook",
                source_id=row["event_id"], scenario_id=scenario_id,
                excerpt=f"{row['created_at']} {row['event_type']} was {row['delivery_status']} after {row['attempt_count']} attempt(s)",
            )
            for index, row in enumerate(rows, 1)
        ]

    def scenario_options(self) -> list[dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT scenario_id, title, domain FROM scenarios ORDER BY scenario_id").fetchall()
        return [{"scenario_id": row[0], "title": row[1], "domain": row[2]} for row in rows]
