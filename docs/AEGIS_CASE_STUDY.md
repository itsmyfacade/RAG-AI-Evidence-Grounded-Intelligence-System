# AEGIS engineering case study

## Project overview

AEGIS is a full-stack evidence-grounded investigation application for synthetic technical incidents. It combines narrative documentation, structured operational evidence, deterministic retrieval, bounded LangGraph orchestration, and explicit citation validation.

## Engineering challenge

The initial hosted profile needed to remain lightweight enough for a constrained free deployment while still making evidence quality visible. The original lexical retriever was fast, but raw token overlap produced weak ranking quality and no useful retrieval-level abstention.

## Technical decisions

- Preserve the existing FastAPI and LangGraph contracts.
- Keep a lite profile that does not require model downloads or the semantic vector index.
- Add cached BM25-style ranking with deterministic title and category weighting.
- Retain the legacy ranker for historical comparisons.
- Add an opt-in evidence score gate for retrieval-level abstention.
- Validate citation identity independently from conservative lexical claim support.
- Keep benchmark labels outside the serving path.
- Record local benchmark artifacts with checksums, configuration, timing, memory, and limitations.

## Measured improvement

On the same 1,200-case synthetic workload, Recall@5 increased from 0.6315 to 0.8375 and MRR increased from 0.5104 to 0.8559. Correct retrieval-level abstention increased from 0.0000 to 0.2333. The optimized p95 retrieval latency was 2.585 ms locally, compared with 1.422 ms for the legacy profile.

These are synthetic retrieval measurements. They do not represent production incident accuracy, semantic entailment, or hallucination prevention.

## Reliability and security

The API applies request validation, bounded concurrency, in-process quotas, safe public errors, and parameterized SQLite access. Retrieved documents are treated as untrusted evidence and are not treated as executable instructions. The system exposes uncertainty, evidence gaps, contradictions, and provider identity instead of silently certifying a root cause.

## Demonstration modes

- Live API mode: the browser calls the configured FastAPI service.
- Benchmark artifact mode: the validation dashboard reads a versioned static summary.
- Recorded local mode: the fallback displays a real deterministic local output and labels it as recorded.
- Human review mode: `frontend/review.html` loads the generated review packet from a local file and exports decisions separately from serving data.

## Remaining limitations

The evaluation corpus is synthetic, evidence families are reused across splits, and the 40-case ground-truth packet has not received independent human decisions. The claim-support check is lexical and explicitly not semantic entailment. Mixed-source retrieval and ambiguous-case abstention require further work.
