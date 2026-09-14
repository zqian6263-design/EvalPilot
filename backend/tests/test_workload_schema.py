"""Tests for the published ``EVALPILOT_WORKLOAD_FILE`` JSON Schema.

The schema is validated with the standard ``jsonschema`` library, and it must
accept every workload that already ships in this repository.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "workload.schema.json"
TEMPLATE_WORKLOAD_PATH = ROOT / "integrations" / "sut_template" / "workload.json"
REPOSITORY_WORKLOADS = (
    ROOT / "integrations" / "mcp_retro" / "workload.json",
    ROOT / "integrations" / "mem0_retro" / "workload.json",
    ROOT / "integrations" / "mem0_retro" / "browser_workload.json",
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def schema() -> dict:
    return _load(SCHEMA_PATH)


@pytest.fixture(scope="module")
def validator(schema: dict) -> Draft202012Validator:
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@pytest.fixture()
def valid_workload() -> dict:
    return _load(TEMPLATE_WORKLOAD_PATH)


def errors(validator: Draft202012Validator, document: dict) -> list[str]:
    return [error.message for error in validator.iter_errors(document)]


def test_schema_is_a_valid_draft_2020_12_schema(schema: dict) -> None:
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_schema_documents_every_published_field(schema: dict) -> None:
    top = schema["properties"]
    assert {
        "workload_id",
        "baseline_version",
        "candidate_version",
        "scenarios",
    } <= set(top)

    scenario = schema["$defs"]["scenario"]["properties"]
    assert {
        "scenario_id",
        "question",
        "category",
        "difficulty",
        "expected_doc_ids",
        "must_include",
    } <= set(scenario)
    assert {
        "must_avoid",
        "expects_refusal",
        "hypothesis_domain",
        "hypothesis_kind",
        "hypothesis_title",
        "suggested_intervention",
        "probe_action",
        "recommendation",
        "browser_url",
        "browser_actions",
    } <= set(scenario)


def test_known_good_workload_passes(validator: Draft202012Validator, valid_workload: dict) -> None:
    assert errors(validator, valid_workload) == []


@pytest.mark.parametrize("path", REPOSITORY_WORKLOADS, ids=lambda item: item.parent.name)
def test_repository_workloads_pass(
    validator: Draft202012Validator, path: Path
) -> None:
    assert errors(validator, _load(path)) == []


def test_missing_workload_id_is_rejected(
    validator: Draft202012Validator, valid_workload: dict
) -> None:
    broken = copy.deepcopy(valid_workload)
    del broken["workload_id"]
    messages = errors(validator, broken)
    assert messages
    assert any("workload_id" in message for message in messages)


def test_missing_scenarios_is_rejected(
    validator: Draft202012Validator, valid_workload: dict
) -> None:
    broken = copy.deepcopy(valid_workload)
    del broken["scenarios"]
    messages = errors(validator, broken)
    assert messages
    assert any("scenarios" in message for message in messages)


def test_empty_scenarios_is_rejected(
    validator: Draft202012Validator, valid_workload: dict
) -> None:
    broken = copy.deepcopy(valid_workload)
    broken["scenarios"] = []
    assert errors(validator, broken)


def test_scenario_missing_question_is_rejected(
    validator: Draft202012Validator, valid_workload: dict
) -> None:
    broken = copy.deepcopy(valid_workload)
    del broken["scenarios"][0]["question"]
    messages = errors(validator, broken)
    assert messages
    assert any("question" in message for message in messages)


def test_scenario_missing_must_include_is_rejected(
    validator: Draft202012Validator, valid_workload: dict
) -> None:
    broken = copy.deepcopy(valid_workload)
    del broken["scenarios"][0]["must_include"]
    messages = errors(validator, broken)
    assert messages
    assert any("must_include" in message for message in messages)


def test_invalid_category_is_rejected(
    validator: Draft202012Validator, valid_workload: dict
) -> None:
    broken = copy.deepcopy(valid_workload)
    broken["scenarios"][0]["category"] = "made-up-category"
    assert errors(validator, broken)


@pytest.mark.parametrize("value", [-0.1, 1.5, "hard"])
def test_invalid_difficulty_is_rejected(
    validator: Draft202012Validator, valid_workload: dict, value: object
) -> None:
    broken = copy.deepcopy(valid_workload)
    broken["scenarios"][0]["difficulty"] = value
    assert errors(validator, broken)


def test_unknown_scenario_field_is_rejected(
    validator: Draft202012Validator, valid_workload: dict
) -> None:
    broken = copy.deepcopy(valid_workload)
    broken["scenarios"][0]["surprise_field"] = "typo"
    assert errors(validator, broken)


def test_duplicate_scenario_ids_are_not_silently_accepted(
    validator: Draft202012Validator, valid_workload: dict, tmp_path: Path
) -> None:
    """The loader rejects duplicates at runtime; the schema is a *static* guard.

    JSON Schema cannot express uniqueness of a property value, so this test
    pins the documented division of labour: the schema is structural, and
    ``_load_workload`` remains the authority on duplicate ids.
    """

    broken = copy.deepcopy(valid_workload)
    broken["scenarios"].append(copy.deepcopy(broken["scenarios"][0]))
    assert errors(validator, broken) == []

    from evalpilot.fixtures import _load_workload

    path = tmp_path / "duplicate-probe.json"
    path.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate scenario_id"):
        _load_workload(path)


def test_browser_workload_actions_are_typed(
    validator: Draft202012Validator, valid_workload: dict
) -> None:
    broken = copy.deepcopy(valid_workload)
    broken["scenarios"][0]["browser_actions"] = ["click #run"]
    assert errors(validator, broken)
