"""Application container: the resolved set of collaborators the routes use.

Lives in its own module so route modules and :mod:`evalpilot.app` can both
import it without a circular dependency.
"""

from __future__ import annotations

from dataclasses import dataclass

from evalpilot.config import Settings, load_settings
from evalpilot.db import Database
from evalpilot.investigation import InvestigationService
from evalpilot.memory import seed_incidents
from evalpilot.orchestration_eval.service import EvaluationService
from evalpilot.repository import Repository
from evalpilot.runner import RunRunner


@dataclass
class Container:
    settings: Settings
    db: Database
    repo: Repository
    runner: RunRunner
    #: Autonomous investigation (V2). Built here rather than in the route so
    #: the counterfactual provider can be swapped for the dedicated engine at
    #: one place: `Container.investigation_runner.provider`.
    investigation_runner: InvestigationService


def build_container(settings: Settings | None = None) -> Container:
    resolved = settings or load_settings()
    db = Database(resolved.db_path, resolved.artifacts_dir)
    db.initialize()
    repo = Repository(db)
    # The incident history is fixture data, so it is seeded on every build.
    # `seed_incidents` is idempotent, which is what makes that safe.
    seed_incidents(repo)
    # Defaults (no judge, fixed seed at the dataclass defaults) keep the demo
    # reproducible and offline; the runner takes the service as a seam.
    evaluation_service = EvaluationService()
    runner = RunRunner(repo, db, resolved, evaluation_service)
    investigation_runner = InvestigationService(
        repo, settings=resolved, evaluation_service=evaluation_service
    )
    return Container(
        settings=resolved,
        db=db,
        repo=repo,
        runner=runner,
        investigation_runner=investigation_runner,
    )
