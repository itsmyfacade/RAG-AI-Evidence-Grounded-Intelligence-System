# Phase 3 release evidence

This is a small, sanitized summary of the reproducible Phase 3 comparison. Large case-level and runtime artifacts remain ignored under `data/evaluation/results/`.

## Dataset and provenance

- Dataset version: `aegis-phase2-v1`
- Generator version: `template-ontology-v1`
- Cases: 1,200
- Evidence documents: 90
- Splits: development 700, validation 200, held-out 300
- Dataset checksum: `51b7c2971014d941c06467ad8fa30229eb547384a162eedba1194206fc553d8d`
- Corpus checksum: `6ee1691ca01258a9db0a2f8ae922f16f7a551165cdee507b5f40a71fa6833ccf`
- Generation seed: `20261114`
- The generator seed and full checksums are recorded in the ignored JSON result artifacts.

## Equivalent comparison

Both profiles used the same 1,200-case workload and 90-document corpus.

| Metric | Legacy lexical | BM25 plus abstention |
| --- | ---: | ---: |
| Recall@5 | 0.6315 | 0.8375 |
| MRR | 0.5104 | 0.8559 |
| nDCG@5 | 0.5285 | 0.8462 |
| Evidence coverage | 0.7144 | 0.8426 |
| Correct abstention | 0.0000 | 0.2333 |
| False-answer proxy | 1.0000 | 0.7667 |

The optimized profile uses `AEGIS_RETRIEVAL_PROFILE=bm25`, `AEGIS_RETRIEVAL_ABSTENTION=true`, and a score threshold of `12.0`. The threshold was selected from development and validation trade-offs. Held-out cases were not used for selection.

## Performance

- Legacy lexical p95: 1.422 ms.
- Optimized BM25 with abstention p95: 2.585 ms.
- Optimized evaluation runtime: 18.96 seconds.
- Optimized post-evaluation working set: approximately 55.1 MiB.
- Errors: 0.
- Timeouts: 0.

The optimized profile trades a small local latency increase for materially stronger retrieval ranking. Mixed-source retrieval and ambiguous-case abstention remain weaknesses.

## Methodology and limitations

- Metrics are case-level macro averages.
- Undefined negative-case retrieval metrics are excluded from their denominators.
- Confidence intervals use 1,000 deterministic bootstrap resamples.
- Abstention is a retrieval-level proxy, not final answer correctness.
- Citation identity is not semantic entailment.
- The corpus and labels are synthetic.
- Evidence families are reused across splits, so full family independence is not claimed.
- The 40-case review packet is pending independent human decisions.

## Reproduction

```powershell
$env:AEGIS_DEPLOYMENT_PROFILE = "lite"
$env:AEGIS_LLM = "local"
$env:AEGIS_EMBEDDINGS = "local"
$env:AEGIS_EMBEDDING_LOCAL_FILES_ONLY = "true"
$env:AEGIS_RETRIEVAL_PROFILE = "bm25"
$env:AEGIS_RETRIEVAL_ABSTENTION = "true"
$env:AEGIS_RETRIEVAL_ABSTENTION_THRESHOLD = "12"
.venv\Scripts\python.exe tools\run_phase2_benchmark.py
```

Historical reproduction uses `AEGIS_RETRIEVAL_PROFILE=legacy` and `AEGIS_RETRIEVAL_ABSTENTION=false`.
