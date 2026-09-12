"""Public workload evidence for the market/landing claims."""

from __future__ import annotations

import asyncio

from evalpilot.public_workload import (
    PUBLIC_WORKLOADS,
    evaluate_public_workload,
    load_public_rows,
)


def test_public_fixtures_have_external_data() -> None:
    for spec in PUBLIC_WORKLOADS.values():
        rows = load_public_rows(spec)
        assert len(rows) == 16
        assert len({row["id"] for row in rows}) == 16
        assert all(row["question"] and row["answers"] for row in rows)


def test_public_workloads_confirm_the_controlled_regressions() -> None:
    for spec in PUBLIC_WORKLOADS.values():
        result = asyncio.run(
            evaluate_public_workload(spec, bootstrap_resamples=500)
        )
        assert result.rows == 16
        assert result.authored_regressions == 5
        assert result.controls == 11
        assert result.baseline_pass_rate == 1.0
        assert result.candidate_pass_rate == 11 / 16
        assert result.naive_detects_regression is True
        assert result.engine_direction == "regression"
        assert result.engine_ci_upper < -0.05
        assert result.engine_confirms_regression is True
