"""Tests for paired-sample power diagnostics."""

from __future__ import annotations

import pytest

from evalpilot.evaluation.power import paired_power_metrics


def test_identical_pairs_need_no_uncertainty_budget() -> None:
    result = paired_power_metrics([0.0, 0.0, 0.0], threshold=0.05)

    assert result["minimum_detectable_effect"] == 0
    assert result["required_matched_cases"] == 2
    assert result["observed_power"] == 1.0
    assert result["sample_size_adequate"] is True


def test_variable_pairs_report_a_finite_sample_requirement() -> None:
    result = paired_power_metrics([-0.2, -0.1, 0.0, 0.0], threshold=0.05)

    assert result["minimum_detectable_effect"] > 0
    assert result["required_matched_cases"] > 4
    assert 0.0 <= result["observed_power"] <= 1.0
    assert result["sample_size_adequate"] is False


def test_small_samples_return_explicit_none_values() -> None:
    result = paired_power_metrics([-0.2], threshold=0.05)

    assert result["minimum_detectable_effect"] is None
    assert result["required_matched_cases"] is None
    assert result["observed_power"] is None


def test_invalid_empty_threshold_is_guarded() -> None:
    result = paired_power_metrics([-0.2, -0.1], threshold=0.0)

    assert result["required_matched_cases"] is not None
