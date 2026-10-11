# AEGIS domain ontology

AEGIS uses a small relational ontology rather than a graph database.

```text
partner --has--> incident --affects--> service
incident --caused_by/preceded_by--> deployment
partner --has--> configuration_change
incident --observed_in--> api_log
incident --discussed_in--> support_ticket
document/chunk --describes--> scenario or incident
evidence_record --references--> document, log, deployment, configuration, or ticket
```

Every generated scenario has a stable `scenario_id`. Incidents, deployments,
configuration changes, API logs, and support tickets reference that ID. Vector
documents remain optimized for semantic research; high-cardinality logs remain
in SQLite and are queried with approved read-only tools.
