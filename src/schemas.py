"""Typed contracts shared by the dataset, tools, graph, and API."""

from typing import Any, Literal

from pydantic import BaseModel, Field


EvidenceKind = Literal["document", "sql", "log", "deployment", "configuration", "ticket", "webhook"]
SupportStatus = Literal["supported", "partially_supported", "unsupported", "unverified"]


class EvidenceRecord(BaseModel):
    evidence_id: str
    source_type: EvidenceKind
    source_id: str
    excerpt: str = Field(min_length=1)
    scenario_id: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class Claim(BaseModel):
    claim_id: str
    statement: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)
    support_status: SupportStatus = "unverified"
    rationale: str = ""


class Finding(BaseModel):
    finding_id: str
    statement: str
    status: Literal["observation", "hypothesis", "conclusion"]
    claim_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class GeneratedFinding(BaseModel):
    statement: str = Field(min_length=1, max_length=1200)
    status: Literal["observation", "hypothesis", "conclusion"]
    evidence_refs: list[str]


class GeneratedSynthesis(BaseModel):
    summary: str = Field(min_length=1, max_length=2000)
    findings: list[GeneratedFinding] = Field(max_length=3)
    uncertainty: list[str] = Field(max_length=3)
    recommended_checks: list[str] = Field(max_length=3)
    evidence_gaps: list[str] = Field(max_length=3)


class AgentTrace(BaseModel):
    step: str
    status: Literal["started", "completed", "skipped", "failed"]
    detail: str = ""


class InvestigationReport(BaseModel):
    investigation_id: str
    question: str
    status: Literal["completed", "insufficient_evidence", "escalated", "failed"]
    summary: str
    findings: list[Finding] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    recommended_checks: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    agent_trace: list[AgentTrace] = Field(default_factory=list)
    provider: str = "local"
    retrieval_mode: str = "unknown"
    model: str | None = None
    token_usage: dict[str, int] = Field(default_factory=dict)
    provider_error: str | None = None
    attempts: int = 0
    provider_diagnostics: dict[str, Any] = Field(default_factory=dict)


class InvestigationRequest(BaseModel):
    question: str = Field(min_length=5, max_length=1000)
    scenario_id: str | None = Field(default=None, pattern=r"^SCN-[0-9]{3}$")


class InvestigationResponse(BaseModel):
    investigation_id: str
    question: str
    status: str
    answer: str
    citations: list[str]
    mode: str
    report: InvestigationReport
    agent_trace: list[AgentTrace]
