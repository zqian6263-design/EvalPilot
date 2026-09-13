"""Tests for judge calibration metrics."""

from __future__ import annotations

from evalpilot.evaluation.calibration import calibration_metrics


def test_calibration_metrics_report_mae_bias_and_correlation() -> None:
    result = calibration_metrics([(0.3, 0.2), (0.6, 0.5), (0.9, 0.8)])

    assert result["count"] == 3
    assert result["mae"] == 0.1
    assert result["bias"] == 0.1
    assert result["pearson"] == 1.0
    assert result["exact_agreement"] == 0.0


def test_calibration_metrics_handle_empty_and_single_rows() -> None:
    empty = calibration_metrics([])
    single = calibration_metrics([(0.5, 0.7)])

    assert empty["count"] == 0
    assert empty["mae"] is None
    assert single["mae"] == 0.2
    assert single["pearson"] is None
