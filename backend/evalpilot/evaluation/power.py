"""Paired-sample power diagnostics for release comparisons."""

from __future__ import annotations

import math
from collections.abc import Sequence
from statistics import NormalDist, stdev

Z_ALPHA_ONE_SIDED = NormalDist().inv_cdf(0.95)
Z_POWER_80 = NormalDist().inv_cdf(0.80)


def paired_power_metrics(
    differences: Sequence[float],
    *,
    threshold: float,
    target_power: float = 0.80,
) -> dict[str, float | int | bool | None]:
    """Return effect-size and sample-size diagnostics for paired differences.

    Power is computed for a one-sided regression test at 95% confidence. The
    result is diagnostic only: it never changes the measured release decision.
    """

    n = len(differences)
    if n < 2:
        return {
            "minimum_detectable_effect": None,
            "required_matched_cases": None,
            "observed_power": None,
            "target_power": target_power,
            "sample_size_adequate": False,
        }

    spread = stdev(differences)
    standard_error = spread / math.sqrt(n)
    z_power = NormalDist().inv_cdf(target_power)
    factor = Z_ALPHA_ONE_SIDED + z_power
    absolute_threshold = abs(float(threshold)) or 1e-12
    minimum_detectable = factor * standard_error

    if spread == 0:
        required = 2
        observed_power = 1.0
    else:
        required = max(2, math.ceil((factor * spread / absolute_threshold) ** 2))
        z = (abs(sum(differences) / n) - absolute_threshold) / standard_error
        observed_power = NormalDist().cdf(z - Z_ALPHA_ONE_SIDED)

    return {
        "minimum_detectable_effect": round(minimum_detectable, 6),
        "required_matched_cases": required,
        "observed_power": round(observed_power, 6),
        "target_power": target_power,
        "sample_size_adequate": n >= required,
    }


__all__ = ["paired_power_metrics"]
