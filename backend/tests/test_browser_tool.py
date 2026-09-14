from __future__ import annotations

from pathlib import Path

import pytest

from evalpilot.db import Database
from evalpilot.executor import ExecutionResult
from evalpilot.models import TestCase as DomainTestCase
from evalpilot.sut.browser_executor import BrowserCaseExecutor, CompositeCaseExecutor
from evalpilot.tools import ToolError, ToolPolicy, ToolRegistry, ToolResult


class FakeRegistry:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def invoke(self, name: str, **kwargs):
        self.calls.append({"name": name, **kwargs})
        return ToolResult(
            name=name,
            ok=True,
            output={
                "answer": "owner_visible=true; foreign_visible=false",
                "extracted": {"answer": "owner_visible=true; foreign_visible=false"},
                "final_url": kwargs["url"],
                "action_trace": kwargs["actions"],
                "console_errors": [],
                "tool_calls": [f"browser.{item['action']}" for item in kwargs["actions"]],
            },
            trace={"tool": name, "outcome": "completed"},
        )


def _case(*, browser: bool = True) -> DomainTestCase:
    extra = {
        "browser_url": "http://127.0.0.1:8120/?version={{version}}&intervention={{intervention}}",
        "browser_actions": [
            {"action": "select", "selector": "#scenario", "value": "{{scenario_id}}"},
            {"action": "click", "selector": "#run"},
            {"action": "extract_text", "selector": "#result", "name": "answer"},
        ],
    } if browser else {}
    return DomainTestCase(
        id="case-1",
        run_id="run-1",
        title="browser case",
        category="adversarial",
        input={
            "scenario_id": "tenant-metadata-overwrite",
            "question": "Can metadata move the memory?",
            "version_label": "mem0ai-3.1.0",
            **extra,
        },
        expected={"must_include": ["owner_visible=true"]},
        difficulty=0.8,
        status="running",
        version="candidate",
        output=None,
    )


def test_browser_tool_is_disabled_by_default() -> None:
    registry = ToolRegistry()
    assert "browser_run" not in registry.available()
    with pytest.raises(ToolError, match="disabled"):
        registry.invoke("browser_run", url="http://127.0.0.1/", actions=[], screenshot_path="x.png")


def test_browser_policy_requires_enabled_and_host(tmp_path: Path) -> None:
    assert not ToolPolicy(browser_screenshot_root=tmp_path).allows_browser()
    assert not ToolPolicy(browser_enabled=True, browser_screenshot_root=tmp_path).allows_browser()
    assert ToolPolicy(browser_enabled=True, browser_allowed_hosts=("127.0.0.1",), browser_screenshot_root=tmp_path).allows_browser()


def test_browser_case_executor_expands_templates_and_persists_evidence(tmp_path: Path) -> None:
    db = Database(tmp_path / "browser.db", tmp_path / "artifacts")
    db.initialize()
    policy = ToolPolicy(browser_enabled=True, browser_allowed_hosts=("127.0.0.1",), browser_screenshot_root=db.artifacts_dir)
    registry = FakeRegistry()
    executor = BrowserCaseExecutor(policy=policy, target_url="http://127.0.0.1:8120/")

    result = executor.execute(_case(), registry, db, "identity_metadata_stripped")

    assert result.output["answer"] == "owner_visible=true; foreign_visible=false"
    assert result.output["version"] == "mem0ai-3.1.0"
    assert registry.calls[0]["url"].endswith("version=mem0ai-3.1.0&intervention=identity_metadata_stripped")
    assert {item.kind for item in result.evidence} == {"text", "screenshot", "trace"}


def test_composite_executor_routes_non_browser_cases_to_fallback(tmp_path: Path) -> None:
    db = Database(tmp_path / "composite.db", tmp_path / "artifacts")
    db.initialize()
    policy = ToolPolicy(browser_enabled=True, browser_allowed_hosts=("127.0.0.1",), browser_screenshot_root=db.artifacts_dir)
    browser = BrowserCaseExecutor(policy=policy, target_url="http://127.0.0.1:8120/")
    fallback_called: list[str] = []

    def fallback_executor(case, registry, db, intervention=None):
        fallback_called.append(case.id)
        return ExecutionResult(output={"answer": "fallback"}, evidence=[])

    composite = CompositeCaseExecutor(fallback=fallback_executor, browser=browser)
    result = composite(_case(browser=False), FakeRegistry(), db)

    assert result.output["answer"] == "fallback"
    assert fallback_called == ["case-1"]