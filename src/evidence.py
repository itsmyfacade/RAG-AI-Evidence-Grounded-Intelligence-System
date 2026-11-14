"""Evidence identity registry and deterministic claim-support checks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.schemas import Claim, EvidenceRecord

_SUPPORT_STOPWORDS = {
    "about", "after", "against", "claim", "evidence", "fact", "from", "investigation",
    "record", "records", "report", "reported", "source", "that", "the", "this", "used",
    "with", "within",
}


def extract_citation_ids(text: str) -> list[str]:
    groups = re.findall(r"\[([A-Z]+-[A-Z0-9-]+(?:\s*,\s*[A-Z]+-[A-Z0-9-]+)*)\]", text)
    return sorted({item.strip() for group in groups for item in group.split(",")})


@dataclass
class EvidenceRegistry:
    """Canonical evidence records plus explicit source-reference aliases."""

    records: dict[str, EvidenceRecord] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_records(cls, records: list[EvidenceRecord]) -> EvidenceRegistry:
        registry = cls()
        for record in records:
            registry.add(record)
        return registry

    def add(self, record: EvidenceRecord) -> None:
        if record.evidence_id in self.records:
            raise ValueError(f"Duplicate evidence ID: {record.evidence_id}")
        self.records[record.evidence_id] = record
        self.aliases[record.evidence_id] = record.evidence_id
        if record.source_id in self.aliases and self.aliases[record.source_id] != record.evidence_id:
            raise ValueError(f"Ambiguous evidence source ID: {record.source_id}")
        self.aliases[record.source_id] = record.evidence_id

    def resolve(self, citation_id: str) -> EvidenceRecord | None:
        canonical_id = self.aliases.get(citation_id)
        return self.records.get(canonical_id) if canonical_id else None

    def validate_text(self, text: str) -> tuple[list[str], list[str]]:
        citations = extract_citation_ids(text)
        unknown = sorted(citation for citation in citations if citation not in self.aliases)
        return citations, unknown

    def canonical_refs(self, citations: list[str]) -> list[str]:
        return [self.aliases[citation] for citation in citations if citation in self.aliases]


def validate_citations(text: str, valid_ids: set[str]) -> tuple[list[str], list[str]]:
    """Backward-compatible validator for callers with a flat allowed-ID set."""
    citations = extract_citation_ids(text)
    return citations, sorted(set(citations) - valid_ids)


def assess_claim_support(claim: Claim, evidence: list[EvidenceRecord]) -> Claim:
    by_id = {item.evidence_id: item for item in evidence}
    if not claim.evidence_refs or any(ref not in by_id for ref in claim.evidence_refs):
        return claim.model_copy(update={"support_status": "unsupported", "rationale": "No resolvable canonical evidence references."})
    terms = {
        term for term in re.findall(r"[a-zA-Z0-9_:-]{4,}", claim.statement.lower())
        if term not in _SUPPORT_STOPWORDS
    }
    overlap_by_ref = {
        ref: len(terms & set(re.findall(r"[a-zA-Z0-9_:-]{4,}", by_id[ref].excerpt.lower())))
        for ref in claim.evidence_refs
    }
    if not terms or not any(overlap_by_ref.values()):
        return claim.model_copy(update={"support_status": "unsupported", "rationale": "Citation IDs are valid, but the cited excerpts contain no lexical support for the claim."})
    if min(overlap_by_ref.values()) >= 2:
        return claim.model_copy(update={"support_status": "supported", "rationale": "Lexical support check passed for every cited excerpt; this is not entailment proof."})
    return claim.model_copy(update={"support_status": "partially_supported", "rationale": "At least one cited excerpt is weak or irrelevant by lexical comparison; semantic entailment was not established."})
