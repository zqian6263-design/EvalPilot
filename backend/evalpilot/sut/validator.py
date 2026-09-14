"""Onboarding validator for an external HTTP system under test (SUT).

This is the logic behind ``scripts/validate-sut.ps1``. It answers one question:
*could a real evaluation run against this service be trusted?* Everything it
reports is observed over real HTTP against the service itself, and nothing is
downgraded to a pass:

* ``GET /health`` and ``GET /capabilities`` must exist and parse.
* Every advertised revision and intervention is exercised once.
* A revision or intervention that was never advertised must be rejected with
  HTTP 4xx, otherwise the capability declaration is decoration rather than a
  contract.
* Every workload scenario is sent for every advertised revision, and the answer
  record must satisfy the same ``SutResponse`` model the executor enforces.
* When a workload is supplied it must also satisfy
  ``schemas/workload.schema.json``.

Usage::

    python -m evalpilot.sut.validator --base-url http://127.0.0.1:8020 \\
        --workload integrations/sut_template/workload.json

Exit code 0 means every check passed. Exit code 1 means at least one check
failed; the printed report names each one.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import httpx
from pydantic import ValidationError

from evalpilot.config import DEFAULT_SUT_TIMEOUT_SECONDS
from evalpilot.sut.http_executor import SutCapabilities, SutResponse

#: Probe labels that no honest SUT can advertise.
PROBE_VERSION = "__evalpilot_undeclared_version__"
PROBE_INTERVENTION = "__evalpilot_undeclared_intervention__"

#: Question used for capability probes when no workload was supplied.
GENERIC_PROBE_QUESTION = "Onboarding probe: are you able to serve this revision?"

DEFAULT_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "schemas" / "workload.schema.json"
)

_DETAIL_LIMIT = 200


@dataclass(frozen=True)
class CheckResult:
    """One observed onboarding check."""

    name: str
    ok: bool
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


@dataclass(frozen=True)
class ValidationReport:
    """The full result of one validation run."""

    base_url: str
    checks: tuple[CheckResult, ...]
    workload: str | None = None
    schema: str | None = None

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    @property
    def failures(self) -> tuple[CheckResult, ...]:
        return tuple(check for check in self.checks if not check.ok)

    @property
    def passed(self) -> int:
        return sum(1 for check in self.checks if check.ok)

    def to_json(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "base_url": self.base_url,
            "workload": self.workload,
            "schema": self.schema,
            "checks_total": len(self.checks),
            "checks_passed": self.passed,
            "checks_failed": len(self.failures),
            "checks": [check.as_dict() for check in self.checks],
        }


@dataclass(frozen=True)
class _Probe:
    """One HTTP attempt, with transport errors captured instead of raised."""

    status_code: int | None
    body: Any
    error: str | None

    @property
    def reached(self) -> bool:
        return self.error is None


def _clip(text: str) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= _DETAIL_LIMIT else text[: _DETAIL_LIMIT - 1] + "…"


def _probe(
    client: httpx.Client,
    method: str,
    url: str,
    payload: Mapping[str, Any] | None = None,
) -> _Probe:
    try:
        response = client.request(method, url, json=payload)
    except httpx.HTTPError as exc:
        return _Probe(None, None, f"{method} {url} failed: {exc}")
    try:
        body: Any = response.json()
    except ValueError:
        body = response.text[:_DETAIL_LIMIT]
    return _Probe(response.status_code, body, None)


def _response_check(
    *,
    name: str,
    label: str,
    probe: _Probe,
    require_non_empty_answer: bool = True,
) -> CheckResult:
    """Validate one answer response against the executor's contract model."""

    if not probe.reached:
        return CheckResult(name, False, str(probe.error))
    if probe.status_code != 200:
        body = probe.body if isinstance(probe.body, str) else json.dumps(probe.body)
        return CheckResult(
            name,
            False,
            f"{label} returned HTTP {probe.status_code}: {_clip(body)}",
        )
    if not isinstance(probe.body, dict):
        return CheckResult(name, False, f"{label} did not return a JSON object")
    try:
        parsed = SutResponse.model_validate(probe.body)
    except ValidationError as exc:
        first = exc.errors()[0]
        location = ".".join(str(part) for part in first.get("loc", ())) or "<root>"
        return CheckResult(
            name,
            False,
            f"{label} violates the response contract at {location}: {first.get('msg')}",
        )
    if require_non_empty_answer and not parsed.answer.strip():
        return CheckResult(name, False, f"{label} returned an empty answer")
    return CheckResult(
        name,
        True,
        f"{label} returned HTTP 200 with a contract-valid answer ({len(parsed.answer)} chars)",
    )


def load_workload(path: Path) -> dict[str, Any]:
    """Read a workload document, raising ``ValueError`` on unusable input."""

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read workload {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"workload {path} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError(
            f"workload {path} must be a JSON object with a scenarios list"
        )
    scenarios = document.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError(f"workload {path} must contain a non-empty scenarios list")
    return document


def schema_errors(document: Any, schema: Mapping[str, Any]) -> list[str]:
    """Validate ``document`` with the standard JSON Schema library."""

    import jsonschema

    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(document), key=lambda item: list(item.path))
    messages: list[str] = []
    for error in errors:
        location = "/".join(str(part) for part in error.path) or "<root>"
        messages.append(f"{location}: {error.message}")
    return messages


def _scenario_question(document: Mapping[str, Any] | None) -> str:
    if document:
        scenarios = document.get("scenarios")
        if isinstance(scenarios, list) and scenarios:
            question = scenarios[0].get("question") if isinstance(scenarios[0], dict) else None
            if isinstance(question, str) and question.strip():
                return question
    return GENERIC_PROBE_QUESTION


def _answer_payload(
    *, version: str, question: str, intervention: str | None, scenario_id: str
) -> dict[str, Any]:
    return {
        "run_id": "validate-sut-run",
        "test_case_id": f"validate-sut-{scenario_id}",
        "scenario_id": scenario_id,
        "question": question,
        "version": version,
        "intervention": intervention,
    }


def _static_checks(
    *,
    workload_path: Path | None,
    schema_path: Path,
) -> tuple[list[CheckResult], dict[str, Any] | None, bool]:
    """Checks that do not need the SUT to be reachable.

    Returns the checks, the parsed workload (when it is usable), and whether the
    run must stop before any HTTP probe.
    """

    if workload_path is None:
        return [], None, False

    try:
        document = load_workload(workload_path)
    except ValueError as exc:
        return [CheckResult("workload", False, str(exc))], None, True

    checks = [
        CheckResult(
            "workload",
            True,
            f"loaded {len(document['scenarios'])} scenario(s) from {workload_path}",
        )
    ]

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        checks.append(
            CheckResult("workload-schema", False, f"cannot read {schema_path}: {exc}")
        )
        return checks, document, True

    try:
        errors = schema_errors(document, schema)
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        checks.append(
            CheckResult(
                "workload-schema",
                False,
                f"the jsonschema library is required to validate workloads: {exc}",
            )
        )
        return checks, document, True

    if errors:
        checks.append(
            CheckResult(
                "workload-schema",
                False,
                f"{workload_path} violates {schema_path.name}: " + "; ".join(errors[:5]),
            )
        )
        return checks, document, True

    checks.append(
        CheckResult(
            "workload-schema",
            True,
            f"{workload_path} satisfies {schema_path.name}",
        )
    )
    return checks, document, False


def run_validation(
    *,
    base_url: str,
    workload_path: Path | str | None = None,
    timeout_seconds: float = DEFAULT_SUT_TIMEOUT_SECONDS,
    schema_path: Path | str | None = None,
) -> ValidationReport:
    """Validate one external SUT over HTTP and return every observed check."""

    base = base_url.rstrip("/")
    resolved_workload = Path(workload_path) if workload_path is not None else None
    resolved_schema = Path(schema_path) if schema_path is not None else DEFAULT_SCHEMA_PATH

    workload_checks, document, fatal = _static_checks(
        workload_path=resolved_workload,
        schema_path=resolved_schema,
    )
    checks: list[CheckResult] = list(workload_checks)
    if fatal:
        return ValidationReport(
            base_url=base,
            checks=tuple(checks),
            workload=str(resolved_workload) if resolved_workload is not None else None,
            schema=str(resolved_schema),
        )

    with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
        health = _probe(client, "GET", f"{base}/health")
        if not health.reached:
            checks.append(CheckResult("health", False, str(health.error)))
        elif health.status_code != 200:
            checks.append(
                CheckResult(
                    "health",
                    False,
                    f"GET /health returned HTTP {health.status_code}",
                )
            )
        else:
            checks.append(CheckResult("health", True, "GET /health returned HTTP 200"))
            if isinstance(health.body, dict):
                checks.append(
                    CheckResult(
                        "health-contract",
                        True,
                        "GET /health returned a JSON object"
                        + (
                            f" (status={health.body.get('status')!r})"
                            if "status" in health.body
                            else ""
                        ),
                    )
                )
            else:
                checks.append(
                    CheckResult(
                        "health-contract",
                        False,
                        "GET /health did not return a JSON object",
                    )
                )

        capabilities_probe = _probe(client, "GET", f"{base}/capabilities")
        capabilities: SutCapabilities | None = None
        if not capabilities_probe.reached:
            checks.append(CheckResult("capabilities", False, str(capabilities_probe.error)))
        elif capabilities_probe.status_code == 404:
            checks.append(
                CheckResult(
                    "capabilities",
                    False,
                    "GET /capabilities returned HTTP 404; onboarding requires a capability "
                    "declaration so every advertised revision and intervention can be checked "
                    "(the runtime still supports the legacy 404 fallback, but nothing can be "
                    "validated against it)",
                )
            )
        elif capabilities_probe.status_code != 200:
            checks.append(
                CheckResult(
                    "capabilities",
                    False,
                    f"GET /capabilities returned HTTP {capabilities_probe.status_code}",
                )
            )
        elif not isinstance(capabilities_probe.body, dict):
            checks.append(
                CheckResult("capabilities", False, "GET /capabilities did not return a JSON object")
            )
        else:
            checks.append(
                CheckResult("capabilities", True, "GET /capabilities returned HTTP 200")
            )
            try:
                capabilities = SutCapabilities.model_validate(capabilities_probe.body)
            except ValidationError as exc:
                first = exc.errors()[0]
                checks.append(
                    CheckResult(
                        "capabilities-contract",
                        False,
                        f"capability declaration violates the contract: {first.get('msg')}",
                    )
                )

        if capabilities is not None:
            problems: list[str] = []
            if not capabilities.versions:
                problems.append("no versions advertised")
            if len(set(capabilities.versions)) != len(capabilities.versions):
                problems.append("duplicate entries in versions")
            if any(not item.strip() for item in capabilities.versions):
                problems.append("empty entry in versions")
            if len(set(capabilities.interventions)) != len(capabilities.interventions):
                problems.append("duplicate entries in interventions")
            if any(not item.strip() for item in capabilities.interventions):
                problems.append("empty entry in interventions")
            checks.append(
                CheckResult(
                    "capabilities-contract",
                    not problems,
                    "; ".join(problems)
                    if problems
                    else (
                        f"contract_version={capabilities.contract_version}, "
                        f"versions={capabilities.versions}, "
                        f"interventions={capabilities.interventions}"
                    ),
                )
            )

        if capabilities is not None and capabilities.versions:
            if isinstance(health.body, dict) and isinstance(health.body.get("versions"), list):
                extra = [
                    item
                    for item in health.body["versions"]
                    if item not in capabilities.versions
                ]
                checks.append(
                    CheckResult(
                        "version-consistency",
                        not extra,
                        (
                            f"GET /health advertises versions not in /capabilities: {extra}"
                            if extra
                            else "GET /health and /capabilities agree on the advertised versions"
                        ),
                    )
                )

            question = _scenario_question(document)

            undeclared_version = _probe(
                client,
                "POST",
                f"{base}/v1/answer",
                _answer_payload(
                    version=PROBE_VERSION,
                    question=question,
                    intervention=None,
                    scenario_id="undeclared-version-probe",
                ),
            )
            if not undeclared_version.reached:
                checks.append(
                    CheckResult("undeclared-version-rejected", False, str(undeclared_version.error))
                )
            else:
                rejected = (
                    undeclared_version.status_code is not None
                    and 400 <= undeclared_version.status_code < 500
                )
                checks.append(
                    CheckResult(
                        "undeclared-version-rejected",
                        rejected,
                        (
                            f"undeclared version {PROBE_VERSION!r} was rejected with HTTP "
                            f"{undeclared_version.status_code}"
                            if rejected
                            else (
                                f"undeclared version {PROBE_VERSION!r} was answered with HTTP "
                                f"{undeclared_version.status_code}; an unadvertised revision must "
                                "be rejected with HTTP 4xx"
                            )
                        ),
                    )
                )

            undeclared_intervention = _probe(
                client,
                "POST",
                f"{base}/v1/answer",
                _answer_payload(
                    version=capabilities.versions[0],
                    question=question,
                    intervention=PROBE_INTERVENTION,
                    scenario_id="undeclared-intervention-probe",
                ),
            )
            if not undeclared_intervention.reached:
                checks.append(
                    CheckResult(
                        "undeclared-intervention-rejected",
                        False,
                        str(undeclared_intervention.error),
                    )
                )
            else:
                rejected = (
                    undeclared_intervention.status_code is not None
                    and 400 <= undeclared_intervention.status_code < 500
                )
                checks.append(
                    CheckResult(
                        "undeclared-intervention-rejected",
                        rejected,
                        (
                            f"undeclared intervention {PROBE_INTERVENTION!r} was rejected with "
                            f"HTTP {undeclared_intervention.status_code}"
                            if rejected
                            else (
                                f"undeclared intervention {PROBE_INTERVENTION!r} was answered with "
                                f"HTTP {undeclared_intervention.status_code}; an intervention that "
                                "was not whitelisted must be rejected with HTTP 4xx"
                            )
                        ),
                    )
                )

            for intervention in capabilities.interventions:
                name = f"intervention:{intervention}"
                probe = _probe(
                    client,
                    "POST",
                    f"{base}/v1/answer",
                    _answer_payload(
                        version=capabilities.versions[0],
                        question=question,
                        intervention=intervention,
                        scenario_id=f"intervention-{intervention}",
                    ),
                )
                checks.append(
                    _response_check(
                        name=name,
                        label=f"advertised intervention {intervention!r}",
                        probe=probe,
                    )
                )

            if document is not None:
                declared = set(capabilities.versions)
                declared_interventions = set(capabilities.interventions)
                declared_problems: list[str] = []
                for key in ("baseline_version", "candidate_version"):
                    value = document.get(key)
                    if isinstance(value, str) and value and value not in declared:
                        declared_problems.append(
                            f"{key}={value!r} is not advertised by the SUT"
                        )
                for scenario in document.get("scenarios", []):
                    if not isinstance(scenario, dict):
                        continue
                    suggested = scenario.get("suggested_intervention")
                    if (
                        isinstance(suggested, str)
                        and suggested
                        and suggested not in declared_interventions
                    ):
                        declared_problems.append(
                            f"{scenario.get('scenario_id')}: suggested_intervention "
                            f"{suggested!r} is not advertised by the SUT"
                        )
                checks.append(
                    CheckResult(
                        "workload-capabilities",
                        not declared_problems,
                        (
                            "; ".join(declared_problems[:5])
                            if declared_problems
                            else "the workload only references advertised revisions and interventions"
                        ),
                    )
                )

            # Every advertised revision is exercised for every scenario. With no
            # workload supplied a synthetic probe stands in, so a revision that
            # is declared but never served still fails onboarding.
            probes: list[tuple[str, str]] = []
            if document is not None:
                for scenario in document.get("scenarios", []):
                    if not isinstance(scenario, dict):
                        continue
                    probes.append(
                        (
                            str(scenario.get("scenario_id") or "unnamed"),
                            str(scenario.get("question") or ""),
                        )
                    )
            if not probes:
                probes.append(("onboarding-probe", GENERIC_PROBE_QUESTION))

            for scenario_id, question in probes:
                for version in capabilities.versions:
                    name = f"scenario:{scenario_id}@{version}"
                    probe = _probe(
                        client,
                        "POST",
                        f"{base}/v1/answer",
                        _answer_payload(
                            version=version,
                            question=question,
                            intervention=None,
                            scenario_id=scenario_id,
                        ),
                    )
                    checks.append(
                        _response_check(
                            name=name,
                            label=f"scenario {scenario_id!r} at revision {version!r}",
                            probe=probe,
                        )
                    )

    return ValidationReport(
        base_url=base,
        checks=tuple(checks),
        workload=str(resolved_workload) if resolved_workload is not None else None,
        schema=str(resolved_schema),
    )


def _print_report(report: ValidationReport, stream: Any) -> None:
    status = "PASS" if report.ok else "FAIL"
    print("== external SUT onboarding validation ==", file=stream)
    print(f"base_url : {report.base_url}", file=stream)
    print(f"workload : {report.workload or '<not supplied>'}", file=stream)
    print(f"schema   : {report.schema}", file=stream)
    print("-" * 72, file=stream)
    for check in report.checks:
        mark = "PASS" if check.ok else "FAIL"
        print(f"  [{mark}] {check.name}: {check.detail}", file=stream)
    print("-" * 72, file=stream)
    if report.ok:
        print(f"result: PASS ({len(report.checks)} checks)", file=stream)
    else:
        print(
            f"result: FAIL ({report.passed} passed, {len(report.failures)} failed)",
            file=stream,
        )
        for check in report.failures:
            print(f"  failed: {check.name}", file=stream)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="validate-sut",
        description="Validate that an external HTTP SUT can be evaluated by EvalPilot.",
    )
    parser.add_argument("--base-url", required=True, help="SUT base URL, for example http://127.0.0.1:8020")
    parser.add_argument("--workload", help="path to a workload JSON manifest (optional)")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_SUT_TIMEOUT_SECONDS,
        help=f"per-request timeout; default {DEFAULT_SUT_TIMEOUT_SECONDS}",
    )
    parser.add_argument(
        "--schema",
        help="workload JSON Schema path; defaults to schemas/workload.schema.json",
    )
    parser.add_argument("--json-report", help="optional path for a machine-readable report")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    import sys

    args = build_parser().parse_args(argv)
    report = run_validation(
        base_url=args.base_url,
        workload_path=args.workload,
        timeout_seconds=args.timeout_seconds,
        schema_path=args.schema,
    )
    _print_report(report, sys.stdout)
    if args.json_report:
        path = Path(args.json_report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report.to_json(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"json report: {path}", file=sys.stdout)
    return 0 if report.ok else 1


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())
