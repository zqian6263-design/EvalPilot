"""Public workload evidence for the market/landing claims."""

from __future__ import annotations

import asyncio

from evalpilot.public_workload import (
    REGRESSED_INDEXES,
    evaluate_public_workload,
    load_public_rows,
)


def test_public_squad_fixture_has_external_data() -> None:
    rows = load_public_rows()
    assert len(rows) == 16
    assert len({row["id"] for row in rows}) == 16
    assert len({row["title"] for row in rows}) > 10
    assert all(row["question"] and row["context"] and row["answers"] for row in rows)


def test_public_workload_confirms_the_controlled_regression() -> None:
    result = asyncio.run(evaluate_public_workload(bootstrap_resamples=500))
    assert result.rows == 16
    assert result.authored_regressions == len(REGRESSED_INDEXES) == 5
    assert result.controls == 11
    assert result.baseline_pass_rate == 1.0
    assert result.candidate_pass_rate == 11 / 16
    assert result.naive_detects_regression is True
    assert result.engine_direction == "regression"
    assert result.engine_ci_upper < -0.05
    assert result.engine_confirms_regression is True
