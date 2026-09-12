"""Deterministic demo fixture metadata and (explicit) seeding.

``GET /demo/seed`` is contractually side-effect free, so :func:`demo_metadata`
only *describes* the demo. The side-effecting :func:`ensure_demo_project` is
used by ``python -m evalpilot.cli seed`` and by tests, never by the read
endpoint.

``GET /demo/investigation`` follows the same rule: it reports where the
investigation workspace currently stands and what it is made of, and never
creates one.
"""

from __future__ import annotations

from typing import Any

from evalpilot.config import Settings
from evalpilot.fixtures import SUPPORT_SCENARIOS, SupportScenario
from evalpilot.memory import incident_metadata
from evalpilot.models import Project, Run, RunStatus
from evalpilot.repository import Repository

DEMO_PROJECT_NAME = "Enterprise Knowledge Base QA"
DEMO_SCENARIO = "kb-qa"
DEMO_BASELINE_VERSION = "v1.0-baseline"
DEMO_CANDIDATE_VERSION = "v1.1-candidate"
DEMO_SEED = 20260919
#: Every golden scenario. The demo compares matched case *means* with a paired
#: bootstrap, so the number of matched cases directly sets how small a change
#: the demo can resolve. Running a subset would leave a real regression
#: inconclusive for lack of power rather than for lack of effect.
DEMO_CASE_COUNT = len(SUPPORT_SCENARIOS)

# The first DEMO_CASE_COUNT scenarios are the demo's fixture set.
DEMO_SCENARIOS: tuple[SupportScenario, ...] = SUPPORT_SCENARIOS[:DEMO_CASE_COUNT]


def _defect(scenario: SupportScenario) -> dict[str, Any] | None:
    if scenario.candidate_drops:
        return {
            "kind": "dropped_required_content",
            "detail": list(scenario.candidate_drops),
        }
    if scenario.candidate_leaks:
        return {
            "kind": "disclosed_forbidden_content",
            "detail": list(scenario.candidate_leaks),
        }
    return None


def scripted_regressions() -> list[str]:
    """Scenarios the candidate version is deliberately built to fail."""
    return [
        scenario.scenario_id
        for scenario in DEMO_SCENARIOS
        if _defect(scenario) is not None
    ]


def demo_metadata() -> dict[str, Any]:
    """Pure description of the seeded demo. No database access, no side effects."""
    by_category: dict[str, int] = {}
    for scenario in DEMO_SCENARIOS:
        by_category[scenario.category] = by_category.get(scenario.category, 0) + 1

    return {
        "scenario": DEMO_SCENARIO,
        "project": {"name": DEMO_PROJECT_NAME, "scenario": DEMO_SCENARIO},
        "baseline_version": DEMO_BASELINE_VERSION,
        "candidate_version": DEMO_CANDIDATE_VERSION,
        "seed": DEMO_SEED,
        "case_count": DEMO_CASE_COUNT,
        "deterministic": True,
        "external_services_required": [],
        "case_categories": by_category,
        "scenarios": [
            {
                "scenario_id": scenario.scenario_id,
                "category": scenario.category,
                "difficulty": scenario.difficulty,
                "question": scenario.question,
                "expected_doc_ids": list(scenario.expected_doc_ids),
                "expects_refusal": scenario.expects_refusal,
            }
            for scenario in DEMO_SCENARIOS
        ],
        "scripted_regressions": scripted_regressions(),
        "defects": {
            scenario.scenario_id: _defect(scenario)
            for scenario in DEMO_SCENARIOS
            if _defect(scenario) is not None
        },
        "how_to_run": [
            "python -m evalpilot.cli seed",
            "POST /api/runs with the returned project_id, then POST /api/runs/{id}/start",
        ],
    }


def find_demo_project(repo: Repository) -> Project | None:
    for project in repo.list_projects():
        if project.name == DEMO_PROJECT_NAME:
            return project
    return None


#: The deterministic lifecycle the investigation workspace renders. Fixed text,
#: not a prediction: it describes the phases the engine actually runs.
INVESTIGATION_STEPS: tuple[dict[str, str], ...] = (
    {"key": "risk", "title": "Risk hypotheses from the run's evidence"},
    {"key": "memory", "title": "Recall the seeded incident history"},
    {"key": "probe", "title": "Follow-up probe for every regressed scenario"},
    {"key": "counterfactual", "title": "Counterfactual replay per critical finding"},
    {"key": "decision", "title": "Release decision"},
    {"key": "report", "title": "Exportable Markdown report with evidence citations"},
)


def investigation_metadata(repo: Repository) -> dict[str, Any]:
    """Describe the investigation workspace. Read-only, no side effects.

    Reports the most recent completed demo run as the entry point when one
    exists, and otherwise says the workspace is waiting for a run. It never
    seeds a project, starts a run, or creates an investigation.
    """
    project = find_demo_project(repo)
    entry: Run | None = None
    if project is not None:
        for run in repo.list_runs():
            if (
                run.project_id == project.id
                and run.baseline_version == DEMO_BASELINE_VERSION
                and run.candidate_version == DEMO_CANDIDATE_VERSION
                and run.status in (RunStatus.COMPLETED, RunStatus.QUEUED)
            ):
                entry = run
                break

    investigation = (
        repo.find_investigation_for_run(entry.id) if entry is not None else None
    )
    seeded = repo.list_historical_incidents()

    return {
        "entry_run_id": entry.id if entry else None,
        "run_status": entry.status.value if entry else None,
        "investigation_id": investigation.id if investigation else None,
        "investigation_status": (
            investigation.status.value if investigation else None
        ),
        "incident_count": len(seeded),
        "interventions": sorted(
            {
                incident.intervention
                for incident in seeded
                if incident.intervention is not None
            }
        ),
        "incidents": incident_metadata()["incidents"],
        "steps": [dict(step) for step in INVESTIGATION_STEPS],
        "how_to_run": [
            "POST /api/investigations with the entry_run_id and an objective",
            "POST /api/investigations/{id}/start",
            "GET /api/investigations/{id} or /api/investigations/{id}/events",
            "GET /api/investigations/{id}/report.md",
        ],
    }


def ensure_demo_project(
    repo: Repository, settings: Settings
) -> tuple[Project, Run | None]:
    """Idempotently create the demo project and its seeded run.

    Returns the project and the most recent demo run, if one already existed
    with the exact demo configuration. A rerun creates a fresh run rather than
    mutating a previous one, so results stay reproducible and auditable.
    """
    project = find_demo_project(repo)
    if project is None:
        project = repo.create_project(DEMO_PROJECT_NAME, DEMO_SCENARIO)

    run: Run | None = None
    for existing in repo.list_runs():
        if (
            existing.project_id == project.id
            and existing.baseline_version == DEMO_BASELINE_VERSION
            and existing.candidate_version == DEMO_CANDIDATE_VERSION
            and existing.case_count == DEMO_CASE_COUNT
        ):
            run = existing
            break

    if run is None:
        run = repo.create_run(
            project_id=project.id,
            baseline_version=DEMO_BASELINE_VERSION,
            candidate_version=DEMO_CANDIDATE_VERSION,
            seed=DEMO_SEED,
            case_count=DEMO_CASE_COUNT,
        )
    return project, run
