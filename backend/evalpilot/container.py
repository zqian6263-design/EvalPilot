"""Application container: the resolved set of collaborators the routes use.

Lives in its own module so route modules and :mod:`evalpilot.app` can both
import it without a circular dependency.
"""

from __future__ import annotations

from dataclasses import dataclass

from evalpilot.config import Settings, load_settings
from evalpilot.db import Database
from evalpilot.orchestration_eval.service import EvaluationService
from evalpilot.repository import Repository
from evalpilot.runner import RunRunner


@dataclass
class Container:
    settings: Settings
    db: Database
    repo: Repository
    runner: RunRunner


def build_container(settings: Settings | None = None) -> Container:
    resolved = settings or load_settings()
    db = Database(resolved.db_path, resolved.artifacts_dir)
    db.initialize()
    repo = Repository(db)
    # Defaults (no judge, fixed seed at the dataclass defaults) keep the demo
    # reproducible and offline; the runner takes the service as a seam.
    runner = RunRunner(repo, db, resolved, EvaluationService())
    return Container(settings=resolved, db=db, repo=repo, runner=runner)

