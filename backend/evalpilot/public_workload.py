"""Run EvalPilot's comparison engine over public question-answering samples.

Two public datasets are used:

- SQuAD: single-passage extractive question answering.
- HotpotQA distractor: multi-hop comparison question answering.

Each workload contains a controlled candidate regression while the remaining
rows are exact controls. The goal is to demonstrate that the comparison engine
generalises beyond EvalPilot's bundled enterprise-support fixture and that the
naive pass-rate delta can be shown side by side with the matched-control result.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evalpilot.evaluation import EvaluationService
from evalpilot.evaluation.models import (
    AnswerInput,
    Citation,
    ExpectedBehavior,
    SampleObservation,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@dataclass(frozen=True)
class PublicWorkloadSpec:
    key: str
    label: str
    fixture: Path
    regressed_indexes: frozenset[int]


PUBLIC_WORKLOADS: dict[str, PublicWorkloadSpec] = {
    "squad": PublicWorkloadSpec(
        key="squad",
        label="rajpurkar/squad validation",
        fixture=FIXTURES / "public_squad_mini.json",
        regressed_indexes=frozenset({1, 4, 7, 10, 13}),
    ),
    "hotpotqa": PublicWorkloadSpec(
        key="hotpotqa",
        label="hotpotqa/hotpot_qa distractor validation",
        fixture=FIXTURES / "public_hotpotqa_mini.json",
        regressed_indexes=frozenset({1, 4, 7, 10, 13}),
    ),
}


@dataclass(frozen=True)
class PublicWorkloadResult:
    workload: str
    label: str
    rows: int
    authored_regressions: int
    controls: int
    baseline_pass_rate: float
    candidate_pass_rate: float
    naive_detects_regression: bool
    engine_direction: str
    engine_mean_difference: float
    engine_ci_lower: float
    engine_ci_upper: float
    engine_confidence: float
    engine_confirms_regression: bool
    report: Any


def load_public_rows(spec: PublicWorkloadSpec) -> list[dict[str, Any]]:
    payload = json.loads(spec.fixture.read_text(encoding="utf-8"))
    rows = payload.get("rows")
    if not isinstance(rows, list) or len(rows) < 10:
        raise ValueError(f"expected at least 10 public workload rows in {spec.fixture}")
    return rows


def _pass_rate(
    rows: list[dict[str, Any]],
    regressed_indexes: frozenset[int],
    *,
    candidate: bool,
) -> float:
    passed = sum(
        1
        for index in range(len(rows))
        if not candidate or index not in regressed_indexes
    )
    return passed / len(rows)


async def evaluate_public_workload(
    spec: PublicWorkloadSpec,
    *,
    bootstrap_resamples: int = 2000,
) -> PublicWorkloadResult:
    dataset = load_public_rows(spec)
    observations: list[SampleObservation] = []
    expectations: dict[str, ExpectedBehavior] = {}
    evidence_ids_by_case: dict[str, list[str]] = {}
    run_id = f"public-{spec.key}-mini"

    for index, row in enumerate(dataset):
        case_id = str(row["id"])
        gold = str(row["answers"][0])
        baseline_text = f"The answer is {gold}."
        candidate_text = (
            "Evidence is insufficient for a response."
            if index in spec.regressed_indexes
            else baseline_text
        )
        evidence_ids_by_case[case_id] = [
            f"public-{spec.key}-{index}-baseline",
            f"public-{spec.key}-{index}-candidate",
        ]
        expectations[case_id] = ExpectedBehavior(required_keywords=[gold])
        for version, text, evidence_id in (
            ("baseline", baseline_text, evidence_ids_by_case[case_id][0]),
            ("candidate", candidate_text, evidence_ids_by_case[case_id][1]),
        ):
            observations.append(
                SampleObservation(
                    id=evidence_id,
                    case_id=case_id,
                    run_id=run_id,
                    version=version,
                    trial_index=0,
                    answer=AnswerInput(
                        text=text,
                        citations=[Citation(uri=f"{spec.key}://{case_id}")],
                    ),
                )
            )

    report = await EvaluationService(
        seed=0,
        bootstrap_resamples=bootstrap_resamples,
    ).compare_async(
        observations=observations,
        expectations=expectations,
        evidence_ids_by_case=evidence_ids_by_case,
        run_id=run_id,
    )
    comparison = report.comparison
    baseline_pass_rate = _pass_rate(
        dataset, spec.regressed_indexes, candidate=False
    )
    candidate_pass_rate = _pass_rate(
        dataset, spec.regressed_indexes, candidate=True
    )
    regression_count = len(spec.regressed_indexes)
    return PublicWorkloadResult(
        workload=spec.key,
        label=spec.label,
        rows=len(dataset),
        authored_regressions=regression_count,
        controls=len(dataset) - regression_count,
        baseline_pass_rate=baseline_pass_rate,
        candidate_pass_rate=candidate_pass_rate,
        naive_detects_regression=candidate_pass_rate < baseline_pass_rate,
        engine_direction=comparison.direction.value,
        engine_mean_difference=comparison.mean_difference,
        engine_ci_lower=comparison.ci_lower,
        engine_ci_upper=comparison.ci_upper,
        engine_confidence=comparison.confidence,
        engine_confirms_regression=(
            comparison.direction.value == "regression" and comparison.is_significant
        ),
        report=report,
    )


def run_public_workloads(
    keys: list[str] | None = None,
    *,
    bootstrap_resamples: int = 2000,
) -> list[PublicWorkloadResult]:
    selected = keys or list(PUBLIC_WORKLOADS)
    return [
        asyncio.run(
            evaluate_public_workload(
                PUBLIC_WORKLOADS[key],
                bootstrap_resamples=bootstrap_resamples,
            )
        )
        for key in selected
    ]
