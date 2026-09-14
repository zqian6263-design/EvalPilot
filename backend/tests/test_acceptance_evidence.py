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

from evalpilot.counterfactual import Intervention

ROOT = Path(__file__).resolve().parents[2]
P4_RESULT = ROOT / "docs" / "P4_MCP_RESULT.json"

BUILTIN_INTERVENTIONS = {member.value for member in Intervention}


def _load(path: Path) -> dict:
    assert path.is_file(), f"missing acceptance evidence: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_measured_replays(document: dict, expected: int) -> None:
    """Every recorded counterfactual must be a measurement, not a prediction.

    Two independent signals are required, because either one alone can be faked
    by a careless script:

    1. the run persisted at least one HTTP replay trace per counterfactual, so
       the replay actually reached the system under test; and
    2. the persisted rationale is the engine's wording ("Replayed ... "), not the
       deterministic fallback's ("... is predicted to restore ...").
    """

    counterfactuals = document["counterfactuals"]
    assert len(counterfactuals) == expected
    assert document.get("measured_http_replays", 0) >= expected, (
        "a counterfactual without a measured HTTP replay trace is a fallback "
        "prediction, not a measurement"
    )
    for item in counterfactuals:
        assert item["verdict"] == "root_cause", item
        assert item["counterfactual_score"] > item["original_score"], item
        rationale = item["rationale"]
        assert rationale.startswith("Replayed "), rationale
        assert "predicted" not in rationale.lower(), rationale


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
