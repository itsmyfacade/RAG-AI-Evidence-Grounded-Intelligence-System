# Phase 3 model-output evaluation

The existing `phase3-ground-truth-review-packet.json` remains a label-review artifact. It is not a model-performance evaluation and is not modified by this workflow. The original 40-case capture, blinded packet, and report are historical baseline artifacts and must not be overwritten.

## Fingerprint and provenance contract

Future review packets use `aegis-phase3-fingerprint-v3`. This is an explicit restricted canonical JSON contract, not a claim of full RFC 8785 compliance. Python and JavaScript use the same UTF-8 bytes and SHA-256 digest. The payload shape is:

```json
{"cases": [...], "source_run_id": "..."}
```

The supported values are null, booleans, strings containing Unicode scalar values, arrays, objects with string keys, and finite numbers with absolute value no greater than 1,000,000. Numbers are rounded half-up to nine fractional digits, and negative zero is serialized as `0`. Object keys are ordered by UTF-16 code units so non-BMP keys have the same order in both runtimes. Non-finite numbers, unpaired surrogates, unsupported values, and non-string object keys are rejected. This restricted numeric precision is intentional and must be treated as part of the contract.

The reporting utility validates the capture run ID, review run ID, decision run ID, source packet fingerprint, review packet content fingerprint, exact case-ID set, decision schema, and allowed decision values before generating a report. Cross-runtime regression tests execute `frontend/fingerprint.js` itself and compare canonical bytes and SHA-256 hashes with Python.

The existing Phase 3 decision export uses the original browser `JSON.stringify` fingerprint and schema `aegis-phase3-model-output-decisions-v1`. It remains accepted only when its run ID, exact case set, notes, and legacy fingerprint independently validate. New exports use schema `aegis-phase3-model-output-decisions-v3` and include the v3 contract. A mismatch is rejected. It is never silently repaired.

## Capture actual outputs

From the repository root, use the project virtual environment and the deterministic local provider:

```powershell
$env:AEGIS_DEPLOYMENT_PROFILE = "lite"
$env:AEGIS_LLM = "local"
.\.venv\Scripts\python.exe tools\phase3_model_output.py capture --profile lite --llm local
```

The command executes each of the 40 packet questions through the existing `src.agents.run_investigation` graph. It writes two local artifacts under `data/evaluation/results/`:

1. A capture artifact containing actual answers, findings, retrieved evidence, citations, trace, provider, model, status, errors, and monotonic latency.
2. A blinded review packet containing only the captured output. It excludes expected evidence, expected citation IDs, answerability labels, and review rationales.

The results directory is ignored because captures can contain private evaluator material. Do not publish captures, review decisions, or the original private packet.

## Perform the blinded review

Open `frontend/model-review.html` locally, or use the application static mount at `/demo/model-review.html`. Select the generated blinded packet. Review each output and record:

- Overall outcome: supported or correct, partially supported, unsupported or incorrect, or not assessable.
- Evidence relevance.
- Citation support.
- Answer correctness.
- Abstention behavior.
- Uncertainty handling.
- Your answerability judgment.
- A reason and reviewer notes.

Decisions remain browser-local and isolated by run fingerprint. Export the decision JSON regularly. No decisions are sent to the public backend, and no expected labels are shown during the initial judgment.

## Controlled comparison and report

After the initial review is complete, compare the decisions with the original packet using the reporting utility. This is a post-judgment comparison. Reviewer agreement with the packet labels is not model accuracy.

```powershell
.\.venv\Scripts\python.exe tools\phase3_model_output.py report `
  --capture data\evaluation\results\<capture>.json `
  --review-packet data\evaluation\results\<review-packet>.json `
  --decisions data\evaluation\results\<decisions>.json `
  --ground-truth data\evaluation\results\phase3-ground-truth-review-packet.json `
  --output data\evaluation\results\<report>.json
```

The report includes denominators, substantive denominators, explicit not-assessable and not-applicable counts, missing-value exclusions, decision counts, criterion counts, and limitations. It does not synthesize missing judgments or combine human review with automated retrieval metrics. Ground-truth comparison categories are `agreement`, `label_disagreement`, `missing_expected_label`, `missing_reviewer_judgment`, and `not_assessable`. The historical `missing` count is retained only as a legacy comparison field and means label disagreement, not missing data.

Retrieval evidence availability and investigation conclusion sufficiency are separate evaluation constructs. The original benchmark labels expected relevant evidence for retrieval evaluation. A reviewer can reasonably judge a full investigation as insufficient when scenario-specific operational evidence is absent. Disagreement is reported neutrally and is not automatically treated as reviewer error or model error.

The report command accepts repository-relative paths, absolute paths inside the repository, and absolute paths outside the repository. Output-path formatting cannot turn a successful report write into a failed command.

Writes are safe by default. Existing output files are rejected unless `--overwrite` is supplied, and the five protected historical artifacts are rejected even with `--overwrite`. New files are written through a temporary sibling and atomically replaced, so an interrupted write does not leave a partial JSON artifact.

## Review status and limitations

The completed historical review used one reviewer and an AI-assisted local workflow. It does not support inter-rater reliability claims. The local deterministic provider is useful for reproducibility, but it is not evidence of production accuracy or generalization beyond the synthetic corpus. Reviewer agreement with the original retrieval labels is not model accuracy.

To reproduce a report safely after a future review, write to a new output path and leave the historical report untouched:

```powershell
.\.venv\Scripts\python.exe tools\phase3_model_output.py report `
  --capture data\evaluation\results\<capture>.json `
  --review-packet data\evaluation\results\<review-packet>.json `
  --decisions <exported-decisions>.json `
  --ground-truth data\evaluation\results\phase3-ground-truth-review-packet.json `
  --output data\evaluation\results\phase3-model-output-report-new.json
```
