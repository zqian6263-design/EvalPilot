"""Deterministic mock planner.

Turns a project brief into concrete test cases. Given the same seed and case
count, the planner always produces the same titles, ordering, difficulty and
input payloads — that determinism is what makes the demo reproducible.
"""

from __future__ import annotations

import random

from evalpilot.clock import new_id
from evalpilot.fixtures import SupportScenario, active_scenarios
from evalpilot.models import TestCase

MIN_CASES = 1
MAX_CASES = 26  # Backward-compatible cap for the bundled public demo workload.


class PlannerError(ValueError):
    """Raised when a plan cannot be produced for the requested parameters."""


def plan_case_count(requested: int | None, seed: int) -> int:
    """Resolve the number of cases to plan.

    An explicit ``case_count`` is honoured (clamped to what the fixture set can
    support). Otherwise a seeded draw picks a number in ``[4, MAX_CASES]`` so
    that ad-hoc runs vary without becoming non-reproducible.
    """
    if requested is not None:
        if requested < MIN_CASES:
            raise PlannerError(f"case_count must be >= {MIN_CASES}")
        return min(requested, len(active_scenarios()))
    scenarios = active_scenarios()
    rng = random.Random(seed)
    lower = min(4, len(scenarios))
    return rng.randint(lower, len(scenarios))


def _difficulty(base: float, rng: random.Random) -> float:
    """Jitter difficulty deterministically without changing its tier."""
    jitter = rng.uniform(-0.03, 0.03)
    return round(min(0.99, max(0.01, base + jitter)), 3)


def select_scenarios(case_count: int) -> list[SupportScenario]:
    """Take the first ``case_count`` scenarios from the active workload."""
    scenarios = active_scenarios()
    if case_count < MIN_CASES:
        raise PlannerError(f"case_count must be >= {MIN_CASES}")
    if case_count > len(scenarios):
        raise PlannerError(
            f"case_count must be <= {len(scenarios)}; active workload has {len(scenarios)} scenarios"
        )
    return list(scenarios[:case_count])


def build_cases(
    run_id: str,
    case_count: int,
    seed: int,
    versions: tuple[str, str] = ("baseline", "candidate"),
) -> list[TestCase]:
    """Build matched baseline/candidate test cases for a run.

    Each scenario yields one case per version, so the evaluator can compare
    matched pairs rather than two different test sets.
    """
    rng = random.Random(seed)
    scenarios = select_scenarios(case_count)
    cases: list[TestCase] = []

    for scenario in scenarios:
        difficulty = _difficulty(scenario.difficulty, rng)
        for version in versions:
            cases.append(
                TestCase(
                    id=new_id(),
                    run_id=run_id,
                    title=f"{scenario.scenario_id} [{version}]",
                    category=scenario.category,  # type: ignore[arg-type]
                    input={
                        "scenario_id": scenario.scenario_id,
                        "question": scenario.question,
                        "version": version,
                    },
                    expected={
                        "expected_doc_ids": list(scenario.expected_doc_ids),
                        "must_include": list(scenario.must_include),
                        "must_avoid": list(scenario.must_avoid),
                        "expects_refusal": scenario.expects_refusal,
                    },
                    difficulty=difficulty,
                    status="pending",
                    version=version,  # type: ignore[arg-type]
                    output=None,
                )
            )

    return cases


def risk_map(scenarios: list[SupportScenario]) -> dict[str, int]:
    """Per-category case counts, useful for the demo UI and the report."""
    counts: dict[str, int] = {}
    for scenario in scenarios:
        counts[scenario.category] = counts.get(scenario.category, 0) + 1
    return counts
