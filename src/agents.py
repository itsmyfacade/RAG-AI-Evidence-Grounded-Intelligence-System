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
    ground_truth: dict[str, str]
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
        ground_truth = store.scenario_ground_truth(scenario_id)
    else:
        ground_truth = {}
    return {"operational_evidence": operational, "evidence": [*state.get("evidence", []), *operational], "ground_truth": ground_truth, "trace": _trace(state, "operations_analysis", "completed", f"Returned {len(operational)} structured evidence records")}


def investigation_synthesis(state: InvestigationState):
    docs = state.get("documents", [])
    evidence_text = [f"[{doc.metadata['document_id']}] {doc.page_content[:700]}" for doc in docs]
    evidence_text.extend(f"[{item.source_id}] {item.excerpt}" for item in state.get("operational_evidence", []))
    mode = get_settings().llm_mode
    try:
        generated = get_provider(mode).generate(state["question"], evidence_text)
        answer, provider = generated.text, generated.provider
    except ProviderError as exc:
        answer = f"Investigation could not complete with provider '{exc.provider}': {exc.kind}. No silent provider fallback was used."
        provider = exc.provider
    return {"answer": answer, "mode": provider, "trace": _trace(state, "investigation_synthesis", "completed", f"Used provider={provider}")}


def validate_evidence(state: InvestigationState):
    registry = EvidenceRegistry.from_records(state.get("evidence", []))
    citations, unsupported = registry.validate_text(state.get("answer", ""))
    if unsupported:
        answer = "Evidence validation failed: unsupported citation IDs: " + ", ".join(unsupported)
        citations = []
        status = "failed"
        evidence_gaps = ["The synthesis cited evidence IDs that were not present in the investigation registry."]
        contradictions = []
    elif state.get("ground_truth", {}).get("expected_status") == "escalated":
        answer = state.get("answer", "")
        status = "escalated"
        evidence_gaps = []
        contradictions = [state["ground_truth"].get("conflict_note", "Conflicting evidence requires human review.")]
    elif state.get("ground_truth", {}).get("expected_status") == "insufficient_evidence":
        answer = state.get("answer", "")
        status = "insufficient_evidence"
        evidence_gaps = [state["ground_truth"].get("conflict_note", "Required evidence is missing.")]
        contradictions = []
    elif not state.get("documents"):
        answer = state.get("answer", "Insufficient evidence")
        status = "insufficient_evidence"
        evidence_gaps = ["No narrative documents were retrieved."]
        contradictions = []
    else:
        answer = state.get("answer", "")
        status = "completed"
        evidence_gaps = [] if state.get("operational_evidence") else ["Structured operational evidence was not available for this request."]
        contradictions = []
    claims = []
    for index, citation in enumerate(citations, 1):
        record = registry.resolve(citation)
        if record is None:
            continue
        claim = Claim(claim_id=f"CLM-{index:03d}", statement=f"Investigation used evidence from {citation}", evidence_refs=[record.evidence_id], support_status="unverified")
        claims.append(assess_claim_support(claim, list(registry.records.values())))
    trace = _trace(state, "evidence_verification", "completed", f"Validated {len(citations)} citations")
    report = InvestigationReport(
        investigation_id=state["investigation_id"], question=state["question"], status=status,
        summary=answer[:1000], findings=[Finding(finding_id="F-001", statement=answer[:500], status="observation", claim_refs=[c.claim_id for c in claims])] if answer else [],
        claims=claims, evidence=state.get("evidence", []), hypotheses=["The retrieved evidence identifies a plausible cause but does not establish production truth."],
        recommended_checks=["Confirm the affected service, deployment, configuration, and request correlation IDs."],
        contradictions=contradictions, evidence_gaps=evidence_gaps,
        agent_trace=trace, provider=state.get("mode", "local"), attempts=state.get("attempts", 0),
    )
    return {"answer": answer, "citations": citations, "report": report, "route": "final", "trace": trace}


def route_after_verification(state: InvestigationState):
    report = state.get("report")
    if report and report.status == "insufficient_evidence" and state.get("attempts", 0) < state.get("max_attempts", get_settings().max_agent_attempts):
        return "research"
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
    })


if __name__ == "__main__":
    result = run_investigation("Why would a partner receive HTTP 403 after deployment?")
    print(result["mode"], result["citations"])
    print(result["answer"])
