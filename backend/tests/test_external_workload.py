from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from evalpilot.counterfactual.models import Intervention
from evalpilot.fixtures import active_scenarios, scenario_by_id
from evalpilot.investigation.service import _suggested_interventions
from evalpilot.planner import build_cases, plan_case_count, select_scenarios


def _write_workload(path: Path) -> Path:
    payload = {
        "workload_id": "unit-test",
        "scenarios": [
            {
                "scenario_id": "tenant-overwrite",
                "question": "Can metadata move this memory to another tenant?",
                "category": "adversarial",
                "difficulty": 0.8,
                "expected_doc_ids": ["mem0-identity-scope"],
                "must_include": ["owner_visible=true", "foreign_visible=false"],
                "must_avoid": ["foreign_visible=true"],
                "hypothesis_domain": "security",
                "hypothesis_kind": "memory_identity_scope",
                "hypothesis_title": "metadata can overwrite immutable identity",
                "suggested_intervention": "identity_metadata_stripped",
                "probe_action": "Replay with identity metadata stripped.",
            },
            {
                "scenario_id": "normal-control",
                "question": "Does a normal metadata update remain readable?",
                "category": "normal",
                "difficulty": 0.2,
                "expected_doc_ids": ["mem0-identity-scope"],
                "must_include": ["owner_visible=true"],
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_external_workload_replaces_builtin_scenarios(monkeypatch, tmp_path: Path) -> None:
    workload = _write_workload(tmp_path / "workload.json")
    monkeypatch.setenv("EVALPILOT_WORKLOAD_FILE", str(workload))

    scenarios = active_scenarios()
    assert [item.scenario_id for item in scenarios] == ["tenant-overwrite", "normal-control"]
    assert scenario_by_id("tenant-overwrite").suggested_intervention == "identity_metadata_stripped"
    assert plan_case_count(None, 1) == 2
    assert len(build_cases("run-1", 2, 7)) == 4


def test_external_workload_validates_duplicate_ids(monkeypatch, tmp_path: Path) -> None:
    workload = _write_workload(tmp_path / "workload.json")
    payload = json.loads(workload.read_text(encoding="utf-8"))
    payload["scenarios"].append(dict(payload["scenarios"][0]))
    workload.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("EVALPILOT_WORKLOAD_FILE", str(workload))

    with pytest.raises(ValueError, match="duplicate scenario_id"):
        select_scenarios(1)


def test_identity_intervention_is_executable() -> None:
    assert Intervention.parse("identity_metadata_stripped") is Intervention.IDENTITY_METADATA_STRIPPED


def test_custom_scenario_supplies_investigation_intervention(monkeypatch, tmp_path: Path) -> None:
    workload = _write_workload(tmp_path / "workload.json")
    monkeypatch.setenv("EVALPILOT_WORKLOAD_FILE", str(workload))
    intake = SimpleNamespace(
        regressed=[
            SimpleNamespace(
                scenario_id="tenant-overwrite",
                leaked_markers=[],
                missing_facts=["owner_visible=true"],
            )
        ]
    )

    suggested = _suggested_interventions([], {}, intake)
    assert suggested["tenant-overwrite"] == "identity_metadata_stripped"