# Public Workload Evidence

Date: 2026-09-13

## Datasets

| Workload | Public source | Task shape | Local sample |
|---|---|---|---|
| SQuAD | `rajpurkar/squad` validation | single-passage extractive QA | `backend/fixtures/public_squad_mini.json` |
| HotpotQA | `hotpotqa/hotpot_qa` distractor validation | multi-hop comparison QA | `backend/fixtures/public_hotpotqa_mini.json` |

Both sources are public and recorded in the fixture metadata. The local samples
contain 16 rows each and are used as controlled replay workloads.

## Controlled experiment

For each workload:

- baseline answers contain the gold answer;
- five candidate answers lose the required answer;
- eleven rows remain identical controls.

This is an external-data replay, not a claim about an open-source model's
benchmark score. It verifies that EvalPilot's comparison engine works on public
question-answering data outside the bundled enterprise-support fixture.

## Command

```powershell
$env:PYTHONPATH = (Resolve-Path backend)
.venv\Scripts\python.exe backend\scripts\public_workload_check.py
```

## Results

### SQuAD

```text
rows: 16
baseline pass rate: 1.0000
candidate pass rate: 0.6875
mean difference: -0.3125
95% CI: -0.5625 to -0.1250
confidence: 0.9859
confirmed regression: true
```

### HotpotQA

```text
rows: 16
baseline pass rate: 1.0000
candidate pass rate: 0.6875
mean difference: -0.3125
95% CI: -0.5625 to -0.1250
confidence: 0.9859
confirmed regression: true
```

Two different public task shapes produce the same matched-control conclusion,
while the naive score delta cannot report controls or uncertainty.
