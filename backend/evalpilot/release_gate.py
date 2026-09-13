"""Single source of truth for the machine-enforced release decision."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from evalpilot.models import ReleaseGate


def build_release_gate(
    *,
    run_id: str,
    metrics: Mapping[str, Any],
    report_url: str,
) -> ReleaseGate:
    """Convert measured report metrics into the CI-compatible gate contract."""

    confirmed = metrics.get("regression_confirmed") is True
    detected = metrics.get("regression_detected") is True
    if confirmed:
        decision = "block"
        exit_code = 2
        reasons = ["regression_confirmed"]
    elif detected:
        decision = "review"
        exit_code = 1
        reasons = ["localized_regression_requires_review"]
    else:
        decision = "allow"
        exit_code = 0
        reasons = ["no_regression_detected"]

    return ReleaseGate(
        run_id=run_id,
        decision=decision,
        exit_code=exit_code,
        regression_detected=detected,
        regression_confirmed=confirmed,
        baseline_pass_rate=float(metrics.get("baseline_pass_rate", 0.0)),
        candidate_pass_rate=float(metrics.get("candidate_pass_rate", 0.0)),
        mean_difference=_optional_float(metrics.get("mean_difference")),
        ci_lower=_optional_float(metrics.get("ci_lower")),
        ci_upper=_optional_float(metrics.get("ci_upper")),
        threshold=_optional_float(metrics.get("regression_threshold")),
        reasons=reasons,
        report_url=report_url,
    )


def _optional_float(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


__all__ = ["build_release_gate"]
