"""Environment-backed settings.

Environment variable names are frozen by ``docs/INTERFACES.md``. Defaults are
chosen so a fresh clone runs the deterministic demo with no external service.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# backend/evalpilot/config.py -> backend/ -> repository root
BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent

DEFAULT_DB_PATH = BACKEND_DIR / "data" / "evalpilot.db"


def _as_bool(raw: str | None, default: bool) -> bool:
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


#: Default per-request LLM timeout in seconds, per ``docs/V3_LLM_INTERFACES.md``.
DEFAULT_LLM_TIMEOUT_SECONDS = 45.0
DEFAULT_SUT_TIMEOUT_SECONDS = 20.0

#: The two modes the contract names.
_LLM_MODES = ("deterministic", "live")


@dataclass(frozen=True)
class Settings:
    # The first four fields have no default: every caller must state its
    # storage location explicitly. Everything after them does, so a new setting
    # is additive and cannot break an existing positional constructor.
    db_path: Path
    artifacts_dir: Path
    llm_base_url: str | None
    llm_api_key: str | None
    llm_model: str | None
    enable_python_tool: bool = False
    demo_mode: bool = True
    step_delay: float = 0.05
    version: str = "0.1.0"
    #: ``deterministic`` (default, offline) or ``live``. An unrecognized value
    #: is carried through as-is; ``evalpilot.llm.runtime`` reports it and runs
    #: deterministically rather than guessing what was meant.
    llm_mode: str = "deterministic"
    llm_timeout_seconds: float = DEFAULT_LLM_TIMEOUT_SECONDS
    judge_max_calls: int | None = None
    judge_max_tokens: int | None = None
    sut_url: str | None = None
    sut_timeout_seconds: float = DEFAULT_SUT_TIMEOUT_SECONDS
    sut_offline: bool = False
    sut_cache_dir: Path | None = None
    sut_discover_capabilities: bool = True
    github_webhook_secret: str | None = None
    github_token: str | None = None
    github_api_url: str = "https://api.github.com"
    browser_enabled: bool = False
    browser_target_url: str | None = None
    browser_allowed_hosts: tuple[str, ...] = ()
    browser_screenshot_dir: Path | None = None
    browser_timeout_seconds: float = 30.0
    browser_executable_path: str | None = None
    browser_headless: bool = True


def _resolve_db_path(raw: str | None) -> Path:
    if raw is None or raw.strip() == "":
        return DEFAULT_DB_PATH
    candidate = Path(raw.strip())
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    return candidate


def _resolve_llm_mode(raw: str | None) -> str:
    """The configured mode, normalized. Unknown values are passed through."""
    value = (raw or "").strip().lower()
    return value or "deterministic"


def _resolve_positive_float(raw: str | None, default: float) -> float:
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _resolve_optional_positive_int(raw: str | None) -> int | None:
    if raw is None or raw.strip() == "":
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def _resolve_optional_path(raw: str | None, default: Path) -> Path:
    value = (raw or "").strip()
    if not value:
        return default
    candidate = Path(value)
    return candidate if candidate.is_absolute() else REPO_ROOT / candidate


def _resolve_llm_timeout(raw: str | None) -> float:
    """The configured timeout, falling back to the default when unusable.

    A non-numeric or non-positive value is not silently clamped: it is
    replaced by the default here, and ``evalpilot.llm.runtime`` treats a
    non-positive *timeout* as a configuration error, so a mistyped value
    cannot quietly become "no timeout".
    """
    if raw is None or raw.strip() == "":
        return DEFAULT_LLM_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_LLM_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_LLM_TIMEOUT_SECONDS


def load_settings(env: dict[str, str] | None = None) -> Settings:
    """Build settings from ``env`` (defaults to ``os.environ``)."""
    from evalpilot import __version__

    source = os.environ if env is None else env
    db_path = _resolve_db_path(source.get("EVALPILOT_DB_PATH"))

    try:
        step_delay = float(source.get("EVALPILOT_STEP_DELAY") or "0.05")
    except ValueError:
        step_delay = 0.05

    artifacts_dir = db_path.parent / "artifacts"
    browser_target_url = (source.get("EVALPILOT_BROWSER_TARGET_URL") or "").strip() or None
    browser_allowed_hosts = tuple(
        host.strip().lower()
        for host in (source.get("EVALPILOT_BROWSER_ALLOWED_HOSTS") or "").split(",")
        if host.strip()
    )
    if not browser_allowed_hosts and browser_target_url:
        host = urlsplit(browser_target_url).hostname
        if host:
            browser_allowed_hosts = (host.lower(),)

    return Settings(
        db_path=db_path,
        artifacts_dir=artifacts_dir,
        llm_base_url=source.get("EVALPILOT_LLM_BASE_URL") or None,
        llm_api_key=source.get("EVALPILOT_LLM_API_KEY") or None,
        llm_model=source.get("EVALPILOT_LLM_MODEL") or None,
        enable_python_tool=_as_bool(source.get("EVALPILOT_ENABLE_PYTHON_TOOL"), False),
        demo_mode=_as_bool(source.get("EVALPILOT_DEMO_MODE"), True),
        step_delay=max(0.0, step_delay),
        version=__version__,
        llm_mode=_resolve_llm_mode(source.get("EVALPILOT_LLM_MODE")),
        llm_timeout_seconds=_resolve_llm_timeout(
            source.get("EVALPILOT_LLM_TIMEOUT_SECONDS")
        ),
        judge_max_calls=_resolve_optional_positive_int(
            source.get("EVALPILOT_JUDGE_MAX_CALLS")
        ),
        judge_max_tokens=_resolve_optional_positive_int(
            source.get("EVALPILOT_JUDGE_MAX_TOKENS")
        ),
        sut_url=(source.get("EVALPILOT_SUT_URL") or "").strip() or None,
        sut_timeout_seconds=_resolve_positive_float(
            source.get("EVALPILOT_SUT_TIMEOUT_SECONDS"), DEFAULT_SUT_TIMEOUT_SECONDS
        ),
        sut_offline=_as_bool(source.get("EVALPILOT_SUT_OFFLINE"), False),
        sut_discover_capabilities=_as_bool(
            source.get("EVALPILOT_SUT_DISCOVERY"), True
        ),
        sut_cache_dir=_resolve_optional_path(
            source.get("EVALPILOT_SUT_CACHE_DIR"),
            db_path.parent / "sut-cache",
        ),
        github_webhook_secret=source.get("EVALPILOT_GITHUB_WEBHOOK_SECRET") or None,
        github_token=source.get("EVALPILOT_GITHUB_TOKEN") or None,
        github_api_url=(
            source.get("EVALPILOT_GITHUB_API_URL") or "https://api.github.com"
        ).rstrip("/"),
        browser_enabled=_as_bool(source.get("EVALPILOT_BROWSER_ENABLED"), False),
        browser_target_url=browser_target_url,
        browser_allowed_hosts=browser_allowed_hosts,
        browser_screenshot_dir=_resolve_optional_path(
            source.get("EVALPILOT_BROWSER_SCREENSHOT_DIR"),
            artifacts_dir,
        ),
        browser_timeout_seconds=_resolve_positive_float(
            source.get("EVALPILOT_BROWSER_TIMEOUT_SECONDS"), 30.0
        ),
        browser_executable_path=(source.get("EVALPILOT_BROWSER_EXECUTABLE") or "").strip() or None,
        browser_headless=_as_bool(source.get("EVALPILOT_BROWSER_HEADLESS"), True),
    )
