"""Public, symptom-oriented presentation for the synthetic scenarios.

This catalog is deliberately separate from evaluator labels.  Titles and questions
describe observed symptoms only; expected outcomes remain in the offline evaluator.
"""

from __future__ import annotations


SCENARIO_PRESENTATION: dict[str, tuple[str, str]] = {
    "SCN-001": ("Reporting requests returned HTTP 403 after a deployment", "Investigate reporting requests returning HTTP 403 after a deployment and authorization evidence."),
    "SCN-002": ("Partner reporting requests returned HTTP 401", "Investigate partner reporting requests returning HTTP 401 and the related authentication records."),
    "SCN-003": ("Partner reporting requests returned HTTP 429", "Investigate partner reporting requests returning HTTP 429, rate limits, and retry timing."),
    "SCN-004": ("Webhook deliveries arrived after acknowledgement delays", "Investigate delayed webhook deliveries, acknowledgement timing, and retry activity."),
    "SCN-005": ("Webhook processing errors with delayed, retried deliveries", "Investigate webhook processing errors, delayed deliveries, and delivery attempts for a partner integration."),
    "SCN-006": ("Partner payloads were rejected by an API integration", "Investigate rejected partner payloads, schema versions, and API compatibility evidence."),
    "SCN-007": ("Partner integration requests began failing after a configuration change", "Investigate failing partner integration requests and the related configuration and delivery records."),
    "SCN-008": ("Reporting totals did not match expected values", "Investigate reporting totals that do not match expected values and the related reporting records."),
    "SCN-009": ("Partner behavior differed between sandbox and production", "Investigate inconsistent partner integration behavior across sandbox and production configurations."),
    "SCN-010": ("Reporting requests slowed after a deployment", "Investigate reporting latency and request timeouts after a deployment."),
    "SCN-011": ("Partner webhook events were delayed", "Investigate delayed partner webhook events and their delivery attempts."),
    "SCN-012": ("Source and destination record counts diverged", "Investigate a mismatch between source and destination record counts and reconciliation evidence."),
    "SCN-013": ("Partner onboarding requests were rejected", "Investigate partner onboarding failures and rejected endpoint-access requests."),
    "SCN-014": ("Partner authorization failures followed a configuration change", "Investigate partner authorization failures and the related configuration and deployment records."),
    "SCN-015": ("Partner records were rejected by the destination system", "Investigate partner records rejected by the destination system and the related error records."),
    "SCN-016": ("A service access review raised findings for the reporting integration", "Investigate the findings of a service access review for the reporting integration."),
    "SCN-017": ("A reporting query exceeded its latency budget", "Investigate a reporting query exceeding its latency budget, timeouts, and deployment evidence."),
    "SCN-018": ("Partner reports HTTP 500 errors from the reporting API", "Investigate HTTP 500 errors returned by the reporting API."),
    "SCN-019": ("Partner reports HTTP 500 errors around a recent deployment", "Investigate HTTP 500 errors reported around a recent deployment."),
    "SCN-020": ("Partner events remained delayed after replay activity", "Investigate delayed partner events, replay activity, and delivery status records."),
}


def public_title(scenario_id: str) -> str:
    return SCENARIO_PRESENTATION.get(scenario_id, (scenario_id, "Investigate the available evidence for this scenario."))[0]


def public_question(scenario_id: str) -> str:
    title, question = SCENARIO_PRESENTATION.get(scenario_id, (scenario_id, "Investigate the available evidence for this scenario."))
    del title
    return f"{question} Do not assume a root cause; distinguish observations, documented causes, hypotheses, and conclusions."
