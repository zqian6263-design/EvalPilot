"""The allowlist contract: no arbitrary code execution by default.

``CLAUDE.md`` non-negotiable #4: default execution must not run arbitrary
untrusted code; the Python tool is allowlisted and disabled unless explicitly
enabled.
"""

from __future__ import annotations

import pytest

from evalpilot.tools import ToolError, ToolRegistry, kb_search
from conftest import make_settings
from evalpilot.config import load_settings


def test_python_tool_disabled_by_default() -> None:
    registry = ToolRegistry()
    assert "python_run" not in registry.available()
    with pytest.raises(ToolError, match="disabled"):
        registry.invoke("python_run", source="print('hi')")


def test_python_tool_still_refuses_when_enabled() -> None:
    """Enabling the flag does not grant arbitrary execution in the MVP."""
    registry = ToolRegistry(enable_python=True)
    assert "python_run" in registry.available()
    with pytest.raises(ToolError):
        registry.invoke("python_run", source="print('hi')")


def test_unimplemented_tools_are_not_reachable() -> None:
    registry = ToolRegistry()
    assert "http_get" not in registry.available()
    assert "file_read" not in registry.available()
    for name in ("http_get", "file_read", "nope"):
        with pytest.raises(ToolError):
            registry.invoke(name, url="http://example.com", path="/etc/passwd")


def test_default_settings_disable_the_python_tool_and_need_no_api_key() -> None:
    settings = load_settings({})
    assert settings.enable_python_tool is False
    assert settings.demo_mode is True
    assert settings.llm_api_key is None


def test_settings_read_the_contract_environment_variables(tmp_path) -> None:
    settings = load_settings(
        {
            "EVALPILOT_DB_PATH": str(tmp_path / "custom.db"),
            "EVALPILOT_ENABLE_PYTHON_TOOL": "true",
            "EVALPILOT_DEMO_MODE": "false",
            "EVALPILOT_LLM_MODEL": "demo-model",
        }
    )
    assert settings.db_path == tmp_path / "custom.db"
    assert settings.enable_python_tool is True
    assert settings.demo_mode is False
    assert settings.llm_model == "demo-model"
    # Artifacts live beside the database, per the storage contract.
    assert settings.artifacts_dir == tmp_path / "artifacts"


def test_kb_search_tool_trace_is_recorded() -> None:
    registry = ToolRegistry()
    result = registry.invoke("kb_search", query="What is the refund window?", top_k=1)
    assert result.ok is True
    assert result.output["documents"][0]["doc_id"] == "kb-refund-policy"
    assert registry.calls and registry.calls[0]["tool"] == "kb_search"


def test_kb_search_is_deterministic() -> None:
    first = kb_search("How long does shipping take?", top_k=2)
    second = kb_search("How long does shipping take?", top_k=2)
    assert first.output == second.output


def test_settings_accept_a_temporary_step_delay(tmp_path) -> None:
    settings = make_settings(tmp_path, step_delay=0.1)
    assert settings.step_delay == 0.1
