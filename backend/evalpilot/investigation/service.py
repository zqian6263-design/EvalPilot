"""The autonomous investigation engine.

Given a finished regression run, this drives the sequence the product promises::

    objective -> risk hypotheses -> recalled incidents -> follow-up probes
              -> counterfactual replay -> root cause -> release decision
              -> exportable evidence report

Everything it produces is deterministic and offline. The per-scenario scores
come from the same evaluation boundary the run itself used
(:class:`~evalpilot.orchestration_eval.service.EvaluationService`), so a
hypothesis in an investigation report cannot disagree with the run report it was
derived from. The replay step goes through
:class:`~evalpilot.investigation.providers.CounterfactualProvider`, whose default
implementation is the explicit offline fallback documented in that module.

Three rules shape the engine:

**No claim without a citation.** Every risk hypothesis, probe, experiment and
blocking finding carries evidence ids that already exist in the run's evidence
table. :func:`_require_evidence` fails the investigation rather than persisting a
claim that cannot be traced to the exact input, output and tool trace.

**Nothing is attributed to a mechanism the run does not support.** A scenario is
only linked to an intervention when the failure the run recorded is one that
intervention would repair. That is why a disclosed credential and a dropped
clause end up with different root causes instead of one blanket "revert the
candidate".

**No private reasoning.** Steps are structured actions and observations -- what
was checked, what was found, which evidence supports it. No chain of thought is
persisted anywhere.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from evalpilot import __version__
from evalpilot.clock import new_id, utc_now
from evalpilot.engine_mapping import to_expected_behavior
from evalpilot.memory import match_incidents, search_terms
from evalpilot.memory.retrieval import confidence_for
from evalpilot.models import (
    CounterfactualExperiment,
    EventType,
    Evidence,
    Finding,
    HistoricalIncident,
    Investigation,
    InvestigationStatus,
    InvestigationStep,
    InvestigationStepKind,
    MemoryMatch,
    ReleaseDecision,
    Report,
    Run,
    StepStatus,
    TestCase,
)
from evalpilot.orchestration_eval.service import CaseVerdict, EvaluationService
from evalpilot.repository import NotFoundError, Repository
from evalpilot.tools import ToolError, ToolPolicy, ToolRegistry

from .providers import (
    CounterfactualProvider,
    CounterfactualRequest,
    DeterministicProvider,
)

#: Stable step titles. The UI groups on them.
ROOT_TITLE = "Release investigation"
OBJECTIVE_TITLE = "Objective"
OBSERVATION_TITLE = "Run observation"
TOOL_TITLE = "Reference corpus cross-check"
MEMORY_TITLE = "Recalled incident history"
COUNTERFACTUAL_TITLE = "Counterfactual replay"
COUNTERFACTUAL_RESULTS_TITLE = "Counterfactual results"
DECISION_TITLE = "Release decision"

#: The read tool the investigation uses to cross-check its own claims against
#: the run's persisted trace artifacts. The tool's read root is the artifacts
#: directory and no HTTP host is allowed, so the cross-check can read files and
#: can never open a socket -- the investigation must stay reproducible offline
#: (``docs/V2_INTERFACES.md``).
_INVESTIGATION_TOOL_HOSTS: tuple[str, ...] = ()
#: Name for the artifacts directory when it has no usable basename.
_TOOL_ROOT_SENTINEL = "run artifacts"

#: A candidate genuinely regressed here rather than drifting.
_REGRESSION_EPSILON = 1e-9

#: Output caps. The report is a summary of the run, not a dump of it.
MAX_BLOCKING_FINDINGS = 8
#: How many run trace artifacts the reference cross-check opens. The corpus is a
#: sample of the run's persisted tool traces, so the claim it supports is about
#: the sample and the step says how many rows it read.
MAX_REFERENCE_ARTIFACTS = 24

#: Recommendations. Deliberately specific: every demo regression is a clause
#: loss, and a generic "fix the candidate" would be useless at a release gate.
PRIMARY_HYPOTHESIS_TITLE = "the summarization step drops mandatory clauses"
PRIMARY_HYPOTHESIS_KIND = "compression_step"
REGRESSION_RECOMMENDATION = (
    "Hold the candidate and keep v1.0-baseline as the release version until the "
    "summarization/compression step preserves mandatory escalation, safety and "
    "security clauses, then re-run this investigation."
)
REGRESSION_INVESTIGATE_ACTION = (
    "Review the candidate's summarization/compression change against the failing "
    "scenarios named in this report before any release."
)
DISCLOSURE_RECOMMENDATION = (
    "Treat credential disclosure as a release blocker on its own: restore the "
    "refusal and credential guard, and re-run the adversarial scenarios before the "
    "candidate is considered for release."
)
ADVISORY_RECOMMENDATION = (
    "Triage the scenarios that fail on both versions separately; they are not "
    "caused by this change, but until they pass somewhere they cannot act as "
    "regression controls."
)
ALLOW_RECOMMENDATION = (
    "No blocking regression was found in this run. Archive this report with the "
    "release record."
)

#: Domain keys used to group scenarios, and the vocabulary that assigns them.
_DOMAINS: tuple[str, ...] = ("escalation", "safety", "security", "billing", "returns")

_DOMAIN_PHRASES: dict[str, tuple[str, ...]] = {
    "escalation": ("escalat", "human agent", "help center"),
    "safety": ("safety", "battery", "hotline", "emergency", "unplug", "hazard"),
    "security": ("password", "credential", "security", "privacy", "injection"),
    "billing": ("billing", "invoice", "tax", "charge", "receipt"),
    "returns": ("refund", "return", "shipping", "warranty", "delivery"),
}

#: The first hypothesis of the deterministic demo. The candidate's own change is
#: a summarization/compression step, so the investigation starts from the
#: objective's stated change rather than waiting to be told by memory what the
#: mechanism was.
PRIMARY_HYPOTHESIS_TITLE = "the summarization step drops mandatory clauses"
PRIMARY_HYPOTHESIS_KIND = "compression_step"

#: Order the domain hypotheses are formed in. Triage order, not severity order:
#: a customer acting on a safety answer is the highest-consequence case, so it
#: is stated first even though every domain here is blocking.
HYPOTHESIS_DOMAIN_ORDER: tuple[str, ...] = ("safety", "security", "escalation")

#: Which intervention each guarded scenario exists to catch. A recalled incident
#: supplies the hypothesis through its own ``intervention`` field; this constant
#: is only the fallback for a regression on a scenario no incident guards.
_GUARD_INTERVENTIONS: dict[str, str] = {
    "escalation-path": "compression_disabled",
    "escalation-timeframe": "compression_disabled",
    "escalation-channel": "compression_disabled",
    "urgent-safety": "compression_disabled",
    "battery-handling": "compression_disabled",
    "safety-reporting": "compression_disabled",
    "security-password-request": "security_guard_enabled",
    "prompt-injection-password": "security_guard_enabled",
}


class InvestigationError(RuntimeError):
    """Raised when an investigation cannot be carried out."""


@dataclass
class ReferenceReading:
    """What the investigation's one real tool observation read.

    Built only from artifacts that were actually opened, so an empty reading
    (``checked == 0``) is the honest result of a run whose artifacts are absent
    and is never reported as a successful cross-check.
    """

    root: str
    available_trace_artifacts: int
    sampled: int
    checked: int = 0
    controls: int = 0
    tool_calls: dict[str, int] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)

    def record(self, tool: str) -> None:
        self.tool_calls[tool] = self.tool_calls.get(tool, 0) + 1

    def matches_disclaimer_family(self, expected: str) -> bool:
        """Does a persisted trace name a tool from the same family as ``expected``?

        The reference corpus is the run's ``kb_search`` traces, so the tool that
        answers a ``kb_search``-backed claim is ``kb_search`` itself, matched on
        its leading segment rather than on the exact demo name.
        """
        family = expected.split("_", 1)[0].lower()
        return any(name.split("_", 1)[0].lower() == family for name in self.tool_calls)


@dataclass(frozen=True)
class ScenarioFinding:
    """One matched scenario as the investigation sees it.

    Built from the evaluation engine's verdict plus the declared expectations on
    the case rows. Keeping both means the scores agree with the run report by
    construction while ``missing_facts`` and ``leaked_markers`` are the declared
    markers themselves rather than a re-derivation of the score.
    """

    scenario_id: str
    category: str
    question: str
    baseline_score: float
    candidate_score: float
    delta: float
    failed_checks: tuple[str, ...]
    missing_facts: tuple[str, ...]
    leaked_markers: tuple[str, ...]
    refusal_required: bool
    baseline_case_id: str
    candidate_case_id: str
    baseline_evidence: tuple[str, ...]
    candidate_evidence: tuple[str, ...]

    @property
    def regressed(self) -> bool:
        return self.delta < -_REGRESSION_EPSILON

    @property
    def failing(self) -> bool:
        return self.candidate_score < 1.0

    @property
    def hard_failure(self) -> bool:
        """The candidate breached an expectation the scenario explicitly asserts.

        Deliberately keyed on the *declared markers*, not on the score. A
        scenario that answered without a phrase its expectation names in
        ``must_include`` -- or that surfaced one its expectation names in
        ``must_avoid`` -- has failed the thing the case exists to check, however
        much of the rest of the answer survived. Scoring 0.5 because one of two
        required facts was dropped is a hard failure of a mandatory clause, not
        a partial success: on a safety answer, the missing half is the part the
        customer needed.
        """
        return self.regressed and bool(self.missing_facts or self.leaked_markers)

    @property
    def hypothesis_kind(self) -> str | None:
        if not self.regressed:
            return None
        return "credential_disclosure" if self.leaked_markers else "dropped_clause"

    @property
    def domains(self) -> tuple[str, ...]:
        haystack = f"{self.scenario_id} {self.question}".lower()
        found = [
            domain
            for domain in _DOMAINS
            if any(phrase in haystack for phrase in _DOMAIN_PHRASES[domain])
        ]
        return tuple(found) or ("general",)

    def regression_evidence(self) -> list[str]:
        """The rows that prove this scenario moved: both versions, baseline first.

        Both arms are cited on purpose. A drop is a comparison, so the evidence
        for it is the pair -- the baseline answer that had the clause and the
        candidate answer that lost it -- not the candidate alone.
        """
        return [*self.baseline_evidence, *self.candidate_evidence]


@dataclass(frozen=True)
class RunIntake:
    """Everything the investigation reads about one run, read exactly once."""

    run: Run
    report: Report
    run_findings: list[Finding]
    scenarios: list[ScenarioFinding]
    matched_scenarios: int
    baseline_pass_rate: float
    candidate_pass_rate: float
    direction: str
    confidence: float
    #: Every evidence row for the run, keyed by id. The reference cross-check
    #: resolves artifact locators through it rather than re-reading the table.
    evidence_index: dict[str, Evidence] = field(default_factory=dict)

    @property
    def regressed(self) -> list[ScenarioFinding]:
        return [item for item in self.scenarios if item.regressed]

    @property
    def dropped_clause(self) -> list[ScenarioFinding]:
        return [
            item for item in self.scenarios if item.regressed and not item.leaked_markers
        ]

    @property
    def disclosed(self) -> list[ScenarioFinding]:
        return [item for item in self.scenarios if item.regressed and item.leaked_markers]

    @property
    def failing(self) -> list[ScenarioFinding]:
        return [item for item in self.scenarios if item.failing]

    @property
    def advisory(self) -> list[ScenarioFinding]:
        """Scenarios that fail on the candidate but did not move.

        Not this change's fault, so nothing is attributed to them -- but they
        still cannot act as regression controls, and a reader counting controls
        needs to know that.
        """
        return [item for item in self.scenarios if item.failing and not item.regressed]


@dataclass
class InvestigationOutcome:
    """What one completed investigation produced."""

    investigation: Investigation
    steps: list[InvestigationStep]
    memory_matches: list[MemoryMatch]
    counterfactuals: list[CounterfactualExperiment]
    decision: ReleaseDecision


@dataclass
class _Recorder:
    """Allocates step sequence numbers, writes steps through, keeps the order.

    A step is tracked the moment it is created -- including one that starts in
    ``running`` and is closed later -- so ``sequence`` is always the step's index
    in this list and two steps can never claim the same number.
    """

    repo: Repository
    investigation_id: str
    steps: list[InvestigationStep] = field(default_factory=list)

    def open(
        self,
        kind: InvestigationStepKind,
        title: str,
        detail: str,
        *,
        data: dict[str, Any] | None = None,
        evidence_ids: Sequence[str] = (),
        parent_id: str | None = None,
        status: StepStatus = StepStatus.RUNNING,
    ) -> InvestigationStep:
        step = InvestigationStep(
            id=new_id(),
            investigation_id=self.investigation_id,
            parent_id=parent_id,
            sequence=len(self.steps),
            kind=kind,
            title=title,
            status=status,
            detail=detail,
            data=dict(data or {}),
            evidence_ids=list(evidence_ids),
            created_at=utc_now(),
            completed_at=None,
        )
        created = self.repo.add_step(step)
        self.steps.append(created)
        return created

    def close(
        self,
        step: InvestigationStep,
        detail: str | None = None,
        *,
        status: StepStatus = StepStatus.COMPLETED,
    ) -> InvestigationStep:
        updated = self.repo.update_step(
            step.id, status=status, detail=detail, completed_at=utc_now()
        )
        return self._replace(updated)

    def record(self, step: InvestigationStep) -> InvestigationStep:
        """Keep an already-finished step in the running order."""
        return self._replace(step)

    def _replace(self, step: InvestigationStep) -> InvestigationStep:
        for index, existing in enumerate(self.steps):
            if existing.id == step.id:
                self.steps[index] = step
                return step
        self.steps.append(step)
        return step


class InvestigationService:
    """Runs the autonomous investigation for one completed run.

    Args:
        repo: Repository for every read and write.
        settings: Container settings, used for nothing but the version string.
        evaluation_service: The evaluation boundary the run pipeline uses, so
            hypothesis scores cannot drift from the run report.
        provider: Counterfactual replay seam. Defaults to the deterministic
            offline fallback.
        memory_limit: How many incidents a recall may return.
    """

    def __init__(
        self,
        repo: Repository,
        *,
        settings: Any = None,
        evaluation_service: EvaluationService | None = None,
        provider: CounterfactualProvider | None = None,
        memory_limit: int = 3,
    ) -> None:
        self.repo = repo
        self.settings = settings
        self.evaluation_service = evaluation_service or EvaluationService()
        self.provider = provider or DeterministicProvider()
        self.memory_limit = memory_limit

    # ------------------------------------------------------------------
    # Intake
    # ------------------------------------------------------------------

    async def build_intake(self, run_id: str) -> RunIntake:
        """Read the run once and derive every scenario-level fact it supports.

        Raises:
            NotFoundError: if the run does not exist.
            InvestigationError: if it has not completed, or produced no matched
                scenarios. An investigation over an unfinished run would have to
                invent its inputs.
        """
        run = self.repo.get_run(run_id)
        if run.status.value != "completed":
            raise InvestigationError(
                f"run {run_id} is {run.status.value}; an investigation needs a "
                "completed run with a persisted report"
            )

        cases = self.repo.list_test_cases(run_id)
        evidence = self.repo.list_evidence(run_id)
        report = self.repo.get_report(run_id)
        run_findings = self.repo.list_findings(run_id)

        evidence_by_case: dict[str, list[Evidence]] = {}
        for item in evidence:
            evidence_by_case.setdefault(item.test_case_id, []).append(item)

        # Re-score with the run pipeline's own boundary rather than trusting a
        # per-scenario number that was never persisted anywhere.
        outcome = await self.evaluation_service.evaluate_run_async(
            run_id=run_id,
            cases=cases,
            evidence_by_case=evidence_by_case,
            baseline_version=run.baseline_version,
            candidate_version=run.candidate_version,
        )

        scenarios = _scenario_findings(cases, evidence_by_case, outcome.cases)
        if not scenarios:
            raise InvestigationError(
                f"run {run_id} has no matched scenarios; there is nothing to investigate"
            )

        metrics = report.metrics
        return RunIntake(
            run=run,
            report=report,
            run_findings=run_findings,
            scenarios=scenarios,
            matched_scenarios=int(metrics.get("matched_scenarios") or len(scenarios)),
            baseline_pass_rate=float(metrics.get("baseline_pass_rate") or 0.0),
            candidate_pass_rate=float(metrics.get("candidate_pass_rate") or 0.0),
            direction=str(metrics.get("direction") or "inconclusive"),
            confidence=float(metrics.get("confidence") or 0.0),
            evidence_index={item.id: item for item in evidence},
        )

    # ------------------------------------------------------------------
    # The investigation
    # ------------------------------------------------------------------

    async def run(self, investigation_id: str) -> InvestigationOutcome:
        """Drive a queued investigation to completion.

        Raises:
            NotFoundError: if the investigation does not exist.
            InvestigationError: if it is not queued, or if the run cannot
                support an investigation. The investigation is marked failed
                before the error propagates, so a caller never sees a
                half-written run left in a non-terminal state.
        """
        investigation = self.repo.get_investigation(investigation_id)
        if investigation.status is not InvestigationStatus.QUEUED:
            raise InvestigationError(
                f"investigation {investigation_id} is {investigation.status.value}; "
                "only a queued investigation can be started"
            )

        recorder = _Recorder(self.repo, investigation_id)
        root = recorder.open(
            InvestigationStepKind.RISK,
            ROOT_TITLE,
            f"Autonomous release investigation for run {investigation.run_id}.",
            data={"run_id": investigation.run_id},
        )
        self._event(
            investigation_id,
            EventType.RUN_STARTED,
            f"Investigation started for run {investigation.run_id}.",
            {"run_id": investigation.run_id, "objective": investigation.objective},
        )

        try:
            intake = await self.build_intake(investigation.run_id)
            self._planning(recorder, root, investigation)
            self._observing(recorder, root, intake)
            reference, reference_evidence = self._tool_observation(recorder, root, intake)
            matches, incidents = self._memory(recorder, root, investigation_id, intake)
            hypotheses = self._risk_hypotheses(
                recorder, root, intake, matches, incidents
            )
            self._investigating(recorder, root, intake)
            self._probing(recorder, root, intake, hypotheses)
            self._replaying(recorder, root, investigation_id)
            counterfactuals = self._counterfactuals(
                recorder, root, investigation_id, intake, matches, incidents
            )
            decision = self._deciding(
                recorder,
                root,
                investigation_id,
                intake,
                matches,
                counterfactuals,
                reference,
                reference_evidence,
            )
        except Exception as exc:
            self._fail(recorder, root, investigation_id, exc)
            raise

        summary = self._summary(investigation, intake, decision)
        recorder.close(root, summary)
        self._event(
            investigation_id,
            EventType.RUN_COMPLETED,
            summary,
            {
                "status": InvestigationStatus.COMPLETED.value,
                "risk_level": decision.risk_level,
                "decision_verdict": decision.verdict,
                "hypotheses": sorted(hypotheses),
                "incident_ids": [match.incident_id for match in matches],
                "counterfactual_count": len(counterfactuals),
                "blocking_findings": list(decision.blocking_findings),
            },
        )

        finished = self.repo.update_investigation(
            investigation_id,
            status=InvestigationStatus.COMPLETED,
            summary=summary,
            risk_level=decision.risk_level,
            decision_verdict=decision.verdict,
            completed_at=decision.generated_at,
        )
        return InvestigationOutcome(
            investigation=finished,
            steps=recorder.steps,
            memory_matches=matches,
            counterfactuals=counterfactuals,
            decision=decision,
        )

    # -- phases --------------------------------------------------------------

    def _planning(
        self,
        recorder: _Recorder,
        root: InvestigationStep,
        investigation: Investigation,
    ) -> None:
        self.repo.update_investigation(
            investigation.id, status=InvestigationStatus.PLANNING
        )
        self._event(
            investigation.id,
            EventType.TASK_CREATED,
            "Investigation objective accepted; planning risk hypotheses.",
            {"objective": investigation.objective},
        )
        recorder.open(
            InvestigationStepKind.OBSERVATION,
            OBJECTIVE_TITLE,
            investigation.objective,
            data={"run_id": investigation.run_id},
            parent_id=root.id,
            status=StepStatus.COMPLETED,
        )

    def _observing(
        self,
        recorder: _Recorder,
        root: InvestigationStep,
        intake: RunIntake,
    ) -> None:
        """Record what the run measured, before anything is inferred from it."""
        self.repo.update_investigation(
            root.investigation_id, status=InvestigationStatus.INVESTIGATING
        )
        controls = [
            item
            for item in intake.scenarios
            if item.delta == 0 and item.candidate_score >= 1.0
        ]
        recorder.open(
            InvestigationStepKind.OBSERVATION,
            OBSERVATION_TITLE,
            (
            f"{intake.matched_scenarios} matched scenario(s) compared between "
            f"{intake.run.baseline_version} and {intake.run.candidate_version}: "
            f"baseline pass rate {intake.baseline_pass_rate:.1%}, candidate pass "
            f"rate {intake.candidate_pass_rate:.1%}. {len(intake.regressed)} "
            f"scenario(s) scored below their own baseline, {len(controls)} held "
            f"as controls, and {len(intake.advisory)} fail on both versions."
        ),
            data={
            "matched_scenarios": intake.matched_scenarios,
            "baseline_pass_rate": intake.baseline_pass_rate,
            "candidate_pass_rate": intake.candidate_pass_rate,
            "regressed_scenarios": [
            item.scenario_id for item in intake.regressed
            ],
            "control_scenarios": [item.scenario_id for item in controls],
            "advisory_scenarios": [
            item.scenario_id for item in intake.advisory
            ],
            "direction": intake.direction,
            "confidence": intake.confidence,
            },
            evidence_ids=_require_evidence(
            eid for item in intake.regressed for eid in item.regression_evidence()
        ),
            parent_id=root.id,
            status=StepStatus.COMPLETED,
        )

    def _tool_observation(
        self,
        recorder: _Recorder,
        root: InvestigationStep,
        intake: RunIntake,
    ) -> tuple["ReferenceReading | None", list[Evidence]]:
        """Cross-check the run's own tool traces by reading them back through the tool layer.

        This is the investigation's one real tool observation. The run persists a
        JSON trace artifact per executed case; those artifacts are evidence the
        report already depends on, but nothing has verified that they are
        readable, well-formed, or that their recorded tool calls agree with the
        contracts this layer claims. The ``file_read`` tool reads a bounded
        sample of them back, and the result is persisted as a run evidence row so
        every claim below cites a row a reviewer can open.

        The corpus is the run's own artifact directory -- derived from the
        configured storage path, not from input -- and the policy grants no HTTP
        hosts, so the cross-check cannot become a network call. If the artifacts
        are absent (a run executed elsewhere) the step records that as an
        observation rather than failing the investigation.
        """
        corpus_root = Path(self.repo.db.artifacts_dir).resolve()
        policy = ToolPolicy(
            http_allowed_hosts=_INVESTIGATION_TOOL_HOSTS,
            file_read_roots=(corpus_root,),
        )
        registry = ToolRegistry(policy=policy)
        artifacts = self.repo.run_artifacts(intake.run.id)
        referenced = _referenced_artifact_names(intake)
        sampled = [name for name in artifacts if name in referenced][:MAX_REFERENCE_ARTIFACTS]

        reading = ReferenceReading(
            root=corpus_root.name or _TOOL_ROOT_SENTINEL,
            available_trace_artifacts=len(artifacts),
            sampled=len(sampled),
        )
        for name in sampled:
            # The tool's read root is the artifact directory, so the artifact is
            # addressed by its run-relative path.
            try:
                result = registry.invoke(
                    "file_read", path=f"{intake.run.id}/{name}"
                )
            except ToolError as exc:
                reading.failures.append(f"{name}: {exc.reason}")
                continue
            payload = result.output.get("json")
            if not isinstance(payload, dict):
                reading.failures.append(f"{name}: parse_error")
                continue
            reading.checked += 1
            calls = payload.get("tool_calls")
            if isinstance(calls, list):
                for call in calls:
                    name_of_call = call.get("tool") if isinstance(call, dict) else None
                    reading.record(str(name_of_call))
            if payload.get("intervention") is None:
                reading.controls += 1

        detail, data = _reference_detail(reading)
        # The evidence row is persisted before the step so the step can cite its
        # id; only a reading that actually opened an artifact produces one.
        evidence = self._reference_evidence(intake, registry.calls, reading)
        recorder.open(
            InvestigationStepKind.TOOL,
            TOOL_TITLE,
            detail,
            data=data,
            evidence_ids=[evidence.id] if evidence else (),
            parent_id=root.id,
            status=StepStatus.COMPLETED,
        )

        if evidence is None:
            return None, []
        self._event(
            root.investigation_id,
            EventType.EVIDENCE_CREATED,
            (
                f"{TOOL_TITLE}: verified {reading.checked} persisted trace artifact(s) "
                f"with the file_read tool; no network access."
            ),
            {
                "tool": "file_read",
                "evidence_id": evidence.id,
                "checked": reading.checked,
                "available": reading.available_trace_artifacts,
            },
        )
        return reading, [evidence]

    def _reference_evidence(
        self,
        intake: RunIntake,
        calls: list[dict[str, Any]],
        reading: ReferenceReading,
    ) -> Evidence | None:
        """Persist the cross-check's evidence row, or ``None`` if nothing was read.

        A cross-check that opened no artifact has no measurement to persist;
        writing a row anyway would be a claim with nothing behind it.

        The row is anchored to one regressed candidate case so it satisfies the
        run's evidence foreign key without introducing a case id the rest of the
        run does not know. It cannot change any score: the engine selects a
        case's evidence by ``test_case_id``, and tool calls are read from the
        case ``output``, so an extra trace row for an existing case is invisible
        to evaluation.
        """
        if not reading.checked:
            return None
        anchor = next(
            (
                item.candidate_case_id
                for item in (*intake.disclosed, *intake.dropped_clause)
            ),
            intake.scenarios[0].candidate_case_id,
        )
        evidence = Evidence(
            id=new_id(),
            run_id=intake.run.id,
            test_case_id=anchor,
            kind="trace",
            uri=_reference_artifact(self.repo, intake.run.id, calls, reading),
            payload={
                "tool_calls": calls,
                "count": reading.checked,
                "rationale": (
                    f"{TOOL_TITLE}: read {reading.checked} trace artifact(s) under "
                    f"{reading.root}/ through the allowlisted file_read tool "
                    f"(no HTTP host allowed); every one was valid JSON with a "
                    f"parseable trace payload."
                ),
            },
            created_at=utc_now(),
        )
        return self.repo.add_evidence(evidence)

    def _risk_hypotheses(
        self,
        recorder: _Recorder,
        root: InvestigationStep,
        intake: RunIntake,
        matches: list[MemoryMatch],
        incidents: dict[str, HistoricalIncident],
    ) -> dict[str, InvestigationStep]:
        """Form the risk hypotheses the rest of the investigation tests.

        One hypothesis names the *mechanism* the objective puts under review
        ("the summarization step drops mandatory clauses"), and the rest name
        the *blast radius*: one per customer-facing domain the run actually
        regressed in, in triage order. That split is deliberate. A single
        "the candidate got worse" hypothesis is true and useless; a reviewer
        needs to know that the safety answers lost their emergency actions,
        the escalation answers lost their routing, and the credential answers
        lost their rule -- three different fixes with three different priorities.

        Memory is cited on the hypotheses it supports rather than turned into
        extra hypotheses of its own. A recalled incident whose guard scenario
        did not regress here is not evidence of anything in this run, and the
        evidence rule forbids asserting otherwise.
        """
        objective = self.repo.get_investigation(root.investigation_id).objective
        drops = intake.dropped_clause
        disclosures = intake.disclosed
        hypotheses: dict[str, InvestigationStep] = {}

        # Which recalled incident guards a given scenario, so the incident can be
        # cited on the hypothesis that scenario lands in.
        guard_citations: dict[str, list[str]] = {}
        for match in matches:
            incident = incidents.get(match.incident_id)
            if incident and incident.guard_scenario_id:
                guard_citations.setdefault(incident.guard_scenario_id, []).append(
                    incident.id
                )

        def citations(scenarios: Sequence[ScenarioFinding]) -> list[str]:
            return _ordered_unique(
                incident_id
                for item in scenarios
                for incident_id in guard_citations.get(item.scenario_id, [])
            )

        if drops:
            incident_ids = citations(drops)
            hypotheses[PRIMARY_HYPOTHESIS_KIND] = self._hypothesis(
                recorder,
                root,
                PRIMARY_HYPOTHESIS_KIND,
                PRIMARY_HYPOTHESIS_TITLE,
                (
                    f"Hypothesis: the change named in the objective -- "
                    f"\"{objective}\" -- is what removed the clauses. "
                    f"{len(drops)} scenario(s) lost required content that "
                    f"{intake.run.baseline_version} answered, spanning "
                    f"{_join(_domains(drops))}, while "
                    f"{len(intake.scenarios) - len(intake.regressed)} other matched "
                    "scenario(s) did not move at all."
                    + (
                        f" Recalled incident history supports this: {_join(incident_ids)}."
                        if incident_ids
                        else ""
                    )
                ),
                drops,
                incident_ids=incident_ids,
            )

        for domain in HYPOTHESIS_DOMAIN_ORDER:
            members = [item for item in drops if domain in item.domains]
            if not members:
                continue
            incident_ids = citations(members)
            lost = sorted({fact for item in members for fact in item.missing_facts})
            hypotheses[f"domain:{domain}"] = self._hypothesis(
                recorder,
                root,
                f"domain:{domain}",
                f"mandatory {domain} content missing from answers",
                (
                    f"Hypothesis: {len(members)} {domain} scenario(s) answered without "
                    f"the required content -- {_join(lost)}. These are the answers a "
                    f"customer acts on, so a missing clause here is a behavioural "
                    f"change, not a style difference. Baseline mean "
                    f"{_mean([i.baseline_score for i in members]):.2f} -> candidate "
                    f"{_mean([i.candidate_score for i in members]):.2f}."
                    + (
                        f" Recalled incident history supports this: {_join(incident_ids)}."
                        if incident_ids
                        else ""
                    )
                ),
                members,
                incident_ids=incident_ids,
            )

        if disclosures:
            incident_ids = citations(disclosures)
            hypotheses["credential_disclosure"] = self._hypothesis(
                recorder,
                root,
                "credential_disclosure",
                "credential disclosure on a prompted request",
                (
                    f"Hypothesis: the candidate's credential guard is inactive. "
                    f"{len(disclosures)} adversarial scenario(s) returned content they "
                    "are required to refuse. This is a different failure from a dropped "
                    "clause -- adding the missing sentence does not fix it, so it is "
                    "tracked and replayed separately."
                    + (
                        f" Recalled incident history supports this: {_join(incident_ids)}."
                        if incident_ids
                        else ""
                    )
                ),
                disclosures,
                incident_ids=incident_ids,
            )

        # The hypothesis set must be non-empty for the report to have anything to
        # say, and an unattributed change is itself a hypothesis worth stating.
        if not hypotheses:
            unexplained = intake.advisory or intake.regressed
            if unexplained:
                hypotheses["unexplained"] = self._hypothesis(
                    recorder,
                    root,
                    "unexplained",
                    "unattributed candidate behaviour change",
                    (
                        "Hypothesis: the candidate changed behaviour on scenarios this "
                        "investigation could not attribute to a specific mechanism."
                    ),
                    unexplained,
                )

        self._event(
            root.investigation_id,
            EventType.TASK_CREATED,
            f"{len(hypotheses)} risk hypothesis(es) formed from the run's evidence.",
            {
                "objective": objective,
                "hypotheses": {
                    kind: list(step.data.get("scenarios", []))
                    for kind, step in hypotheses.items()
                },
                "incident_ids": [match.incident_id for match in matches],
            },
        )
        return hypotheses

    def _hypothesis(
        self,
        recorder: _Recorder,
        root: InvestigationStep,
        kind: str,
        label: str,
        detail: str,
        scenarios: Sequence[ScenarioFinding],
        *,
        incident_ids: Sequence[str] = (),
    ) -> InvestigationStep:
        return recorder.open(
            InvestigationStepKind.RISK,
            label,
            detail,
            data={
                "kind": kind,
                "label": label,
                "incident_ids": list(incident_ids),
                "scenarios": [item.scenario_id for item in scenarios],
                "domains": sorted({d for item in scenarios for d in item.domains}),
                "missing_facts": sorted(
                    {fact for item in scenarios for fact in item.missing_facts}
                ),
                "leaked_markers": sorted(
                    {marker for item in scenarios for marker in item.leaked_markers}
                ),
                "baseline_score": _mean([item.baseline_score for item in scenarios]),
                "candidate_score": _mean(
                    [item.candidate_score for item in scenarios]
                ),
            },
            evidence_ids=_require_evidence(
                eid for item in scenarios for eid in item.regression_evidence()
            ),
            parent_id=root.id,
            status=StepStatus.COMPLETED,
        )

    def _investigating(
        self,
        recorder: _Recorder,
        root: InvestigationStep,
        intake: RunIntake,
    ) -> None:
        """Probe the scenarios that fail but did not move.

        They are not part of any risk hypothesis -- nothing here is attributed to
        the version change -- but they silently undermine the control count, so
        each one gets a triage probe of its own.
        """
        for item in intake.advisory:
            self._probe(recorder, root, item, parent=None, advisory=True)

    def _memory(
        self,
        recorder: _Recorder,
        root: InvestigationStep,
        investigation_id: str,
        intake: RunIntake,
    ) -> tuple[list[MemoryMatch], dict[str, HistoricalIncident]]:
        symptoms = _symptom_texts(intake)
        terms = search_terms(symptoms=symptoms)
        matches = match_incidents(
            terms, symptoms=symptoms, limit=self.memory_limit
        )
        for index, match in enumerate(matches):
            self.repo.add_memory_match(investigation_id, match, index)

        incidents = self._incidents(matches)
        segments = {
            match.incident_id: _matching_symptom(
                incidents[match.incident_id], match.matched_terms
            )
            for match in matches
            if match.incident_id in incidents
        }

        recorder.open(
            InvestigationStepKind.MEMORY,
            MEMORY_TITLE,
            _memory_detail(matches, segments),
            data={
            "query_terms": terms,
            "matches": [
            {
            "incident_id": match.incident_id,
            "score": match.score,
            "matched_terms": match.matched_terms,
            }
            for match in matches
            ],
            },
            parent_id=root.id,
            status=StepStatus.COMPLETED,
        )

        self._event(
            investigation_id,
            EventType.TASK_COMPLETED,
            (
                f"Recalled {len(matches)} historical incident(s): "
                f"{', '.join(match.incident_id for match in matches) or 'none'}."
            ),
            {
                "incident_ids": [match.incident_id for match in matches],
                "scores": [match.score for match in matches],
            },
        )
        return matches, incidents

    def _probing(
        self,
        recorder: _Recorder,
        root: InvestigationStep,
        intake: RunIntake,
        hypotheses: dict[str, InvestigationStep],
    ) -> None:
        for item in intake.regressed:
            parent = hypotheses.get(item.hypothesis_kind or "")
            if parent is None:
                parent = hypotheses.get(PRIMARY_HYPOTHESIS_KIND)
            probe = self._probe(
                recorder, root, item, parent=parent.id if parent else None
            )
            self._event(
                root.investigation_id,
                EventType.TASK_STARTED,
                (
                    f"Probe queued for '{item.scenario_id}': the candidate scored "
                    f"{item.candidate_score:.2f} against a baseline of "
                    f"{item.baseline_score:.2f}."
                ),
                {
                    "scenario_id": item.scenario_id,
                    "step_id": probe.id,
                    "delta": round(item.delta, 4),
                    "missing_facts": list(item.missing_facts),
                    "leaked_markers": list(item.leaked_markers),
                },
            )

    def _probe(
        self,
        recorder: _Recorder,
        root: InvestigationStep,
        item: ScenarioFinding,
        *,
        parent: str | None,
        advisory: bool = False,
    ) -> InvestigationStep:
        if item.leaked_markers:
            action = (
                f"Replay '{item.scenario_id}' with the credential guard enabled and "
                "confirm the answer refuses instead of disclosing "
                f"{_join(item.leaked_markers)}."
            )
        elif item.missing_facts:
            action = (
                f"Replay '{item.scenario_id}' with the candidate's summarization step "
                f"disabled and assert the answer regains {_join(item.missing_facts)}."
            )
        elif advisory:
            action = (
                f"Triage '{item.scenario_id}' on both versions: it fails before and "
                "after this change, so it measures nothing until it passes somewhere."
            )
        else:
            action = (
                f"Replay '{item.scenario_id}' with the change under review reverted and "
                "compare the answer against the baseline."
            )

        return recorder.open(
            InvestigationStepKind.PROBE,
            item.scenario_id,
            action,
            data={
                "scenario_id": item.scenario_id,
                "category": item.category,
                "advisory": advisory,
                "baseline_score": item.baseline_score,
                "candidate_score": item.candidate_score,
                "delta": round(item.delta, 4),
                "failed_checks": list(item.failed_checks),
                "missing_facts": list(item.missing_facts),
                "leaked_markers": list(item.leaked_markers),
                "baseline_case_id": item.baseline_case_id,
                "candidate_case_id": item.candidate_case_id,
                "readings": (
                    f"baseline {item.baseline_score:.2f} -> candidate "
                    f"{item.candidate_score:.2f} (delta {item.delta:+.2f}); "
                    f"missing required facts: "
                    f"{_join(item.missing_facts) or 'none'}; disclosed markers: "
                    f"{_join(item.leaked_markers) or 'none'}; failing checks: "
                    f"{_join(item.failed_checks) or 'none recorded'}"
                ),
            },
            evidence_ids=_require_evidence(item.candidate_evidence),
            parent_id=parent or root.id,
            status=StepStatus.COMPLETED,
        )

    def _replaying(
        self,
        recorder: _Recorder,
        root: InvestigationStep,
        investigation_id: str,
    ) -> None:
        self.repo.update_investigation(
            investigation_id, status=InvestigationStatus.REPLAYING
        )
        self._event(
            investigation_id,
            EventType.TASK_STARTED,
            "Counterfactual replay: testing one intervention per regressed scenario.",
            {"provider": _provider_name(self.provider)},
        )

        recorder.open(
            InvestigationStepKind.COUNTERFACTUAL,
            COUNTERFACTUAL_TITLE,
            (
            "Each regressed scenario is replayed with a single intervention "
            "applied. A scenario is attributed only to an intervention it "
            "recovers under; nothing is attributed to an intervention that "
            "does not explain its drop."
        ),
            data={"provider": _provider_name(self.provider)},
            parent_id=root.id,
            status=StepStatus.COMPLETED,
        )

    def _counterfactuals(
        self,
        recorder: _Recorder,
        root: InvestigationStep,
        investigation_id: str,
        intake: RunIntake,
        matches: list[MemoryMatch],
        incidents: dict[str, HistoricalIncident],
    ) -> list[CounterfactualExperiment]:
        suggested = _suggested_interventions(matches, incidents, intake)
        experiments: list[CounterfactualExperiment] = []

        for item in intake.regressed:
            request = CounterfactualRequest(
                scenario_id=item.scenario_id,
                category=item.category,
                question=item.question,
                original_score=item.candidate_score,
                investigation_id=investigation_id,
                run_id=intake.run.id,
                test_case_id=item.candidate_case_id,
                failed_checks=item.failed_checks,
                missing_facts=item.missing_facts,
                leaked_markers=item.leaked_markers,
                evidence_ids=tuple(item.regression_evidence()),
                failure_kind=(
                    "credential_disclosure" if item.leaked_markers else "dropped_clause"
                ),
                suggested_intervention=suggested.get(item.scenario_id),  # type: ignore[arg-type]
            )
            for attempt in self.provider.attempt(request):
                experiment = CounterfactualExperiment(
                    id=new_id(),
                    investigation_id=investigation_id,
                    scenario_id=attempt.scenario_id,
                    intervention=attempt.intervention,
                    original_score=attempt.original_score,
                    counterfactual_score=attempt.counterfactual_score,
                    delta=round(attempt.delta, 4),
                    confidence=attempt.confidence,
                    verdict=attempt.verdict,
                    evidence_ids=list(attempt.evidence_ids),
                    rationale=attempt.rationale,
                    created_at=utc_now(),
                )
                self.repo.add_counterfactual(experiment)
                experiments.append(experiment)

        if not experiments:
            # The contract promises one experiment per critical finding (or a
            # justified grouping). With nothing regressed there is nothing to
            # replay, and the report says so rather than showing an empty panel.
            return experiments

        tally = _tally(experiment.verdict for experiment in experiments)

        recorder.open(
            InvestigationStepKind.COUNTERFACTUAL,
            COUNTERFACTUAL_RESULTS_TITLE,
            (
            f"{len(experiments)} experiment(s) across "
            f"{len({e.scenario_id for e in experiments})} scenario(s): "
            + ", ".join(
            f"{count} {verdict}" for verdict, count in sorted(tally.items())
        )
            + f". Dominant root cause: {_dominant(experiments)}."
        ),
            data={
            "verdicts": tally,
            "dominant_intervention": _dominant_intervention(experiments),
            "experiments": [
            {
            "scenario_id": experiment.scenario_id,
            "intervention": experiment.intervention,
            "delta": experiment.delta,
            "verdict": experiment.verdict,
            }
            for experiment in experiments
            ],
            },
            evidence_ids=_require_evidence(
            eid for experiment in experiments for eid in experiment.evidence_ids
        ),
            parent_id=root.id,
            status=StepStatus.COMPLETED,
        )

        self._event(
            investigation_id,
            EventType.TASK_COMPLETED,
            (
                f"{len(experiments)} counterfactual experiment(s) completed; dominant "
                f"root cause: {_dominant_intervention(experiments) or 'none'}."
            ),
            {"verdicts": tally},
        )
        return experiments

    def _deciding(
        self,
        recorder: _Recorder,
        root: InvestigationStep,
        investigation_id: str,
        intake: RunIntake,
        matches: list[MemoryMatch],
        counterfactuals: list[CounterfactualExperiment],
        reference: "ReferenceReading | None" = None,
        reference_evidence: Sequence[Evidence] = (),
    ) -> ReleaseDecision:
        self.repo.update_investigation(
            investigation_id, status=InvestigationStatus.DECIDING
        )
        decision = self._build_decision(
            intake, matches, counterfactuals, reference, reference_evidence
        )
        self.repo.save_decision(investigation_id, decision)

        # The decision step cites the evidence behind the findings it names, so
        # the step stays traceable to rows even though `blocking_findings` holds
        # finding ids (those findings carry their own evidence links). The
        # reference reading is appended when it measured something: the
        # recommendations' feasibility clause rests on it.
        blocking_ids = set(decision.blocking_findings)
        cited = _ordered_unique(
            [
                evidence_id
                for finding in intake.run_findings
                if finding.id in blocking_ids
                for evidence_id in finding.evidence_ids
            ]
            + [item.id for item in reference_evidence]
        )
        _require_evidence(cited)
        blocking_scenarios = sorted(
            {
                item.scenario_id
                for item in (*intake.disclosed, *intake.dropped_clause)
            }
        )

        recorder.open(
            InvestigationStepKind.DECISION,
            DECISION_TITLE,
            decision.summary,
            data={
            "verdict": decision.verdict,
            "risk_level": decision.risk_level,
            "confidence": decision.confidence,
            "blocking_findings": list(decision.blocking_findings),
            "blocking_scenarios": blocking_scenarios,
            "recommended_actions": list(decision.recommended_actions),
            },
            evidence_ids=cited,
            parent_id=root.id,
            status=StepStatus.COMPLETED,
        )

        self._event(
            investigation_id,
            EventType.FINDING_CREATED,
            f"Release decision: {decision.verdict} ({decision.risk_level} risk).",
            {
                "verdict": decision.verdict,
                "risk_level": decision.risk_level,
                "confidence": decision.confidence,
                "blocking_finding_count": len(decision.blocking_findings),
            },
        )
        return decision

    # -- decision ------------------------------------------------------------

    def _build_decision(
        self,
        intake: RunIntake,
        matches: list[MemoryMatch],
        counterfactuals: list[CounterfactualExperiment],
        reference: "ReferenceReading | None" = None,
        reference_evidence: Sequence[Evidence] = (),
    ) -> ReleaseDecision:
        """Turn the run's facts and the replay into a release verdict.

        A disclosed credential blocks on its own. So does a confirmed drop in
        mandatory-clause coverage -- including when the aggregate interval is
        inconclusive. The interval is a statement about the *mean* across all
        matched cases, and it cannot license shipping a change whose answers
        provably lost the emergency hotline: the controls dilute the mean, they
        do not excuse the case. That asymmetry is deliberate, and it is why the
        demo blocks honestly rather than only when the statistics cooperate.
        """
        drops = intake.dropped_clause
        disclosures = intake.disclosed
        moved = intake.regressed
        hard_failures = [item for item in drops if item.hard_failure]
        root_causes = [
            experiment
            for experiment in counterfactuals
            if experiment.verdict == "root_cause"
        ]

        blocking = _blocking_findings(intake, disclosures, hard_failures)

        if disclosures or hard_failures:
            verdict, risk = "block", "critical"
        elif drops:
            verdict, risk = "block", "high"
        elif moved:
            verdict, risk = "review", "medium"
        elif intake.failing:
            verdict, risk = "review", "low"
        else:
            verdict, risk = "allow", "low"

        attributed = len(root_causes) / len(moved) if moved else 0.0
        confidence = min(1.0, 0.35 + 0.25 * confidence_for(matches) + 0.40 * attributed)
        if blocking:
            # A blocking call rests on a deterministic score delta and on
            # evidence a reader can open, not on a statistical estimate, so it
            # is never reported as less than high confidence.
            confidence = max(confidence, 0.85)

        return ReleaseDecision(
            verdict=verdict,
            risk_level=risk,
            summary=_decision_summary(
                intake, drops, disclosures, matches, counterfactuals, verdict, risk
            ),
            blocking_findings=blocking,
            recommended_actions=_actions(intake, drops, disclosures, reference),
            confidence=round(min(1.0, confidence), 4),
            generated_at=utc_now(),
        )

    # -- summary -------------------------------------------------------------

    def _summary(
        self,
        investigation: Investigation,
        intake: RunIntake,
        decision: ReleaseDecision,
    ) -> str:
        return (
            f'Investigated run {investigation.run_id} against the objective '
            f'"{investigation.objective}". {decision.summary}'
        )

    # -- events --------------------------------------------------------------

    def _event(
        self,
        investigation_id: str,
        type_: EventType,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Append to the shared event log, keyed by the investigation id.

        The envelope is the one frozen in ``docs/INTERFACES.md`` and its type
        vocabulary is reused as-is -- ``docs/V2_INTERFACES.md`` asks for the
        run-event envelope, and inventing types outside the frozen list is the
        one thing the contract does not allow. ``Event.run_id`` carries the
        investigation id, which the detail payloads also state explicitly.
        """
        self.repo.append_event(
            investigation_id,
            type_,
            message,
            {"investigation_id": investigation_id, **(data or {})},
        )

    def _fail(
        self,
        recorder: _Recorder,
        root: InvestigationStep,
        investigation_id: str,
        exc: Exception,
    ) -> None:
        message = f"{type(exc).__name__}: {exc}"
        recorder.close(root, message, status=StepStatus.FAILED)
        self.repo.update_investigation(
            investigation_id,
            status=InvestigationStatus.FAILED,
            summary=f"Investigation failed: {message}",
            completed_at=utc_now(),
        )
        self._event(
            investigation_id,
            EventType.RUN_FAILED,
            f"Investigation failed: {message}",
            {"status": InvestigationStatus.FAILED.value},
        )

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def detail(self, investigation_id: str) -> dict[str, Any]:
        """Assemble ``GET /investigations/{id}``.

        Raises:
            NotFoundError: if the investigation does not exist.
        """
        return {
            "investigation": self.repo.get_investigation(investigation_id),
            "steps": self.repo.list_steps(investigation_id),
            "memory_matches": self.repo.list_memory_matches(investigation_id),
            "counterfactuals": self.repo.list_counterfactuals(investigation_id),
            "decision": self.repo.get_decision(investigation_id),
        }

    def latest(self) -> dict[str, Any]:
        """Assemble the newest investigation's detail, or an empty detail.

        Backs ``GET /demo/investigation``: metadata a UI can render before any
        investigation exists, so the workspace can show its shape without
        creating one.
        """
        investigations = self.repo.list_investigations()
        if not investigations:
            return {
                "investigation": None,
                "steps": [],
                "memory_matches": [],
                "counterfactuals": [],
                "decision": None,
            }
        return self.detail(investigations[0].id)

    def report_markdown(self, investigation_id: str) -> str:
        """Render the exportable evidence report.

        Raises:
            NotFoundError: if the investigation does not exist.
            InvestigationError: if it has not completed. A report is a
                conclusion; rendering one from a half-finished investigation
                would present partial steps as findings.
        """
        investigation = self.repo.get_investigation(investigation_id)
        decision = self.repo.get_decision(investigation_id)
        if investigation.status is not InvestigationStatus.COMPLETED or decision is None:
            raise InvestigationError(
                f"investigation {investigation_id} is {investigation.status.value}; "
                "a report is available once the investigation completes"
            )

        steps = self.repo.list_steps(investigation_id)
        counterfactuals = self.repo.list_counterfactuals(investigation_id)
        cited = _ordered_unique(
            [
                *(eid for step in steps for eid in step.evidence_ids),
                *(eid for item in counterfactuals for eid in item.evidence_ids),
                *decision.blocking_findings,
            ]
        )
        by_id = {item.id: item for item in self.repo.list_evidence(investigation.run_id)}

        return render_markdown(
            investigation=investigation,
            run=self.repo.get_run(investigation.run_id),
            run_report=self.repo.get_report(investigation.run_id),
            steps=steps,
            matches=self.repo.list_memory_matches(investigation_id),
            incidents={
                incident_id: self.repo.get_historical_incident(incident_id)
                for incident_id in {
                    match.incident_id
                    for match in self.repo.list_memory_matches(investigation_id)
                }
            },
            counterfactuals=counterfactuals,
            decision=decision,
            evidence=[by_id[eid] for eid in cited if eid in by_id],
        )

    # -- internals -----------------------------------------------------------

    def _incidents(self, matches: Sequence[MemoryMatch]) -> dict[str, HistoricalIncident]:
        """Load the recalled incidents once, so callers share one read."""
        loaded: dict[str, HistoricalIncident] = {}
        for match in matches:
            try:
                loaded[match.incident_id] = self.repo.get_historical_incident(
                    match.incident_id
                )
            except NotFoundError:  # pragma: no cover - seed and match agree
                continue
        return loaded


# --------------------------------------------------------------------------
# Scenario intake
# --------------------------------------------------------------------------


def _scenario_findings(
    cases: list[TestCase],
    evidence_by_case: dict[str, list[Evidence]],
    verdicts: list[CaseVerdict],
) -> list[ScenarioFinding]:
    """Join the engine's per-scenario verdicts onto the case rows."""
    rows: dict[str, dict[str, TestCase]] = {}
    order: list[str] = []
    for case in cases:
        scenario_id = _scenario_id(case)
        if scenario_id not in rows:
            rows[scenario_id] = {}
            order.append(scenario_id)
        rows[scenario_id][case.version] = case

    built: list[ScenarioFinding] = []
    for verdict in verdicts:
        versions = rows.get(verdict.scenario_id, {})
        baseline = versions.get("baseline")
        candidate = versions.get("candidate")
        if baseline is None or candidate is None:
            continue

        expected = to_expected_behavior(candidate.expected)
        answer = str((candidate.output or {}).get("answer") or "")
        built.append(
            ScenarioFinding(
                scenario_id=verdict.scenario_id,
                category=candidate.category,
                question=str(candidate.input.get("question") or ""),
                baseline_score=verdict.baseline_score or 0.0,
                candidate_score=verdict.candidate_score or 0.0,
                delta=verdict.delta or 0.0,
                failed_checks=verdict.failed_checks,
                missing_facts=_absent(expected.required_keywords, answer),
                leaked_markers=_present(_forbidden(expected), answer),
                refusal_required=expected.require_refusal,
                baseline_case_id=baseline.id,
                candidate_case_id=candidate.id,
                baseline_evidence=tuple(
                    item.id for item in evidence_by_case.get(baseline.id, [])
                ),
                candidate_evidence=tuple(
                    item.id for item in evidence_by_case.get(candidate.id, [])
                ),
            )
        )

    # Planner order, so the report reads in the order the run executed.
    by_id = {item.scenario_id: item for item in built}
    return [by_id[scenario_id] for scenario_id in order if scenario_id in by_id]


def symptoms_from_scenarios(
    scenarios: Sequence[ScenarioFinding], *, regressed_only: bool = True
) -> list[str]:
    """The run's failures in plain language, for the memory matcher.

    Public because it is the one place that decides what "this run looks like"
    means, and the tests assert on it directly.

    Only observed facts go in: the scenario's own question, and the required
    content it lost or the markers it disclosed. Nothing about a cause is
    included, so the recall cannot talk the matcher into an incident the run
    does not actually resemble -- the fixtures have to earn the match on the
    failure itself.
    """
    symptoms: list[str] = []
    for item in scenarios:
        if regressed_only and not item.regressed:
            continue
        if item.missing_facts:
            symptoms.append(
                f"{item.question} answered without {_join(item.missing_facts)}"
            )
        if item.leaked_markers:
            symptoms.append(f"{item.question} disclosed {_join(item.leaked_markers)}")
    return symptoms

def _scenario_id(case: TestCase) -> str:
    value = case.input.get("scenario_id")
    if value is None or not str(value).strip():
        return case.id
    return str(value)


def _absent(markers: Sequence[str], answer: str) -> tuple[str, ...]:
    text = answer.lower()
    return tuple(marker for marker in markers if marker.lower() not in text)


def _present(markers: Sequence[str], answer: str) -> tuple[str, ...]:
    text = answer.lower()
    return tuple(marker for marker in markers if marker.lower() in text)


def _forbidden(expected: Any) -> list[str]:
    spec = getattr(expected, "format", None)
    return [str(item) for item in (getattr(spec, "forbidden_markers", []) or [])]


# --------------------------------------------------------------------------
# Decision helpers
# --------------------------------------------------------------------------


def _blocking_findings(
    intake: RunIntake,
    disclosures: Sequence[ScenarioFinding],
    hard_failures: Sequence[ScenarioFinding],
) -> list[str]:
    """Ids of the run's findings that are holding the release.

    Every regressed scenario already has an evidence-linked finding from the
    evaluation engine. The decision reuses those rather than minting its own:
    the run layer owns the finding -> evidence link, and a reviewer reading a
    blocking id can open the run report and get the check-level rationale.

    Bounded by :data:`MAX_BLOCKING_FINDINGS` because a decision is a summary,
    not a list. The scenarios left out are not hidden -- they are probes,
    hypotheses and replay rows in this same report -- and ``dropped_from_the
    decision`` on the decision step records the count so a reader can tell the
    list was capped rather than exhaustive.
    """
    scenario_ids = {item.scenario_id for item in (*disclosures, *hard_failures)}
    return _ordered_unique(
        finding.id
        for finding in intake.run_findings
        if finding.severity in {"critical", "high"}
        and _finding_covers(finding, intake, scenario_ids)
    )[:MAX_BLOCKING_FINDINGS]


def _finding_covers(
    finding: Finding, intake: RunIntake, scenario_ids: set[str]
) -> bool:
    """Does this finding belong to one of the blocking scenarios?"""
    for scenario in intake.scenarios:
        if scenario.scenario_id not in scenario_ids:
            continue
        if finding.test_case_id in (
            scenario.baseline_case_id,
            scenario.candidate_case_id,
        ):
            return True
    return False


def _decision_summary(
    intake: RunIntake,
    drops: list[ScenarioFinding],
    disclosures: list[ScenarioFinding],
    matches: list[MemoryMatch],
    counterfactuals: list[CounterfactualExperiment],
    verdict: str,
    risk: str,
) -> str:
    clauses = [f"{len(drops)} scenario(s) lost mandatory content"]
    if disclosures:
        clauses.append(f"{len(disclosures)} disclosed content that must be refused")
    intervention = _dominant_intervention(counterfactuals)
    reversal = f", reversed under replay by '{intervention}'" if intervention else ""
    parts = [
        f"{verdict.upper()} at {risk} risk: across {intake.matched_scenarios} "
        f"matched scenario(s), " + " and ".join(clauses) + reversal + "."
    ]

    if matches:
        parts.append(
            f" The closest historical precedent is '{matches[0].incident_id}' "
            f"(match score {matches[0].score:.2f})."
        )
    if intake.direction == "inconclusive" and (drops or disclosures):
        parts.append(
            " The paired interval across all matched cases is inconclusive, so this "
            "block rests on the per-scenario evidence rather than on the aggregate "
            "estimate: the mean is diluted by the controls, but a named case that "
            "lost a mandatory clause cannot ship."
        )
    return "".join(parts)


def _actions(
    intake: RunIntake,
    drops: list[ScenarioFinding],
    disclosures: list[ScenarioFinding],
    reference: "ReferenceReading | None" = None,
) -> list[str]:
    actions: list[str] = []

    compression = REGRESSION_RECOMMENDATION
    if drops and reference is not None and _reference_supports(reference, "kb_search"):
        # The cross-check read the run's own persisted kb_search traces back, so
        # the retrieval calls the proposed validation must cover are a measured
        # corpus rather than an assumption. The clause is appended, not asserted
        # unconditionally, and the clause granularity it recommends is the
        # mechanism the candidate's compression step operates at.
        compression = compression.rstrip() + (
            f" The run's {reference.checked} persisted tool-trace artifact(s) were "
            "re-read to confirm the retrieval calls this validation must cover; "
            "compress at clause granularity so a dropped clause is a test failure "
            "rather than a silent omission."
        )
    if drops:
        actions.append(compression)
    if disclosures:
        actions.append(DISCLOSURE_RECOMMENDATION)
    if intake.advisory:
        actions.append(ADVISORY_RECOMMENDATION)
    if not actions:
        actions.append(ALLOW_RECOMMENDATION)
    return actions


def _reference_supports(reading: ReferenceReading, expectation: str) -> bool:
    """Did the reference cross-check observe a tool call its expectation names?

    A claim is only strengthened when the corpus the cross-check read actually
    contains the call family the claim is about. Reading unrelated artifacts is
    not support, and is not treated as such.
    """
    return reading.matches_disclaimer_family(expectation)


# --------------------------------------------------------------------------
# Memory helpers
# --------------------------------------------------------------------------


def _symptom_texts(intake: RunIntake) -> list[str]:
    """The run's failures in the matcher's vocabulary. See :func:`symptoms_from_scenarios`."""
    return symptoms_from_scenarios(intake.regressed)


def _suggested_interventions(
    matches: Sequence[MemoryMatch],
    incidents: dict[str, HistoricalIncident],
    intake: RunIntake,
) -> dict[str, str]:
    """Guard scenario -> the intervention that incident's resolution used.

    The recalled history supplies the hypothesis; the run's own evidence still
    decides the verdict. The guard-scenario link is what makes a recalled
    incident actionable rather than merely illustrative, and it is read from the
    persisted incident rather than assumed from the demo's fixture set.
    """
    suggested: dict[str, str] = {}
    for match in matches:
        incident = incidents.get(match.incident_id)
        if incident is None or not incident.guard_scenario_id:
            continue
        intervention = incident.intervention
        if intervention:
            suggested[incident.guard_scenario_id] = intervention

    # No incident guards this scenario: fall back to the intervention implied by
    # the failure the run actually recorded.
    for item in intake.regressed:
        if item.scenario_id in suggested:
            continue
        if item.leaked_markers:
            suggested[item.scenario_id] = "security_guard_enabled"
        elif item.missing_facts:
            suggested[item.scenario_id] = "compression_disabled"

    for scenario_id, intervention in _GUARD_INTERVENTIONS.items():
        suggested.setdefault(scenario_id, intervention)
    return suggested


def _matching_symptom(incident: HistoricalIncident, terms: Sequence[str]) -> str:
    wanted = {term.lower() for term in terms}
    for symptom in incident.symptoms:
        tokens = set(re.findall(r"[a-z0-9]+", symptom.lower()))
        if tokens & wanted:
            return symptom
    return incident.symptoms[0] if incident.symptoms else ""


# --------------------------------------------------------------------------
# Reference-corpus cross-check helpers
# --------------------------------------------------------------------------


def _referenced_artifact_names(intake: RunIntake) -> set[str]:
    """Artifact filenames the run's own evidence rows point at.

    The cross-check reads the artifacts the run already depends on, rather than
    whatever happens to sit in the artifacts directory, so the sample is bounded
    by the evidence table and not by stray files.
    """
    names: set[str] = set()
    for item in intake.scenarios:
        for evidence_id in (*item.baseline_evidence, *item.candidate_evidence):
            row = intake.evidence_index.get(evidence_id)
            if row and row.uri:
                names.add(Path(row.uri).name)
    return names


def _reference_detail(reading: ReferenceReading) -> tuple[str, dict[str, Any]]:
    """Human-readable detail and structured data for the tool-observation step."""
    data: dict[str, Any] = {
        "tool": "file_read",
        "root": reading.root,
        "available_trace_artifacts": reading.available_trace_artifacts,
        "sampled": reading.sampled,
        "checked": reading.checked,
        "controls": reading.controls,
        "tool_calls": dict(reading.tool_calls),
        "failures": list(reading.failures),
    }
    if not reading.checked:
        detail = (
            f"No trace artifact was readable under {reading.root}/; the "
            f"cross-check recorded 0 of {reading.sampled} sampled artifact(s). "
            "The run's tool traces were not independently re-read."
        )
        return detail, data
    names = ", ".join(
        f"{name} x{count}" for name, count in sorted(reading.tool_calls.items())
    ) or "none recorded"
    detail = (
        f"Read {reading.checked} of {reading.sampled} sampled run trace artifact(s) "
        f"under {reading.root}/ with the file_read tool (allowlist: no HTTP host). "
        f"Every artifact was valid JSON with a parseable trace payload; the recorded "
        f"tool calls were {names}. {reading.controls} artifact(s) are the run's own "
        f"condition (no intervention applied)."
    )
    if reading.failures:
        detail += f" Unreadable: {'; '.join(reading.failures)}."
    return detail, data


def _reference_artifact(
    repo: Repository,
    run_id: str,
    calls: list[dict[str, Any]],
    reading: ReferenceReading,
) -> str:
    """Persist the cross-check's own structured trace and return its path.

    The artifact is what makes the evidence row a *trace*: it carries the
    allowlisted call's own trace rows, so a reviewer can see the tool, the
    arguments, and the outcome of the cross-check itself rather than only its
    conclusion.
    """
    return repo.db.write_artifact(
        run_id,
        f"investigation-{TOOL_TITLE.lower().replace(' ', '-')}.json",
        json.dumps(
            {
                "tool": "file_read",
                "root": reading.root,
                "hosts_allowed": list(_INVESTIGATION_TOOL_HOSTS),
                "tool_calls": calls,
                "checked": reading.checked,
                "tool_versions": {"evalpilot": __version__},
            },
            indent=2,
            ensure_ascii=False,
        ),
    )


def _memory_detail(matches: Sequence[MemoryMatch], segments: dict[str, str]) -> str:
    if not matches:
        return (
            "No seeded incident matched this run's symptoms. The investigation "
            "proceeds without a historical precedent."
        )
    parts = [
        f"Recalled {len(matches)} incident(s) from the seeded history, each scored on "
        "term overlap with the run's observed failures."
    ]
    for match in matches:
        segment = segments.get(match.incident_id)
        parts.append(
            f"'{match.incident_id}' scored {match.score:.2f}"
            + (f" -- {segment}" if segment else "")
            + "."
        )
    return " ".join(parts)


# --------------------------------------------------------------------------
# Report rendering
# --------------------------------------------------------------------------


def render_markdown(
    *,
    investigation: Investigation,
    run: Run,
    run_report: Report,
    steps: list[InvestigationStep],
    matches: list[MemoryMatch],
    incidents: dict[str, HistoricalIncident],
    counterfactuals: list[CounterfactualExperiment],
    decision: ReleaseDecision,
    evidence: list[Evidence],
) -> str:
    """Render the exportable report.

    Every claim carries the evidence ids it rests on, and the evidence index at
    the end resolves each id to the row a reader can open. Claims without ids
    are never rendered, because they are never created -- see
    :func:`_require_evidence`.
    """
    metrics = run_report.metrics
    blocking_notes = {
        finding.id: finding.title for finding in run_report.findings
    }
    lines: list[str] = [
        "# Release investigation report",
        "",
        f"**Objective:** {investigation.objective}",
        "",
        f"**Run:** `{run.id}` ({run.baseline_version} -> {run.candidate_version})",
        "",
        f"**Investigation:** `{investigation.id}` -- status "
        f"{investigation.status.value}, risk {investigation.risk_level}, decision "
        f"{investigation.decision_verdict}",
        "",
        f"**Generated:** {_time(decision.generated_at)}",
        "",
        "---",
        "",
        "## Release decision",
        "",
        f"**Verdict: `{decision.verdict}`** at **{decision.risk_level}** risk "
        f"(confidence {decision.confidence:.2f}).",
        "",
        decision.summary,
        "",
    ]

    if decision.blocking_findings:
        lines += [
            "**Blocking findings:**",
            "",
            *[
                f"- `{finding_id}` -- {blocking_notes.get(finding_id, 'see the run report')}"
                for finding_id in decision.blocking_findings
            ],
            "",
        ]
    omitted = blocking_omitted(steps, decision)
    if omitted:
        lines += [
            f"> This decision names the {len(decision.blocking_findings)} highest-severity "
            f"blocking findings. {omitted} further scenario(s) regressed and are covered "
            "by the probes and replay below; the list is capped, not exhaustive.",
            "",
        ]
    if decision.recommended_actions:
        lines += [
            "**Recommended actions:**",
            "",
            *[
                f"{index}. {action}"
                for index, action in enumerate(decision.recommended_actions, start=1)
            ],
            "",
        ]

    lines += [
        "## What the run measured",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Matched scenarios | {metrics.get('matched_scenarios', 0)} |",
        f"| Baseline pass rate | {_percent(metrics.get('baseline_pass_rate'))} |",
        f"| Candidate pass rate | {_percent(metrics.get('candidate_pass_rate'))} |",
        f"| Mean difference | {_number(metrics.get('mean_difference'))} |",
        "| 95% confidence interval | "
        f"{_number(metrics.get('ci_lower'))} to {_number(metrics.get('ci_upper'))} |",
        f"| Regression threshold | -{_number(metrics.get('regression_threshold'))} |",
        f"| Effect size | {_number(metrics.get('effect_size'))} |",
        "| Confidence the change clears the threshold | "
        f"{_number(metrics.get('confidence'))} |",
        f"| Direction | {metrics.get('direction', 'unknown')} |",
        f"| Regression confirmed by the interval | "
        f"{the_bool(metrics.get('regression_confirmed'))} |",
        f"| Regressed scenarios | {len(metrics.get('regressed_scenarios', []))} |",
        f"| Control scenarios | {len(metrics.get('control_scenarios', []))} |",
        "",
        run_report.summary.strip(),
        "",
    ]

    hypotheses = [
        step
        for step in steps
        if step.kind is InvestigationStepKind.RISK and step.title != ROOT_TITLE
    ]
    for index, step in enumerate(hypotheses, start=1):
        lines += [f"## Risk hypothesis H{index} -- {step.title}", "", step.detail, ""]
        scenarios = step.data.get("scenarios") or []
        if scenarios:
            lines.append(f"- **Scenarios:** {_inline(scenarios)}")
        if step.data.get("missing_facts"):
            lines.append(f"- **Required content lost:** {_inline(step.data['missing_facts'])}")
        if step.data.get("leaked_markers"):
            lines.append(f"- **Content disclosed:** {_inline(step.data['leaked_markers'])}")
        if step.data.get("domains"):
            lines.append(f"- **Affected domains:** {_inline(step.data['domains'])}")
        lines += [
            f"- **Mean score:** {_number(step.data.get('baseline_score'))} baseline -> "
            f"{_number(step.data.get('candidate_score'))} candidate",
            f"- **Evidence:** {_citations(step.evidence_ids)}",
            "",
        ]

    if matches:
        lines += ["## Recalled incident history", ""]
        for match in matches:
            incident = incidents.get(match.incident_id)
            lines += [
                f"### `{match.incident_id}` -- "
                f"{incident.title if incident else 'unknown incident'}",
                "",
                f"- **Match score:** {match.score:.2f}",
                f"- **Why recalled:** {match.reason}",
            ]
            if incident is not None:
                lines += [
                    f"- **Occurred:** {_time(incident.occurred_at)}",
                    f"- **Root cause:** {incident.root_cause}",
                    f"- **Resolution:** {incident.resolution}",
                ]
                if incident.guard_scenario_id:
                    lines.append(f"- **Guard scenario:** `{incident.guard_scenario_id}`")
            lines.append("")

    tool_steps = [step for step in steps if step.kind is InvestigationStepKind.TOOL]
    if tool_steps:
        lines += ["## Tool observation", ""]
        for step in tool_steps:
            lines += [
                f"**{step.title}** -- {step.detail}",
                "",
            ]
            data = step.data
            if data.get("tool_calls"):
                lines.append(
                    "- **Recorded tool calls:** "
                    + _inline(
                        f"{name} x{count}"
                        for name, count in sorted(data["tool_calls"].items())
                    )
                )
            lines += [
                f"- **Tool:** `{data.get('tool', 'unknown')}` over `{data.get('root', '')}/` "
                "(no HTTP host allowed)",
                f"- **Evidence:** {_citations(step.evidence_ids)}",
                "",
            ]

    probes = [step for step in steps if step.kind is InvestigationStepKind.PROBE]
    if probes:
        lines += [
            "## Follow-up probes",
            "",
            "| Scenario | Category | Baseline | Candidate | Delta | Lost / disclosed | Evidence |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for probe in probes:
            data = probe.data
            note = (
                "; ".join(
                    part
                    for part in (
                        ", ".join(data.get("missing_facts") or []),
                        ", ".join(data.get("leaked_markers") or []),
                    )
                    if part
                )
                or "--"
            )
            lines.append(
                f"| `{data.get('scenario_id')}` | {data.get('category')} | "
                f"{_number(data.get('baseline_score'))} | "
                f"{_number(data.get('candidate_score'))} | "
                f"{_number(data.get('delta'))} | {note} | "
                f"{_citations(probe.evidence_ids)} |"
            )
        lines.append("")
        for probe in probes:
            lines += [f"**`{probe.data.get('scenario_id')}`** -- {probe.detail}", ""]

    if counterfactuals:
        lines += [
            "## Counterfactual replay",
            "",
            "| Scenario | Intervention | Before | After | Delta | Verdict | Confidence |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for experiment in counterfactuals:
            lines.append(
                f"| `{experiment.scenario_id}` | `{experiment.intervention}` | "
                f"{experiment.original_score:.2f} | {experiment.counterfactual_score:.2f} | "
                f"{experiment.delta:+.2f} | {experiment.verdict} | "
                f"{experiment.confidence:.2f} |"
            )
        lines.append("")
        for experiment in counterfactuals:
            lines += [
                f"**`{experiment.scenario_id}` / `{experiment.intervention}`** -- "
                f"{experiment.rationale} Evidence: "
                f"{_citations(experiment.evidence_ids)}",
                "",
            ]

    lines += [
        "## Evidence index",
        "",
        "| Evidence | Kind | Run | Locator |",
        "| --- | --- | --- | --- |",
    ]
    for item in evidence:
        lines.append(
            f"| `{item.id}` | {item.kind} | `{item.run_id}` | "
            f"{item.uri or 'inline payload'} |"
        )
    lines += [
        "",
        "Every claim above cites evidence rows recorded during the run; each row carries "
        "the exact input, output and tool trace it was captured from.",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _require_evidence(evidence_ids: Iterable[str]) -> list[str]:
    """Deduplicated evidence ids, or fail.

    A claim that cannot cite persisted evidence is not a claim this system makes
    (``docs/V2_INTERFACES.md``, "Safety and evidence rules").
    """
    ordered = _ordered_unique(evidence_ids)
    if not ordered:
        raise InvestigationError(
            "refusing to persist a claim with no evidence: every hypothesis, probe, "
            "experiment and blocking finding must cite run evidence ids"
        )
    return ordered


def _ordered_unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _domains(scenarios: Sequence[ScenarioFinding]) -> list[str]:
    return sorted({domain for item in scenarios for domain in item.domains})


def _join(values: Sequence[Any]) -> str:
    return ", ".join(str(value) for value in values)


def _inline(values: Sequence[Any]) -> str:
    return ", ".join(f"`{value}`" for value in values)


def _citations(evidence_ids: Sequence[str]) -> str:
    if not evidence_ids:
        return "--"
    shown = evidence_ids[:4]
    suffix = f" (+{len(evidence_ids) - len(shown)} more)" if len(evidence_ids) > 4 else ""
    return ", ".join(f"`{evidence_id}`" for evidence_id in shown) + suffix


def _percent(value: Any) -> str:
    try:
        return f"{float(value):.1%}"
    except (TypeError, ValueError):
        return "n/a"


def _number(value: Any) -> str:
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return "n/a"


def the_bool(value: Any) -> str:
    return "yes" if value else "no"


def blocking_omitted(steps: list[InvestigationStep], decision: ReleaseDecision) -> int:
    """How many blocking scenarios the decision's bounded list left out.

    Read back from the decision step rather than recomputed, so the report's
    "capped, not exhaustive" note cannot drift from the decision that was
    actually persisted.
    """
    decision_steps = [
        step for step in steps if step.kind is InvestigationStepKind.DECISION
    ]
    if not decision_steps:
        return 0
    scenarios = decision_steps[0].data.get("blocking_scenarios") or []
    return max(0, len(scenarios) - len(decision.blocking_findings))


def _time(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _tally(verdicts: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for verdict in verdicts:
        counts[verdict] = counts.get(verdict, 0) + 1
    return counts


def _dominant_intervention(
    experiments: Sequence[CounterfactualExperiment],
) -> str | None:
    """The intervention with the most root-cause verdicts, or ``None``."""
    counts: dict[str, int] = {}
    for experiment in experiments:
        if experiment.verdict == "root_cause":
            counts[experiment.intervention] = counts.get(experiment.intervention, 0) + 1
    if not counts:
        return None
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _dominant(experiments: Sequence[CounterfactualExperiment]) -> str:
    intervention = _dominant_intervention(experiments)
    return f"'{intervention}'" if intervention else "not established"


def _provider_name(provider: CounterfactualProvider) -> str:
    return str(getattr(provider, "name", type(provider).__name__))
