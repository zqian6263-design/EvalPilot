# Real Upstream Version Comparison

Date: 2026-09-13

## Question

Does a real upstream Haystack upgrade change the evaluated behavior of the same
RAG pipeline?

## Setup

- Baseline environment: `haystack-ai 3.0.0`
- Candidate environment: `haystack-ai 3.1.1`
- Same adapter source revision
- Same public pipeline: splitter -> BM25 retriever -> joiner -> grounded reranker
- Same 26 enterprise-support scenarios and both revision arms
- 52 HTTP comparisons

## Result

```text
baseline engine: 3.0.0
candidate engine: 3.1.1
comparisons: 52
semantic mismatches: 0
status: pass
```

The comparison includes answer text, citations, and refusal behavior. Latency is
recorded separately and is not treated as a correctness signal.

Full result: `docs/UPSTREAM_VERSION_RESULT.json`.

## Interpretation

This is a negative control for a real dependency upgrade. EvalPilot did not
invent a regression, which is the correct result when the upstream behavior is
unchanged. It also demonstrates that the SUT contract can evaluate two
independently installed upstream environments.

## Reproduce

```powershell
$env:PYTHONPATH = (Resolve-Path backend)
.venv\Scripts\python.exe backend\scripts\upstream_version_check.py `
  --baseline-python .runtime\haystack-3.0-venv\Scripts\python.exe `
  --candidate-python .venv\Scripts\python.exe `
  --output docs\UPSTREAM_VERSION_RESULT.json
```
