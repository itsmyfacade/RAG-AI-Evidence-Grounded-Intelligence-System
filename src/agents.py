"""Bounded LangGraph investigation orchestration."""

from __future__ import annotations

import re
from typing import TypedDict
from uuid import uuid4

from langchain_core.documents import Document
from langgraph.graph import END, START, StateGraph

from src.evidence import EvidenceRegistry, assess_claim_support
from src.providers import ProviderError, get_provider
from src.rag import search
from src.schemas import AgentTrace, Claim, EvidenceRecord, Finding, InvestigationReport
from src.settings import get_settings
from src.sql_tools import OperationalEvidenceStore
from src.status_rules import classify_status


class InvestigationState(TypedDict, total=False):
    investigation_id: str
    question: str
    scenario_id: str | None
    documents: list[Document]
    operational_evidence: list[EvidenceRecord]
    evidence: list[EvidenceRecord]
    answer: str
    citations: list[str]
    mode: str
    attempts: int
    max_attempts: int
    route: str
    provider_error: str
    provider_model: str | None
    token_usage: dict[str, int]
    provider_diagnostics: dict
    structured_output: dict
    report: InvestigationReport
    trace: list[AgentTrace]


def _trace(state, step, status, detail=""):
    return [*state.get("trace", []), AgentTrace(step=step, status=status, detail=detail)]


def supervisor(state: InvestigationState):
    question = state["question"]
    scenario_id = state.get("scenario_id") or next(iter(re.findall(r"SCN-\d{3}", question.upper())), None)
    return {"scenario_id": scenario_id, "attempts": state.get("attempts", 0) + 1, "trace": _trace(state, "supervisor", "completed", f"Selected document and operational research; scenario={scenario_id or 'unspecified'}")}


def document_research(state: InvestigationState):
    docs = search(state["question"], k=4)
    evidence = [
        EvidenceRecord(
            evidence_id=f"DOC-{doc.metadata['document_id']}-{doc.metadata.get('chunk_index', 0)}",
            source_type="document",
            source_id=doc.metadata["document_id"],
            scenario_id=state.get("scenario_id"),
            excerpt=doc.page_content,
            metadata={"title": doc.metadata.get("title", ""), "category": doc.metadata.get("category", "")},
        )
        for doc in docs
    ]
    return {"documents": docs, "evidence": evidence, "trace": _trace(state, "document_research", "completed", f"Retrieved {len(docs)} document passages")}


def operations_analysis(state: InvestigationState):
    scenario_id = state.get("scenario_id")
    operational = []
    database_path = get_settings().database_path
    if scenario_id and database_path.exists():
        store = OperationalEvidenceStore(database_path)
        operational = store.scenario_evidence(scenario_id) + store.deployment_and_configuration(scenario_id) + store.webhook_evidence(scenario_id)
    else:
        operational = []
    return {"operational_evidence": operational, "evidence": [*state.get("evidence", []), *operational], "trace": _trace(state, "operations_analysis", "completed", f"Returned {len(operational)} structured evidence records")}


def _scenario_suffix(scenario_id: str | None) -> str | None:
    match = re.search(r"(\d{3})$", scenario_id or "")
    return match.group(1) if match else None


def _document_bucket(record: EvidenceRecord, scenario_id: str | None) -> str:
    if record.source_type != "document":
        return "operational"
    if record.metadata.get("scenario_id") and record.metadata.get("scenario_id") == scenario_id:
        return "direct_incident"
    category = record.metadata.get("category", "").lower()
    suffix = _scenario_suffix(scenario_id)
    source_suffix = re.search(r"(\d{3})$", record.source_id)
    if category == "incident" and suffix and source_suffix and source_suffix.group(1) == suffix:
        return "direct_incident"
    if category in {"api", "runbook", "security", "architecture", "data"}:
        return "reference"
    return "background"


def _documented_causal_statements(excerpt: str) -> list[str]:
    statements = []
    for sentence in re.split(r"(?<=[.!?])\s+", excerpt):
        normalized = sentence.strip()
        if normalized and re.search(r"\b(because|caused|due to|resulted in|after|when|failed to|did not)\b", normalized, re.IGNORECASE):
            statements.append(normalized[:400])
    return statements[:2]


def _clear_causal_mechanism(statement: str) -> str | None:
    lowered = statement.lower()
    if re.search(r"\b(?:not|no|never)\s+(?:caused by|due to)\b|\b(?:may|might|could|possibly)\s+be\s+caused\s+by\b|\b(?:hypothesis|hypothetical)\b", lowered):
        return None
    patterns = (
        r"\bbecause\s+(.+)",
        r"\bcaused\s+by\s+(.+)",
        r"\bdue\s+to\s+(.+)",
        r"\bresulted\s+in\s+(.+)",
        r"\bfailed\s+to\s+(.+)",
        r"\bdid\s+not\s+([a-z][^.;!?]*)",
    )
    for pattern in patterns:
        match = re.search(pattern, statement, re.IGNORECASE)
        if match:
            return match.group(1).strip(" .;:,")[:400]
    return None


def _mechanism_terms(text: str) -> set[str]:
    terms = set(re.findall(r"[a-zA-Z][a-zA-Z0-9_:-]{3,}", text.lower()))
    ignored = {"because", "caused", "cause", "resulted", "failed", "does", "did", "that", "this", "with", "from", "into", "their", "they"}
    normalized = set()
    for term in terms - ignored:
        if term.endswith("ing") and len(term) > 6:
            term = term[:-3]
        elif term.endswith("ed") and len(term) > 5:
            term = term[:-2]
        elif term.endswith("s") and not term.endswith("ss") and len(term) > 5:
            term = term[:-1]
        normalized.add(term)
    return normalized


def _documented_cause_coverage_gaps(state: InvestigationState, structured: dict, registry: EvidenceRegistry) -> list[str]:
    """Flag omitted clear documented mechanisms without asserting operational truth."""
    findings = structured.get("findings", [])
    finding_text = " ".join(str(item.get("statement", "")) for item in findings)
    finding_terms = _mechanism_terms(finding_text)
    gaps = []
    for record in state.get("evidence", []):
        if _document_bucket(record, state.get("scenario_id")) != "direct_incident":
            continue
        for causal_statement in _documented_causal_statements(record.excerpt):
            mechanism = _clear_causal_mechanism(causal_statement)
            mechanism_terms = _mechanism_terms(mechanism or "")
            if len(mechanism_terms) < 2:
                continue
            if len(mechanism_terms & finding_terms) < 2:
                gaps.append(f"Documented causal mechanism not addressed: [{record.evidence_id}] {causal_statement}")
    return gaps


def _evidence_brief(state: InvestigationState, *, canonical_ids: bool = True) -> str:
    """Build a bounded, labeled brief without changing the evidence registry."""
    scenario_id = state.get("scenario_id")
    groups: dict[str, list[EvidenceRecord]] = {"direct_incident": [], "operational": [], "reference": [], "background": []}
    for record in state.get("evidence", []):
        groups[_document_bucket(record, scenario_id)].append(record)

    lines = [f"Investigation scenario: {scenario_id or 'unspecified'}"]
    labels = {
        "direct_incident": "DIRECTLY RELEVANT INCIDENT DOCUMENTATION",
        "operational": "OBSERVED OPERATIONAL RECORDS",
        "reference": "GENERAL CONTRACTS AND RUNBOOKS",
        "background": "LOWER-CONFIDENCE OR CROSS-INCIDENT BACKGROUND",
    }
    for bucket in ("direct_incident", "operational", "reference", "background"):
        lines.append(f"\n{labels[bucket]}:")
        if not groups[bucket]:
            lines.append("(none)")
            continue
        for record in groups[bucket]:
            evidence_id = record.evidence_id if canonical_ids else record.source_id
            line = f"[{evidence_id}] source_type={record.source_type}; source_reference={record.source_id}; excerpt={record.excerpt[:700]}"
            if bucket == "direct_incident":
                causal = _documented_causal_statements(record.excerpt)
                line += f"; documented_causal_statements={causal if causal else ['none explicitly detected']}"
            elif bucket == "background":
                line += "; classification=not direct proof of this scenario"
            lines.append(line)
    return "\n".join(lines)


def investigation_synthesis(state: InvestigationState):
    mode = get_settings().llm_mode
    evidence_text = [_evidence_brief(state, canonical_ids=mode != "local")]
    try:
        generated = get_provider(mode).generate(state["question"], evidence_text)
        answer, provider = generated.text, generated.provider
        return {
            "answer": answer,
            "mode": provider,
            "provider_model": generated.model,
            "token_usage": generated.token_usage or {},
            "provider_diagnostics": generated.diagnostics or {},
            "structured_output": generated.structured or {},
            "trace": _trace(state, "investigation_synthesis", "completed", f"Used provider={provider}; model={generated.model or 'unspecified'}"),
        }
    except ProviderError as exc:
        answer = f"Investigation could not complete with provider '{exc.provider}': {exc.kind}. No silent provider fallback was used."
        provider = exc.provider
        configuration = get_settings()
        provider_model = configuration.bedrock_inference_profile if provider == "bedrock" else configuration.gemini_model if provider == "gemini" else "deterministic-local"
        return {
            "answer": answer,
            "mode": provider,
            "provider_error": f"{exc.provider}:{exc.kind}",
            "provider_model": provider_model,
            "token_usage": exc.diagnostics.get("cumulative_token_usage", exc.diagnostics.get("token_usage", {})),
            "provider_diagnostics": exc.diagnostics,
            "trace": _trace(state, "investigation_synthesis", "failed", f"Provider failure: {exc.kind}"),
        }


def _record_ids(records: list[EvidenceRecord], *, source_types: set[str] | None = None, limit: int = 6) -> list[str]:
    selected = [record.evidence_id for record in records if source_types is None or record.source_type in source_types]
    return selected[:limit]


def _report_summary(status: str, state: InvestigationState, documents: list[Document], operational: list[EvidenceRecord]) -> str:
    if status == "failed":
        return "Assessment unavailable: evidence validation rejected one or more citations."
    if status == "insufficient_evidence":
        return f"Assessment: insufficient evidence. Retrieved {len(documents)} narrative passages and {len(operational)} structured records, but the scenario is missing required correlation evidence."
    if status == "escalated":
        return f"Assessment: conflicting evidence requires review. Retrieved {len(documents)} narrative passages and {len(operational)} structured records, but the available sources do not agree."
    return f"Assessment: evidence is available for this investigation ({len(documents)} narrative passages and {len(operational)} structured records). It supports further diagnosis but does not prove a production root cause."


def _report_findings(status: str, state: InvestigationState, registry: EvidenceRegistry, claims: list[Claim], structured: dict | None = None) -> list[Finding]:
    if structured and structured.get("findings"):
        findings = []
        for index, item in enumerate(structured["findings"], 1):
            refs = [registry.resolve(reference).evidence_id for reference in item.get("evidence_refs", []) if registry.resolve(reference)]
            findings.append(Finding(finding_id=f"F-{index:03d}", statement=item["statement"], status=item["status"], claim_refs=[claim.claim_id for claim in claims], evidence_refs=refs))
        return findings
    documents = state.get("documents", [])
    operational = state.get("operational_evidence", [])
    all_records = list(registry.records.values())
    operational_refs = _record_ids(operational)
    document_refs = _record_ids([record for record in all_records if record.source_type == "document"])
    claim_refs = [claim.claim_id for claim in claims]
    findings = []
    if all_records:
        findings.append(Finding(
            finding_id="F-001",
            statement=f"Observed fact: {len(documents)} narrative passages and {len(operational)} structured operational records were available to the investigation.",
            status="observation",
            claim_refs=claim_refs,
            evidence_refs=[*document_refs[:3], *operational_refs[:3]],
        ))
    if operational:
        source_types = sorted({record.source_type for record in operational})
        findings.append(Finding(
            finding_id="F-002",
            statement=f"Observed fact: operational evidence spans {', '.join(source_types)} sources; timestamps and identifiers should be correlated before assigning a root cause.",
            status="observation",
            claim_refs=claim_refs,
            evidence_refs=operational_refs,
        ))
    if status == "insufficient_evidence":
        findings.append(Finding(
            finding_id="F-003",
            statement="Evidence gap: the available records do not establish the missing correlation needed to reach a supported conclusion.",
            status="hypothesis",
            claim_refs=claim_refs,
            evidence_refs=operational_refs,
        ))
    elif status == "escalated":
        findings.append(Finding(
            finding_id="F-003",
            statement="Uncertainty: conflicting source records prevent a reliable conclusion without reconciliation.",
            status="hypothesis",
            claim_refs=claim_refs,
            evidence_refs=operational_refs,
        ))
    elif all_records:
        webhook_refs = _record_ids(operational, source_types={"webhook"})
        if webhook_refs:
            hypothesis = "Hypothesis: webhook delivery or duplicate-processing behavior is plausible from the available event records; confirm idempotency and acknowledgement state before concluding."
            refs = webhook_refs
        else:
            hypothesis = "Hypothesis: a change, access, or service behavior may explain the observed records; the current evidence does not establish which cause is definitive."
            refs = operational_refs or document_refs
        findings.append(Finding(finding_id="F-003", statement=hypothesis, status="hypothesis", claim_refs=claim_refs, evidence_refs=refs))
    return findings


def _recommended_checks(state: InvestigationState, status: str) -> list[str]:
    records = state.get("operational_evidence", [])
    checks = []
    if any(record.source_type == "webhook" for record in records):
        checks.append("Compare webhook event IDs, delivery status, attempt counts, and acknowledgement timestamps for duplicate or delayed delivery.")
    if any(record.source_type in {"deployment", "configuration"} for record in records):
        checks.append("Correlate deployment and configuration timestamps with the first affected request IDs before and after the change.")
    status_codes = {record.metadata.get("status_code") for record in records}
    if "401" in status_codes or "403" in status_codes:
        checks.append("Verify the partner credential, token age, and required authorization scopes against the affected request IDs.")
    if "429" in status_codes:
        checks.append("Compare rate-limit responses with retry-after behavior, partner volume, and the deployment window.")
    if status == "insufficient_evidence":
        checks.append("Collect the missing correlation logs or request IDs before treating any hypothesis as a conclusion.")
    if status == "escalated":
        checks.append("Reconcile the conflicting source timestamps and preserve both source records for human review.")
    if not checks:
        checks.append("Confirm the affected service, timestamps, deployment, configuration, and request correlation IDs.")
    return checks


def validate_evidence(state: InvestigationState):
    registry = EvidenceRegistry.from_records(state.get("evidence", []))
    citations, unsupported = registry.validate_text(state.get("answer", ""))
    structured = state.get("structured_output", {})
    structured_refs = [reference for item in structured.get("findings", []) for reference in item.get("evidence_refs", [])]
    unsupported = sorted(set(unsupported) | {reference for reference in structured_refs if registry.resolve(reference) is None})
    if state.get("provider_error"):
        answer = "Investigation synthesis failed: " + state["provider_error"]
        citations = []
        status = "failed"
        evidence_gaps = ["The selected provider did not return a usable investigation report."]
        contradictions = []
    elif unsupported:
        answer = "Evidence validation failed: unsupported citation IDs: " + ", ".join(unsupported)
        citations = []
        status = "failed"
        evidence_gaps = ["The synthesis cited evidence IDs that were not present in the investigation registry."]
        contradictions = []
    else:
        answer = state.get("answer", "")
        status, evidence_gaps, contradictions = classify_status(state.get("documents", []), state.get("operational_evidence", []))
    claims = []
    structured_findings = structured.get("findings", [])
    if structured_findings:
        for index, item in enumerate(structured_findings, 1):
            refs = []
            for reference in item.get("evidence_refs", []):
                record = registry.resolve(reference)
                if record is not None and record.evidence_id not in refs:
                    refs.append(record.evidence_id)
            claim = Claim(claim_id=f"CLM-{index:03d}", statement=item["statement"], evidence_refs=refs, support_status="unverified")
            claims.append(assess_claim_support(claim, list(registry.records.values())))
    else:
        for index, citation in enumerate(citations, 1):
            record = registry.resolve(citation)
            if record is None:
                continue
            claim = Claim(claim_id=f"CLM-{index:03d}", statement=f"Investigation used evidence from {citation}", evidence_refs=[record.evidence_id], support_status="unverified")
            claims.append(assess_claim_support(claim, list(registry.records.values())))
    weak_claims = [claim for claim in claims if claim.support_status in {"unsupported", "partially_supported"}]
    if weak_claims and not state.get("provider_error") and not unsupported:
        evidence_gaps = [*evidence_gaps, "One or more generated claims have weak lexical support; citation identity is valid but semantic entailment was not established."]
    if structured and not state.get("provider_error") and not unsupported:
        evidence_gaps = [*evidence_gaps, *_documented_cause_coverage_gaps(state, structured, registry)]
    trace = _trace(state, "evidence_verification", "completed", f"Validated {len(citations)} citations")
    findings = _report_findings(status, state, registry, claims, structured)
    report = InvestigationReport(
        investigation_id=state["investigation_id"], question=state["question"], status=status,
        summary=_report_summary(status, state, state.get("documents", []), state.get("operational_evidence", [])), findings=findings,
        claims=claims, evidence=state.get("evidence", []), hypotheses=[finding.statement for finding in findings if finding.status == "hypothesis"],
        recommended_checks=_recommended_checks(state, status),
        contradictions=contradictions, evidence_gaps=evidence_gaps,
        agent_trace=[*state.get("trace", []), AgentTrace(step="evidence_verification", status="completed", detail=f"Validated {len(citations)} citations")], provider=state.get("mode", "local"), retrieval_mode="lexical" if get_settings().deployment_profile == "lite" else "chroma", model=state.get("provider_model"), token_usage=state.get("token_usage", {}), provider_error=state.get("provider_error"), attempts=state.get("attempts", 0),
        provider_diagnostics=state.get("provider_diagnostics", {}),
    )
    return {"answer": answer, "citations": citations, "report": report, "route": "final", "trace": trace}


def route_after_verification(state: InvestigationState):
    # A second pass previously repeated the same retrieval and SQL queries without
    # changing strategy. Stop after one bounded pass and expose the evidence gap.
    return "final"


builder = StateGraph(InvestigationState)
builder.add_node("supervisor", supervisor)
builder.add_node("document_research", document_research)
builder.add_node("operations_analysis", operations_analysis)
builder.add_node("investigation_synthesis", investigation_synthesis)
builder.add_node("evidence_verification", validate_evidence)
builder.add_edge(START, "supervisor")
builder.add_edge("supervisor", "document_research")
builder.add_edge("document_research", "operations_analysis")
builder.add_edge("operations_analysis", "investigation_synthesis")
builder.add_edge("investigation_synthesis", "evidence_verification")
builder.add_conditional_edges("evidence_verification", route_after_verification, {"research": "supervisor", "final": END})
graph = builder.compile()


def run_investigation(question: str, scenario_id: str | None = None):
    return graph.invoke({
        "investigation_id": f"INV-{uuid4().hex[:10]}", "question": question, "scenario_id": scenario_id,
        "documents": [], "operational_evidence": [], "evidence": [], "answer": "", "citations": [],
        "mode": "", "attempts": 0, "max_attempts": get_settings().max_agent_attempts, "trace": [],
        "token_usage": {}, "structured_output": {},
    })


if __name__ == "__main__":
    result = run_investigation("Why would a partner receive HTTP 403 after deployment?")
    print(result["mode"], result["citations"])
    print(result["answer"])
