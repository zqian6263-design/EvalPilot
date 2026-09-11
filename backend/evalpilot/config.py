"""Environment-backed settings.

Environment variable names are frozen by ``docs/INTERFACES.md``. Defaults are
chosen so a fresh clone runs the deterministic demo with no external service.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from evalpilot import __version__

# backend/evalpilot/config.py -> backend/ -> repository root
BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent

DEFAULT_DB_PATH = BACKEND_DIR / "data" / "evalpilot.db"


def _as_bool(raw: str | None, default: bool) -> bool:
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    db_path: Path
    artifacts_dir: Path
    llm_base_url: str | None
    llm_api_key: str | None
    llm_model: str | None
    enable_python_tool: bool
    demo_mode: bool
    step_delay: float
    version: str


def _resolve_db_path(raw: str | None) -> Path:
    if raw is None or raw.strip() == "":
        return DEFAULT_DB_PATH
    candidate = Path(raw.strip())
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    return candidate


def load_settings(env: dict[str, str] | None = None) -> Settings:
    """Build settings from ``env`` (defaults to ``os.environ``)."""
    source = os.environ if env is None else env
    db_path = _resolve_db_path(source.get("EVALPILOT_DB_PATH"))

    try:
        step_delay = float(source.get("EVALPILOT_STEP_DELAY") or "0.05")
    except ValueError:
        step_delay = 0.05

    return Settings(
        db_path=db_path,
        artifacts_dir=db_path.parent / "artifacts",
        llm_base_url=source.get("EVALPILOT_LLM_BASE_URL") or None,
        llm_api_key=source.get("EVALPILOT_LLM_API_KEY") or None,
        llm_model=source.get("EVALPILOT_LLM_MODEL") or None,
        enable_python_tool=_as_bool(source.get("EVALPILOT_ENABLE_PYTHON_TOOL"), False),
        demo_mode=_as_bool(source.get("EVALPILOT_DEMO_MODE"), True),
        step_delay=max(0.0, step_delay),
        version=__version__,
    )
