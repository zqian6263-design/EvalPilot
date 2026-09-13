# Judge Calibration

Date: 2026-09-13

Judge calibration compares EvalPilot's rubric judge with human-scored answers.

## Input contract

CSV columns:

```text
case_id,question,answer,rubric,human_score
```

`human_score` must be in `[0, 1]`. Multiple evaluators should be collapsed into
a documented mean before running the tool.

## Command

```powershell
$env:PYTHONPATH = (Resolve-Path backend)
.venv\Scripts\python.exe backend\scripts\judge_calibration.py `
  path\to\human_scores.csv --output docs\JUDGE_CALIBRATION_RESULT.json
```

## Output

```text
count
mae
bias
pearson
exact_agreement
```

- `mae`: mean absolute judge-human difference.
- `bias`: signed mean `judge - human`; positive means over-scoring.
- `pearson`: linear agreement when both score vectors vary.
- `exact_agreement`: fraction within numerical tolerance.

## Policy

A calibration report is evidence, not a release gate. The judge score may enter
qualitative scoring only after the deterministic checks and the measured
counterfactual replay. Human labels are required to run this experiment; no
human scores are fabricated in this repository.
