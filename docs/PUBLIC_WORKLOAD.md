# Public Workload Evidence

Date: 2026-09-12

## Dataset

- Source: `rajpurkar/squad`
- Config: `plain_text`
- Split: `validation`
- URL: https://huggingface.co/datasets/rajpurkar/squad
- License: CC BY-SA 4.0
- Local sample: `backend/fixtures/public_squad_mini.json`
- Sample: 16 validation rows across 16 distinct article titles.

## Controlled experiment

The baseline answer contains the gold answer. Five candidate answers lose the
required answer while eleven remain identical controls.

This is an external-data replay, not a claim that EvalPilot contains an
open-source model. Its purpose is to verify that the comparison engine works on
a public question-answering workload outside the bundled enterprise-support
fixture.

## Command

```powershell
$env:PYTHONPATH = (Resolve-Path backend)
.venv\Scripts\python.exe backend\scripts\public_workload_check.py
```

## Result

```text
rows: 16
authored regressions: 5
controls: 11
naive baseline pass rate: 1.0000
naive candidate pass rate: 0.6875
naive detects regression: true

EvalPilot direction: regression
mean difference: -0.3125
95% CI: -0.5625 to -0.1250
confidence: 0.9859
confirmed regression: true
```

## Interpretation

The naive score comparison and EvalPilot agree that the candidate is worse, but
only EvalPilot reports the paired uncertainty, matched count, controls, and
confidence interval. The experiment is reproducible offline after the fixture
is checked out; network access is required only to refresh the public sample.
