"""Browser-backed case executor for browser workloads."""

from __future__ import annotations

import json
from typing import Any

from evalpilot.clock import new_id, utc_now
from evalpilot.executor import ExecutionResult
from evalpilot.models import Evidence, TestCase
from evalpilot.tools import ToolPolicy, ToolRegistry


def _expand(value: Any, case: TestCase, intervention: str | None) -> Any:
    if isinstance(value, str):
        version = str(case.input.get("version_label") or case.version)
        return (
            value.replace("{{version}}", version)
            .replace("{{scenario_id}}", str(case.input.get("scenario_id") or ""))
            .replace("{{intervention}}", intervention or "")
        )
    if isinstance(value, dict):
        return {key: _expand(item, case, intervention) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand(item, case, intervention) for item in value]
    return value


class BrowserCaseExecutor:
    """Execute a test case whose input declares browser actions."""

    def __init__(self, *, policy: ToolPolicy, target_url: str | None) -> None:
        if not policy.allows_browser():
            raise ValueError("BrowserCaseExecutor requires browser policy access")
        self.policy = policy
        self.target_url = target_url

    def execute(self, case: TestCase, registry: ToolRegistry, db: Any, intervention: str | None = None) -> ExecutionResult:
        raw_actions = case.input.get("browser_actions")
        if not isinstance(raw_actions, list) or not raw_actions:
            raise ValueError("browser case has no browser_actions")
        target_url = str(case.input.get("browser_url") or self.target_url or "")
        if not target_url:
            raise ValueError("browser case has no target URL")
        target_url = _expand(target_url, case, intervention)
        actions = _expand(raw_actions, case, intervention)

        artifact_dir = db.run_artifact_dir(case.run_id)
        screenshot_name = f"{case.id}-{new_id()}-browser.png"
        result = registry.invoke(
            "browser_run",
            url=target_url,
            actions=actions,
            screenshot_path=str(artifact_dir / screenshot_name),
        )
        output = dict(result.output)
        answer = str(output.get("extracted", {}).get("answer") or output.get("answer") or "")
        created_at = utc_now()
        base = {"run_id": case.run_id, "test_case_id": case.id, "created_at": created_at.isoformat()}
        screenshot_relative = f"data/artifacts/{case.run_id}/{screenshot_name}"
        # The request is recorded next to the observed action trace, the same way
        # the HTTP executor records its request. Without the intervention in the
        # payload, a counterfactual replay's browser evidence is indistinguishable
        # from an ordinary execution's, so "this replay ran" could not be audited
        # from the evidence itself.
        request = {
            "url": target_url,
            "actions": actions,
            "scenario_id": case.input.get("scenario_id"),
            "version": case.input.get("version_label") or case.version,
            "intervention": intervention,
        }
        trace_uri = db.write_artifact(
            case.run_id,
            f"{case.id}-browser-trace.json",
            json.dumps({"request": request, "result": output}, ensure_ascii=False, indent=2, default=str),
        )
        evidence = [
            Evidence(id=new_id(), run_id=case.run_id, test_case_id=case.id, kind="text", uri=None, payload={"answer": answer, "final_url": output.get("final_url"), **base}, created_at=created_at),
            Evidence(id=new_id(), run_id=case.run_id, test_case_id=case.id, kind="screenshot", uri=screenshot_relative, payload={"path": screenshot_relative, **base}, created_at=created_at),
            Evidence(id=new_id(), run_id=case.run_id, test_case_id=case.id, kind="trace", uri=trace_uri, payload={"request": request, "actions": output.get("action_trace", []), "console_errors": output.get("console_errors", []), **base}, created_at=created_at),
        ]
        output.update({"scenario_id": case.input.get("scenario_id"), "version": case.input.get("version_label") or case.version, "answer": answer, "citations": [], "tool_calls": output.get("tool_calls", [])})
        return ExecutionResult(output=output, evidence=evidence)


class CompositeCaseExecutor:
    """Route browser cases to an explicit browser executor and others to a fallback."""

    def __init__(self, *, fallback: Any, browser: BrowserCaseExecutor) -> None:
        self.fallback = fallback
        self.browser = browser

    def __call__(self, case: TestCase, registry: ToolRegistry, db: Any, intervention: str | None = None) -> ExecutionResult:
        if case.input.get("browser_actions"):
            return self.browser.execute(case, registry, db, intervention)
        return self.fallback(case, registry, db, intervention)