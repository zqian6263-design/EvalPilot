"""Tests for ``scripts/validate-sut.ps1``'s core logic.

The validator is exercised over real HTTP: each test starts the real FastAPI
app in a uvicorn thread on an ephemeral port and drives the real validator
client against it. Faults are produced by a deliberately broken sibling app, so
every failure path is observed end to end rather than mocked.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from evalpilot.sut.validator import CheckResult, ValidationReport, main, run_validation

from .uvicorn_server import free_port, serve_app

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = ROOT / "integrations" / "sut_template"
TEMPLATE_APP_PATH = TEMPLATE_DIR / "app.py"
FAULTY_APP_PATH = TEMPLATE_DIR / "faulty_sut.py"
TEMPLATE_WORKLOAD_PATH = TEMPLATE_DIR / "workload.json"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def template():
    return _load_module("p5_template_for_validator", TEMPLATE_APP_PATH)


@pytest.fixture(scope="module")
def faulty():
    return _load_module("p5_faulty_sut", FAULTY_APP_PATH)


def names(report: ValidationReport) -> set[str]:
    return {check.name for check in report.checks}


def failing(report: ValidationReport) -> list[CheckResult]:
    return [check for check in report.checks if not check.ok]


def test_validator_accepts_the_onboarding_template(template) -> None:
    with serve_app(template.app) as base_url:
        report = run_validation(
            base_url=base_url,
            workload_path=TEMPLATE_WORKLOAD_PATH,
            timeout_seconds=10,
        )

    assert failing(report) == [], [check.detail for check in failing(report)]
    assert report.ok is True
    assert "health" in names(report)
    assert "capabilities-contract" in names(report)
    assert "undeclared-version-rejected" in names(report)
    assert "undeclared-intervention-rejected" in names(report)
    assert any(name.startswith("scenario:") for name in names(report))
    assert any(name.startswith("intervention:") for name in names(report))


def test_validator_probes_every_declared_version_for_every_scenario(template) -> None:
    with serve_app(template.app) as base_url:
        report = run_validation(
            base_url=base_url,
            workload_path=TEMPLATE_WORKLOAD_PATH,
            timeout_seconds=10,
        )

    workload = json.loads(TEMPLATE_WORKLOAD_PATH.read_text(encoding="utf-8"))
    capabilities = template.capabilities()
    for scenario in workload["scenarios"]:
        for version in capabilities["versions"]:
            assert f"scenario:{scenario['scenario_id']}@{version}" in names(report)


def test_validator_validates_the_workload_against_the_json_schema(template, tmp_path: Path) -> None:
    broken = json.loads(TEMPLATE_WORKLOAD_PATH.read_text(encoding="utf-8"))
    del broken["scenarios"][0]["must_include"]
    path = tmp_path / "broken-workload.json"
    path.write_text(json.dumps(broken), encoding="utf-8")

    with serve_app(template.app) as base_url:
        report = run_validation(base_url=base_url, workload_path=path, timeout_seconds=10)

    schema_checks = [check for check in report.checks if check.name == "workload-schema"]
    assert schema_checks and schema_checks[0].ok is False
    assert "must_include" in schema_checks[0].detail
    assert report.ok is False


def test_validator_reports_a_broken_capability_declaration(faulty) -> None:
    with serve_app(faulty.create_app("capabilities")) as base_url:
        report = run_validation(base_url=base_url, timeout_seconds=10)

    assert report.ok is False
    assert "capabilities" in names(report)
    assert failing(report)


def test_validator_rejects_a_declared_version_that_is_not_served(faulty) -> None:
    with serve_app(faulty.create_app("version")) as base_url:
        report = run_validation(base_url=base_url, timeout_seconds=10)

    assert report.ok is False
    assert any(
        check.name.startswith("scenario:") and not check.ok for check in report.checks
    )


def test_validator_rejects_a_declared_intervention_that_fails(faulty) -> None:
    with serve_app(faulty.create_app("intervention")) as base_url:
        report = run_validation(base_url=base_url, timeout_seconds=10)

    assert report.ok is False
    assert any(
        check.name.startswith("intervention:") and not check.ok for check in report.checks
    )


def test_validator_rejects_a_response_that_violates_the_contract(faulty) -> None:
    with serve_app(faulty.create_app("response")) as base_url:
        report = run_validation(base_url=base_url, timeout_seconds=10)

    assert report.ok is False
    assert any(
        check.name.startswith("scenario:") and not check.ok for check in report.checks
    )
    detail = " ".join(check.detail for check in failing(report))
    assert "contract" in detail.lower() or "answer" in detail.lower()


def test_validator_rejects_a_missing_health_endpoint(faulty) -> None:
    with serve_app(faulty.create_app("health")) as base_url:
        report = run_validation(base_url=base_url, timeout_seconds=10)

    assert report.ok is False
    assert any(check.name == "health" and not check.ok for check in report.checks)


def test_validator_rejects_a_sut_that_silently_accepts_undeclared_versions(faulty) -> None:
    with serve_app(faulty.create_app("silent")) as base_url:
        report = run_validation(base_url=base_url, timeout_seconds=10)

    assert report.ok is False
    assert any(
        check.name == "undeclared-version-rejected" and not check.ok
        for check in report.checks
    )


def test_validator_fails_loudly_when_the_sut_is_unreachable() -> None:
    base_url = f"http://127.0.0.1:{free_port()}"
    report = run_validation(base_url=base_url, timeout_seconds=2)

    assert report.ok is False
    assert failing(report)


def test_validator_rejects_a_workload_path_that_does_not_exist(tmp_path: Path) -> None:
    report = run_validation(
        base_url="http://127.0.0.1:1",
        workload_path=tmp_path / "missing.json",
        timeout_seconds=2,
    )
    assert report.ok is False
    assert any(
        check.name == "workload" and "missing.json" in check.detail
        for check in report.checks
    )


def test_report_serialises_to_ci_friendly_json(template) -> None:
    with serve_app(template.app) as base_url:
        report = run_validation(base_url=base_url, timeout_seconds=10)

    payload = report.to_json()
    assert payload["ok"] is True
    assert payload["base_url"].startswith("http://127.0.0.1:")
    assert isinstance(payload["checks"], list)
    assert {"name", "ok", "detail"} <= set(payload["checks"][0])
    json.dumps(payload)


def test_cli_exit_codes_and_json_report(template, tmp_path: Path, capsys) -> None:
    report_path = tmp_path / "report.json"
    with serve_app(template.app) as base_url:
        good = main(
            [
                "--base-url",
                base_url,
                "--workload",
                str(TEMPLATE_WORKLOAD_PATH),
                "--timeout-seconds",
                "10",
                "--json-report",
                str(report_path),
            ]
        )
    assert good == 0
    written = json.loads(report_path.read_text(encoding="utf-8"))
    assert written["ok"] is True
    assert "[PASS]" in capsys.readouterr().out

    bad = main(["--base-url", f"http://127.0.0.1:{free_port()}", "--timeout-seconds", "2"])
    assert bad == 1


def test_cli_requires_a_base_url() -> None:
    with pytest.raises(SystemExit):
        main([])
