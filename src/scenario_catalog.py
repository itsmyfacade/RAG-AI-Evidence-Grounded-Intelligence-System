"""Public, symptom-oriented presentation for the synthetic scenarios.

This catalog is deliberately separate from evaluator labels.  Titles and questions
describe observed symptoms only; expected outcomes remain in the offline evaluator.
"""

from __future__ import annotations


SCENARIO_PRESENTATION: dict[str, tuple[str, str]] = {
    "SCN-001": ("Reporting requests returned HTTP 403 after a deployment", "Investigate reporting requests returning HTTP 403 after a deployment and authorization evidence."),
    "SCN-002": ("Partner reporting requests returned HTTP 401", "Investigate partner reporting requests returning HTTP 401 and invalid bearer-token evidence."),
    "SCN-003": ("Partner reporting requests returned HTTP 429", "Investigate partner reporting requests returning HTTP 429, rate limits, and retry timing."),
    "SCN-004": ("Webhook deliveries arrived after acknowledgement delays", "Investigate delayed webhook deliveries, acknowledgement timing, and retry activity."),
    "SCN-005": ("Duplicate downstream records followed repeated webhook deliveries", "Investigate repeated webhook deliveries, duplicate downstream records, and event processing evidence."),
    "SCN-006": ("Partner payloads were rejected by an API integration", "Investigate rejected partner payloads, schema versions, and API compatibility evidence."),
    "SCN-007": ("Webhook signature checks failed after a credential change", "Investigate webhook signature verification failures, secret rotation, and rejected deliveries."),
    "SCN-008": ("Reporting totals differed across a UTC date boundary", "Investigate reporting totals that differ across a UTC date boundary and aggregation evidence."),
    "SCN-009": ("Partner behavior differed between sandbox and production", "Investigate inconsistent partner integration behavior across sandbox and production configurations."),
    "SCN-010": ("Reporting requests slowed after a deployment", "Investigate reporting latency and request timeouts after a deployment."),
    "SCN-011": ("Webhook events accumulated in a retry queue", "Investigate delayed webhook events, retry queue activity, and delivery attempts."),
    "SCN-012": ("Source and destination record counts diverged", "Investigate a mismatch between source and destination record counts and reconciliation evidence."),
    "SCN-013": ("Partner onboarding requests were rejected", "Investigate partner onboarding failures and rejected endpoint-access requests."),
    "SCN-014": ("Authorization behavior changed after role configuration", "Investigate authorization failures following a role configuration change and scope evidence."),
    "SCN-015": ("ETL records accumulated after schema validation errors", "Investigate ETL records accumulating after destination schema validation errors and nullable fields."),
    "SCN-016": ("A service access review reported unexpected permissions", "Investigate unexpected permissions found during a service access review and least-privilege records."),
    "SCN-017": ("A reporting query exceeded its latency budget", "Investigate a reporting query exceeding its latency budget, timeouts, and deployment evidence."),
    "SCN-018": ("Correlation identifiers were absent from some request logs", "Investigate request logs missing correlation identifiers and affected request metadata."),
    "SCN-019": ("Support reports and deployment timestamps differed", "Investigate conflicting support reports, deployment timestamps, and source-clock evidence."),
    "SCN-020": ("Partner events remained delayed after replay activity", "Investigate delayed partner events, replay activity, and delivery status records."),
}


def public_title(scenario_id: str) -> str:
    return SCENARIO_PRESENTATION.get(scenario_id, (scenario_id, "Investigate the available evidence for this scenario."))[0]


def public_question(scenario_id: str) -> str:
    title, question = SCENARIO_PRESENTATION.get(scenario_id, (scenario_id, "Investigate the available evidence for this scenario."))
    del title
    return f"{question} Do not assume a root cause; distinguish observations, documented causes, hypotheses, and conclusions."
