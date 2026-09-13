"""Calibration metrics for comparing judge scores with human labels."""

from __future__ import annotations

import math
from collections.abc import Sequence


def calibration_metrics(pairs: Sequence[tuple[float, float]]) -> dict[str, float | int | None]:
    """Return MAE, signed bias, Pearson correlation, and exact agreement."""

    count = len(pairs)
    if count == 0:
        return {
            "count": 0,
            "mae": None,
            "bias": None,
            "pearson": None,
            "exact_agreement": None,
        }

    errors = [judge - human for judge, human in pairs]
    mae = sum(abs(error) for error in errors) / count
    bias = sum(errors) / count
    exact = sum(1 for error in errors if abs(error) <= 1e-9) / count

    if count < 2:
        pearson = None
    else:
        judge_mean = sum(judge for judge, _ in pairs) / count
        human_mean = sum(human for _, human in pairs) / count
        covariance = sum(
            (judge - judge_mean) * (human - human_mean)
            for judge, human in pairs
        )
        judge_var = sum((judge - judge_mean) ** 2 for judge, _ in pairs)
        human_var = sum((human - human_mean) ** 2 for _, human in pairs)
        pearson = (
            covariance / math.sqrt(judge_var * human_var)
            if judge_var > 0 and human_var > 0
            else None
        )

    return {
        "count": count,
        "mae": round(mae, 6),
        "bias": round(bias, 6),
        "pearson": round(pearson, 6) if pearson is not None else None,
        "exact_agreement": round(exact, 6),
    }


__all__ = ["calibration_metrics"]
