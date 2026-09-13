"""Application container: the resolved set of collaborators the routes use.

Lives in its own module so route modules and :mod:`evalpilot.app` can both
import it without a circular dependency.
"""

from __future__ import annotations

from dataclasses import dataclass

from evalpilot.config import Settings, load_settings
from evalpilot.db import Database
from evalpilot.evaluation.judge import RubricJudge
from evalpilot.investigation import InvestigationService
from evalpilot.investigation.engine_provider import EngineCounterfactualProvider
from evalpilot.llm.judge_adapter import build_judge_callable
from evalpilot.llm.runtime import LLMRuntime, build_runtime
from evalpilot.memory import seed_incidents
from evalpilot.orchestration_eval.service import EvaluationService
from evalpilot.repository import Repository
from evalpilot.runner import RunRunner
from evalpilot.sut import HttpCaseExecutor
from evalpilot.tools import ToolPolicy, ToolRegistry


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
    #: The registered tool set, so `GET /api/runtime` reports what the process
    #: can actually do rather than a hard-coded list.
    tools: ToolRegistry
    #: Resolved LLM mode. `deterministic` by default; `live` installs a
    #: provider into the investigation and the judge seam.
    llm_runtime: LLMRuntime


def build_container(settings: Settings | None = None) -> Container:
    resolved = settings or load_settings()
    llm_runtime = build_runtime(resolved)
    db = Database(resolved.db_path, resolved.artifacts_dir)
    db.initialize()
    repo = Repository(db)
    tools = ToolRegistry(
        enable_python=resolved.enable_python_tool,
        policy=ToolPolicy(
            http_allowed_hosts=("127.0.0.1",),
            file_read_roots=(resolved.artifacts_dir.resolve(),),
        ),
    )
    # The incident history is fixture data, so it is seeded on every build.
    # `seed_incidents` is idempotent, which is what makes that safe.
    seed_incidents(repo)
    # Defaults (no judge, fixed seed at the dataclass defaults) keep the demo
    # reproducible and offline; the runner takes the service as a seam.
    #
    # The judge seam is populated only in live mode. In deterministic mode
    # `build_judge_callable` returns None and no judge is installed at all, so
    # the offline path is byte-for-byte what it was before this package
    # existed. Run evaluation passes question text and the judge rubric into
    # the engine; investigation intake explicitly disables judge re-scoring.
    judge_callable = build_judge_callable(llm_runtime)
    evaluation_service = EvaluationService(
        judge=RubricJudge(judge_callable) if judge_callable is not None else None,
        max_judge_calls=resolved.judge_max_calls,
        max_judge_tokens=resolved.judge_max_tokens,
    )
    case_executor = None
    if resolved.sut_url:
        case_executor = HttpCaseExecutor(
            base_url=resolved.sut_url,
            timeout_seconds=resolved.sut_timeout_seconds,
            offline=resolved.sut_offline,
            cache_dir=resolved.sut_cache_dir,
            discover_capabilities=resolved.sut_discover_capabilities,
        ).execute
    runner = RunRunner(
        repo,
        db,
        resolved,
        evaluation_service,
        case_executor=case_executor,
    )
    investigation_runner = InvestigationService(
        repo,
        settings=resolved,
        evaluation_service=evaluation_service,
        provider=EngineCounterfactualProvider(repo=repo, executor=case_executor),
        llm_runtime=llm_runtime,
    )
    return Container(
        settings=resolved,
        db=db,
        repo=repo,
        runner=runner,
        investigation_runner=investigation_runner,
        tools=tools,
        llm_runtime=llm_runtime,
    )


def use_llm_runtime(container: "Container", runtime: LLMRuntime) -> LLMRuntime:
    """Install ``runtime`` as *the* LLM runtime for the whole container.

    There is exactly one runtime object per container, and both the service
    that consults the model and ``GET /api/runtime`` read it. Swapping it in
    one place only would let the status endpoint report a mode the
    investigation is not actually using, which is precisely the kind of
    dishonesty this endpoint exists to prevent.
    """
    container.llm_runtime = runtime
    container.investigation_runner.llm_runtime = runtime
    return runtime
