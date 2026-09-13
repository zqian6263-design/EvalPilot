# P1 Verification Record

Date: 2026-09-13

## Implemented

- SUT capability discovery: `GET /capabilities`, version/intervention validation, legacy 404 fallback.
- Model planning robustness: one retry for malformed/schema-invalid responses, valid-plan preservation, deterministic fill-in for missing scenarios.
- Judge budget guard: `EVALPILOT_JUDGE_MAX_CALLS`, `EVALPILOT_JUDGE_MAX_TOKENS`, skipped-call metrics.
- CI integration: JUnit XML, SARIF 2.1.0, artifact export script, GitHub Actions template, PR summary.
- Statistical diagnostics: minimum detectable effect, required matched cases, observed power, sample-size adequacy.

## Verification

- Full backend suite: pass.
- Public Haystack SUT E2E: pass, including capability discovery and failure when the SUT is unavailable.
- Haystack pipeline: `splitter -> retriever -> joiner -> grounded reranker`; baseline 26/26 and candidate 8/26 regressions unchanged.
- Pipeline acceptance evidence: `.runtime/sut-e2e-94284678fa274bacaa1ccd96f0832c3c/summary.json`.
- CI export against a live run:
  - `gate.json` decision `BLOCK`, exit code `2`.
  - `junit.xml`: 8 failures / 8 test cases.
  - `results.sarif`: SARIF `2.1.0`, 8 results.
  - `summary.md`: generated for PR comments.
- Existing planner comparison remains unchanged.

## RAG pipeline

The public Haystack adapter now runs a real pipeline with document splitting,
BM25 retrieval, document joining, grounded reranking, and answer composition.
The pipeline preserves the baseline 26/26 pass rate and the eight controlled
candidate regressions.
