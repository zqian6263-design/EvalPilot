"""Guards for the committed acceptance evidence.

An acceptance record is only worth committing if the numbers in it are the
numbers the command produced. These tests read the committed result files and
enforce the invariants that distinguish a measured counterfactual from a
predicted one — the failure mode that previously let the deterministic
fallback's output be published as a replay measurement.

Nothing here re-runs an acceptance check; each one is a real, slow, external
process. What it checks is that the recorded evidence could only have come from a
measured run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evalpilot.counterfactual import Intervention

ROOT = Path(__file__).resolve().parents[2]
P3_RESULT = ROOT / "docs" / "P3_BROWSER_RESULT.json"
P4_RESULT = ROOT / "docs" / "P4_MCP_RESULT.json"
P5_RESULT = ROOT / "docs" / "P5_E2E_RESULT.json"
TEMPLATE_WORKLOAD = ROOT / "integrations" / "sut_template" / "workload.json"

BUILTIN_INTERVENTIONS = {member.value for member in Intervention}


def _load(path: Path) -> dict:
    assert path.is_file(), f"missing acceptance evidence: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_measured_replays(
    document: dict, expected: int, *, counter_key: str = "measured_http_replays"
) -> None:
    """Every recorded counterfactual must be a measurement, not a prediction.

    Two independent signals are required, because either one alone can be faked
    by a careless script:

    1. the run persisted a replay trace per counterfactual, so the replay
       actually reached the system under test; and
    2. the persisted rationale is the engine's wording ("Replayed ... "), not the
       deterministic fallback's ("... is predicted to restore ...").
    """

    counterfactuals = document["counterfactuals"]
    assert len(counterfactuals) == expected
    assert document.get(counter_key, 0) >= expected, (
        f"a counterfactual without a measured replay trace ({counter_key}) is a "
        "fallback prediction, not a measurement"
    )
    for item in counterfactuals:
        assert item["verdict"] == "root_cause", item
        assert item["counterfactual_score"] > item["original_score"], item
        rationale = item["rationale"]
        assert rationale.startswith("Replayed "), rationale
        assert "predicted" not in rationale.lower(), rationale


def test_p3_browser_evidence_records_measured_replays() -> None:
    document = _load(P3_RESULT)

    assert document["status"] == "passed"
    assert document["run_id"] and document["investigation_id"]
    assert document["matched_scenarios"] == 6
    assert len(document["regressed_scenarios"]) == 3
    assert len(document["control_scenarios"]) == 3
    assert document["decision"] == "block"
    _assert_measured_replays(
        document, expected=3, counter_key="measured_browser_replays"
    )

    # Both arms of every counterfactual ran in a real browser, so the run gained
    # one screenshot and one browser trace per arm on top of its own 12.
    arms = document["measured_replay_arms"]
    assert arms == 2 * len(document["counterfactuals"])
    assert document["measured_replay_traces"] == 12 + arms
    assert document["measured_replay_screenshots"] == 12 + arms
    assert document["trace_evidence"] == 12 and document["screenshot_evidence"] == 12


def test_p4_mcp_evidence_records_measured_replays() -> None:
    document = _load(P4_RESULT)

    assert document["status"] == "passed"
    assert document["regression_run_id"] and document["investigation_id"]
    assert document["matched_scenarios"] == 6
    assert len(document["regressed_scenarios"]) == 3
    assert len(document["control_scenarios"]) == 3
    _assert_measured_replays(document, expected=3)
    assert {
        item["intervention"] for item in document["counterfactuals"]
    } == {"mcp_v2_error_path_enabled"}


def test_p4_replay_intervention_is_not_a_builtin_name() -> None:
    """The P4 replay only proves the external-name path if the name is external."""

    document = _load(P4_RESULT)

    assert {
        item["intervention"] for item in document["counterfactuals"]
    }.isdisjoint(BUILTIN_INTERVENTIONS)


def test_p5_template_e2e_evidence_records_measured_replays() -> None:
    document = _load(P5_RESULT)

    assert document["status"] == "passed"
    assert document["workload_file"] == "integrations/sut_template/workload.json"
    assert document["onboarding_gate"]["exit_code"] == 0
    assert document["onboarding_gate"]["checks_failed"] == 0
    assert document["regression_run_id"] and document["control_run_id"]
    assert document["investigation_id"]
    assert document["matched_scenarios"] == 8
    assert document["regression_confirmed"] is True
    assert document["control_run_mean_difference"] == 0.0
    assert document["decision"] == "block"
    _assert_measured_replays(document, expected=5)


def test_p5_replay_used_a_custom_intervention_name() -> None:
    """The P5 proof is only meaningful if the replayed intervention was *not* one
    of the engine's built-in names: that is the path that used to fall back."""

    document = _load(P5_RESULT)
    custom = document["custom_intervention"]

    assert custom not in BUILTIN_INTERVENTIONS
    assert custom in document["sut_interventions"]
    assert {item["intervention"] for item in document["counterfactuals"]} == {custom}


def test_p5_regressed_scenarios_match_the_template_workload() -> None:
    """The recorded result must describe the workload that is actually shipped."""

    document = _load(P5_RESULT)
    workload = json.loads(TEMPLATE_WORKLOAD.read_text(encoding="utf-8"))

    declared_regressions = {
        scenario["scenario_id"]
        for scenario in workload["scenarios"]
        if scenario.get("suggested_intervention")
    }
    assert set(document["regressed_scenarios"]) == declared_regressions
    assert set(document["failing_scenarios"]) == declared_regressions
    assert declared_regressions.isdisjoint(set(document["control_scenarios"]))
    assert set(document["control_scenarios"]) <= {
        scenario["scenario_id"] for scenario in workload["scenarios"]
    }
