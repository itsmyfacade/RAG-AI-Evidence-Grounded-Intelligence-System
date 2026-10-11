"""Pydantic schemas for generated operational records."""

from pydantic import BaseModel, Field


class ScenarioRecord(BaseModel):
    scenario_id: str
    title: str
    domain: str
    expected_outcome: str
    created_at: str
    evidence_profile: str
    expected_status: str
    conflict_note: str


class PartnerRecord(BaseModel):
    partner_id: str
    name: str
    environment: str


class IncidentRecord(BaseModel):
    incident_id: str
    scenario_id: str
    partner_id: str
    service: str
    opened_at: str
    resolved_at: str | None
    observed_status: int | None
    root_cause: str


class DeploymentRecord(BaseModel):
    deployment_id: str
    scenario_id: str
    service: str
    environment: str
    deployed_at: str
    change_summary: str


class ConfigurationChangeRecord(BaseModel):
    change_id: str
    scenario_id: str
    partner_id: str
    changed_at: str
    setting: str
    before_value: str
    after_value: str


class ApiLogRecord(BaseModel):
    log_id: int
    scenario_id: str
    request_id: str
    partner_id: str
    service: str
    environment: str
    occurred_at: str
    endpoint: str
    status_code: int = Field(ge=100, le=599)
    error_code: str | None
    deployment_id: str | None
    event_id: str | None
    latency_ms: int = Field(ge=0)


class WebhookEventRecord(BaseModel):
    event_id: str
    scenario_id: str
    partner_id: str
    created_at: str
    event_type: str
    delivery_status: str
    attempt_count: int = Field(ge=1)
    acknowledged_at: str | None


class SupportTicketRecord(BaseModel):
    ticket_id: str
    scenario_id: str
    partner_id: str
    opened_at: str
    summary: str
    resolution: str


class EvidenceCatalogRecord(BaseModel):
    evidence_id: str
    scenario_id: str
    source_type: str
    source_id: str
    content_hash: str
    lineage: str
