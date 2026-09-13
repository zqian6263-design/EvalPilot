"""Evaluation service: the boundary the API layer calls.

The service has one async core (:meth:`EvaluationService.compare_async`) and one
synchronous wrapper (:meth:`EvaluationService.compare`) so a sync FastAPI route
and an async route can both use it. The sync wrapper refuses to run inside a
live event loop rather than deadlocking on one.

Scoring
-------
Each sampled observation is scored on two independent axes:

- **deterministic**, from :mod:`evalpilot.evaluation.checks`, always available;
- **judge**, from the injected LLM judge, only when a rubric is supplied and the
  observation did not error.

They are blended with equal weight. Deterministic checks stay authoritative
because they are reproducible and free; the judge adds judgement on qualities
no keyword check can see. A judge failure is counted and the deterministic score
is used alone, so one flaky judge call cannot zero out a run.

Then trials are collapsed to a per-case, per-version mean. That collapse is
what makes the downstream comparison treat the *case* as the unit of analysis.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime

from pydantic import Field

from .checks import applicable_score, run_deterministic_checks
from .comparison import DEFAULT_REGRESSION_THRESHOLD, ComparisonResult, compare_matched_cases
from .findings import build_comparison_findings, build_missing_evidence_findings
from .judge import DEFAULT_RUBRIC, JudgeError, RubricJudge
from .models import (
    CheckKind,
    CheckOutcome,
    ComparisonDirection,
    EvaluationModel,
    EvidenceKind,
    ExpectedBehavior,
    Finding,
    JudgeOutput,
    JudgeRequest,
    MissingEvidence,
    SampleObservation,
    Version,
    utc_now,
)

#: The checks whose failure means "this case did not provide the evidence it
#: was supposed to". Maps a failing check to the evidence it stands for.
_MISSING_EVIDENCE_BY_CHECK: dict[CheckKind, EvidenceKind] = {
    CheckKind.CITATION: EvidenceKind.CITATION,
    CheckKind.TOOL_TRACE: EvidenceKind.TRACE,
}

#: Weight of the deterministic half of a blended score.
DETERMINISTIC_WEIGHT = 0.5

#: Suite order, so a case's failing checks report in a stable sequence rather
#: than in whatever order a set happened to iterate.
_CHECK_ORDER: tuple[CheckKind, ...] = (
    CheckKind.FORMAT,
    CheckKind.REFUSAL,
    CheckKind.CITATION,
    CheckKind.FACTS,
    CheckKind.TOOL_TRACE,
)


class CaseEvaluation(EvaluationModel):
    """Aggregated evaluation of one test case across its sampled trials."""

    case_id: str
    trial_counts: dict[str, int] = Field(default_factory=dict)
    scores_by_version: dict[str, float] = Field(default_factory=dict)
    deterministic_scores_by_version: dict[str, float] = Field(default_factory=dict)
    judge_scores_by_version: dict[str, float] = Field(default_factory=dict)
    judge_failures: int = 0
    judge_usage: dict[str, int] = Field(default_factory=dict)
    errors: int = 0
    missing_evidence: list[MissingEvidence] = Field(default_factory=list)
    #: Checks that failed on at least one trial, deduplicated in suite order.
    #: ``missing_evidence`` only covers checks that stand for a piece of
    #: evidence (citations, tool traces); a caller reporting *why* a case lost
    #: points needs the content failures too.
    failing_checks: list[CheckKind] = Field(default_factory=list)
    observations_scored: int = 0

    @property
    def average(self) -> float | None:
        """Mean score across versions, or ``None`` when nothing was scored."""
        if not self.scores_by_version:
            return None
        return sum(self.scores_by_version.values()) / len(self.scores_by_version)


class ComparisonReport(EvaluationModel):
    """The artifact the API layer serves and the UI renders."""

    run_id: str | None = None
    comparison: ComparisonResult
    findings: list[Finding] = Field(default_factory=list)
    case_evaluations: list[CaseEvaluation] = Field(default_factory=list)
    metrics: dict[str, float | int | str] = Field(default_factory=dict)
    excluded_case_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    judge_failures: int = 0
    judge_usage: dict[str, int] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=utc_now)


class EvaluationService:
    """Scores observations and compares matched cases.

    Args:
        judge: An injected judge. Optional: without one, only deterministic
            checks run. Tests inject fakes; production injects an adapter over
            whatever LLM client the project uses.
        judge_criteria: Default criteria names passed to the judge.
        threshold: Regression threshold forwarded to the comparison.
        bootstrap_resamples: Bootstrap resamples forwarded to the comparison.
        seed: Bootstrap seed, so a run's verdict is reproducible.
    """

    def __init__(
        self,
        *,
        judge: RubricJudge | None = None,
        judge_criteria: Sequence[str] | None = None,
        threshold: float = DEFAULT_REGRESSION_THRESHOLD,
        bootstrap_resamples: int = 2000,
        seed: int = 0,
    ) -> None:
        self.judge = judge
        self.judge_criteria = list(judge_criteria or [])
        self.threshold = threshold
        self.bootstrap_resamples = bootstrap_resamples
        self.seed = seed

    # ------------------------------------------------------------------
    # Single-case evaluation
    # ------------------------------------------------------------------

    def evaluate_case(
        self,
        *,
        case_id: str,
        expected: ExpectedBehavior,
        observations: Sequence[SampleObservation],
        rubric: str | None = None,
        question: str | None = None,
        context: str | None = None,
    ) -> CaseEvaluation:
        """Synchronously evaluate one case.

        Raises:
            ValueError: if any observation belongs to a different case.
            RuntimeError: if called from inside a running event loop; use
                :meth:`evaluate_case_async` there instead.
        """
        self._guard_event_loop("evaluate_case", "evaluate_case_async")
        return asyncio.run(
            self.evaluate_case_async(
                case_id=case_id,
                expected=expected,
                observations=observations,
                rubric=rubric,
                question=question,
                context=context,
            )
        )

    async def evaluate_case_async(
        self,
        *,
        case_id: str,
        expected: ExpectedBehavior,
        observations: Sequence[SampleObservation],
        rubric: str | None = None,
        question: str | None = None,
        context: str | None = None,
    ) -> CaseEvaluation:
        """Evaluate one case, awaiting judge calls concurrently.

        Raises:
            ValueError: if any observation belongs to a different case.
        """
        selected = self._select_observations(case_id, observations)

        tasks = [
            self._score_observation(
                observation,
                expected=expected,
                rubric=rubric,
                question=question,
                context=context,
            )
            for observation in selected
        ]
        scored = await asyncio.gather(*tasks) if tasks else []

        return self._aggregate_case(case_id, scored)

    # ------------------------------------------------------------------
    # Full comparison
    # ------------------------------------------------------------------

    def compare(
        self,
        *,
        observations: Sequence[SampleObservation],
        expectations: Mapping[str, ExpectedBehavior],
        evidence_ids_by_case: Mapping[str, Sequence[str]],
        rubric: str | None = None,
        questions: Mapping[str, str] | None = None,
        contexts: Mapping[str, str] | None = None,
        run_id: str | None = None,
    ) -> ComparisonReport:
        """Synchronously run a full matched comparison.

        Raises:
            RuntimeError: if called from inside a running event loop; use
                :meth:`compare_async` there instead.
        """
        self._guard_event_loop("compare", "compare_async")
        return asyncio.run(
            self.compare_async(
                observations=observations,
                expectations=expectations,
                evidence_ids_by_case=evidence_ids_by_case,
                rubric=rubric,
                questions=questions,
                contexts=contexts,
                run_id=run_id,
            )
        )

    async def compare_async(
        self,
        *,
        observations: Sequence[SampleObservation],
        expectations: Mapping[str, ExpectedBehavior],
        evidence_ids_by_case: Mapping[str, Sequence[str]],
        rubric: str | None = None,
        questions: Mapping[str, str] | None = None,
        contexts: Mapping[str, str] | None = None,
        run_id: str | None = None,
    ) -> ComparisonReport:
        """Run a full matched comparison across all cases and versions."""
        warnings: list[str] = []
        questions = dict(questions or {})
        contexts = dict(contexts or {})
        evidence_ids_by_case = {
            case_id: list(ids) for case_id, ids in evidence_ids_by_case.items()
        }

        # Evaluate every case that has an expectation, in a stable order.
        case_ids = _stable_unique(observation.case_id for observation in observations)
        scorable = [case_id for case_id in case_ids if case_id in expectations]
        for case_id in case_ids:
            if case_id not in expectations:
                warnings.append(
                    f"Case {case_id} has no expectation and was skipped: every case "
                    "needs an ExpectedBehavior to be scored."
                )

        evaluations = [
            await self.evaluate_case_async(
                case_id=case_id,
                expected=expectations[case_id],
                observations=observations,
                rubric=rubric,
                question=questions.get(case_id),
                context=contexts.get(case_id),
            )
            for case_id in scorable
        ]

        by_case = {evaluation.case_id: evaluation for evaluation in evaluations}

        # Build matched pairs: only cases scored on both versions.
        pairs: list[tuple[float, float]] = []
        matched_case_ids: list[str] = []
        excluded_case_ids: list[str] = []
        for case_id in scorable:
            evaluation = by_case[case_id]
            baseline = evaluation.scores_by_version.get(Version.BASELINE.value)
            candidate = evaluation.scores_by_version.get(Version.CANDIDATE.value)
            if baseline is None or candidate is None:
                excluded_case_ids.append(case_id)
                continue
            pairs.append((baseline, candidate))
            matched_case_ids.append(case_id)

        if excluded_case_ids:
            warnings.append(
                f"{len(excluded_case_ids)} case(s) were not matched across both versions "
                "and were excluded from the comparison."
            )
        if not pairs:
            warnings.append("No cases were matched across both versions; nothing to compare.")

        comparison = compare_matched_cases(
            pairs,
            seed=self.seed,
            threshold=self.threshold,
            resamples=self.bootstrap_resamples,
        )

        trial_counts = [max(e.trial_counts.values()) for e in evaluations if e.trial_counts]
        trial_count = max(trial_counts) if trial_counts else 0

        findings, finding_warnings = self._build_findings(
            comparison=comparison,
            evaluations=evaluations,
            matched_case_ids=matched_case_ids,
            evidence_ids_by_case=evidence_ids_by_case,
            run_id=run_id,
        )
        warnings.extend(finding_warnings)

        return ComparisonReport(
            run_id=run_id,
            comparison=comparison.model_copy(update={"trial_count": trial_count}),
            findings=findings,
            case_evaluations=evaluations,
            metrics=self._build_metrics(comparison, evaluations, trial_count),
            excluded_case_ids=excluded_case_ids,
            warnings=warnings,
            judge_failures=sum(e.judge_failures for e in evaluations),
            judge_usage=_sum_usage(e.judge_usage for e in evaluations),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_findings(
        self,
        *,
        comparison: ComparisonResult,
        evaluations: Sequence[CaseEvaluation],
        matched_case_ids: Sequence[str],
        evidence_ids_by_case: Mapping[str, Sequence[str]],
        run_id: str | None,
    ) -> tuple[list[Finding], list[str]]:
        warnings: list[str] = []
        findings: list[Finding] = []

        attributed = {
            case_id: list(evidence_ids_by_case.get(case_id, []))
            for case_id in matched_case_ids
        }
        comparison_evidence = [
            evidence_id for ids in attributed.values() for evidence_id in ids
        ]

        if comparison_evidence:
            findings.extend(
                build_comparison_findings(
                    comparison=comparison,
                    case_ids=list(matched_case_ids),
                    evidence_ids=comparison_evidence,
                    title="Candidate version regressed against baseline",
                    description=(
                        f"Across {comparison.sample_size} matched case(s), the candidate's "
                        f"mean score changed by {comparison.mean_difference:+.3f} "
                        f"(effect size {comparison.effect_size:+.2f}). "
                        f"Confidence the change clears the threshold: "
                        f"{comparison.confidence:.0%}."
                    ),
                    run_id=run_id,
                )
            )
        elif comparison.direction is ComparisonDirection.REGRESSION:
            warnings.append(
                "A regression was detected but no evidence ids were supplied for the "
                "matched cases, so no finding was emitted. Findings must cite evidence."
            )

        gaps: list[MissingEvidence] = []
        for evaluation in evaluations:
            gaps.extend(evaluation.missing_evidence)

        if gaps:
            unattributed = [
                gap.case_id
                for gap in gaps
                if not evidence_ids_by_case.get(gap.case_id)
            ]
            if unattributed:
                warnings.append(
                    f"{len(unattributed)} missing-evidence gap(s) could not be attributed "
                    "to evidence ids and produced no finding."
                )
            findings.extend(
                build_missing_evidence_findings(
                    missing_evidence=[
                        gap for gap in gaps if evidence_ids_by_case.get(gap.case_id)
                    ],
                    evidence_ids_by_case=evidence_ids_by_case,
                    run_id=run_id,
                )
            )

        return findings, warnings

    @staticmethod
    def _build_metrics(
        comparison: ComparisonResult,
        evaluations: Sequence[CaseEvaluation],
        trial_count: int,
    ) -> dict[str, float | int | str]:
        return {
            "case_count": comparison.sample_size,
            "evaluated_case_count": len(evaluations),
            "trial_count": trial_count,
            "baseline_mean": comparison.baseline_mean,
            "candidate_mean": comparison.candidate_mean,
            "mean_difference": comparison.mean_difference,
            "ci_lower": comparison.ci_lower,
            "ci_upper": comparison.ci_upper,
            "effect_size": comparison.effect_size,
            "confidence": comparison.confidence,
            "direction": comparison.direction.value,
        }

    def _select_observations(
        self, case_id: str, observations: Sequence[SampleObservation]
    ) -> list[SampleObservation]:
        """Filter to one case's observations.

        ``compare`` takes the whole run's observations, so most calls here pass
        observations for other cases. Those are filtered out rather than
        treated as an error; only a case with no observations at all is a
        caller mistake.
        """
        selected = [o for o in observations if o.case_id == case_id]
        if not selected:
            others = sorted({o.case_id for o in observations if o.case_id != case_id})
            raise ValueError(
                f"No observations for case_id {case_id!r}. "
                f"Supplied observations belong to: {others or 'no cases at all'}."
            )
        return selected

    async def _score_observation(
        self,
        observation: SampleObservation,
        *,
        expected: ExpectedBehavior,
        rubric: str | None,
        question: str | None,
        context: str | None,
    ) -> "_ScoredObservation":
        """Score one observation deterministically, and with the judge if enabled."""
        if observation.error:
            return _ScoredObservation(observation=observation, score=0.0, errored=True)

        outcomes = run_deterministic_checks(observation, expected)
        deterministic = applicable_score(outcomes)

        judge_score: float | None = None
        judge_failed = False
        judge_usage: dict[str, int] | None = None
        if rubric and self.judge is not None:
            judge_score, judge_failed, judge_usage = await self._judge_observation(
                observation,
                question=question,
                rubric=rubric,
                context=context,
            )

        if deterministic is None and judge_score is None:
            # Nothing applicable to score. Treat as a neutral pass rather than a
            # failure: the case asked for no assertions we can check.
            blended = 1.0
        elif deterministic is None:
            blended = float(judge_score)
        elif judge_score is None:
            blended = deterministic
        else:
            blended = DETERMINISTIC_WEIGHT * deterministic + (1 - DETERMINISTIC_WEIGHT) * judge_score

        return _ScoredObservation(
            observation=observation,
            score=blended,
            deterministic=deterministic,
            judge=judge_score,
            judge_failed=judge_failed,
            judge_usage=judge_usage,
            outcomes=outcomes,
        )

    async def _judge_observation(
        self,
        observation: SampleObservation,
        *,
        question: str | None,
        rubric: str,
        context: str | None,
    ) -> tuple[float | None, bool, dict[str, int] | None]:
        """Return ``(judge_score, failed, usage)``; never raises."""
        assert self.judge is not None  # guarded by the caller
        request = JudgeRequest(
            case_id=observation.case_id,
            question=question or "",
            answer_text=observation.answer.text,
            rubric=rubric or DEFAULT_RUBRIC,
            criteria=self.judge_criteria or self.judge.criteria,
            context=context,
        )
        try:
            if hasattr(self.judge, "judge_with_meta"):
                output, response = await self.judge.judge_with_meta(request)
            else:
                output = await self.judge.judge(request)
                response = None
        except JudgeError:
            return None, True, None
        return output.score, False, response.usage if response is not None else None

    @staticmethod
    def _aggregate_case(
        case_id: str, scored: Sequence["_ScoredObservation"]
    ) -> CaseEvaluation:
        """Collapse repeated trials into one score per version."""
        by_version: dict[str, list[_ScoredObservation]] = {}
        for item in scored:
            by_version.setdefault(item.observation.version, []).append(item)

        trial_counts: dict[str, int] = {}
        scores: dict[str, float] = {}
        deterministic_scores: dict[str, float] = {}
        judge_scores: dict[str, float] = {}
        gaps: dict[tuple[str, EvidenceKind], MissingEvidence] = {}
        failing: set[CheckKind] = set()
        errors = 0
        judge_failures = 0
        judge_usage: dict[str, int] = {}

        for version, items in by_version.items():
            trial_counts[version] = len(items)
            scores[version] = sum(item.score for item in items) / len(items)

            deterministic = [item.deterministic for item in items if item.deterministic is not None]
            if deterministic:
                deterministic_scores[version] = sum(deterministic) / len(deterministic)

            judge = [item.judge for item in items if item.judge is not None]
            if judge:
                judge_scores[version] = sum(judge) / len(judge)

            for item in items:
                errors += int(item.errored)
                judge_failures += int(item.judge_failed)
                judge_usage = _merge_usage(judge_usage, item.judge_usage)
                for outcome in item.outcomes:
                    if outcome.applicable and not outcome.passed:
                        failing.add(outcome.kind)
                for gap in item.missing_evidence():
                    key = (version, gap.kind)
                    if key in gaps:
                        gaps[key] = gaps[key].model_copy(
                            update={"occurrences": gaps[key].occurrences + 1}
                        )
                    else:
                        gaps[key] = gap

        return CaseEvaluation(
            case_id=case_id,
            trial_counts=trial_counts,
            scores_by_version=scores,
            deterministic_scores_by_version=deterministic_scores,
            judge_scores_by_version=judge_scores,
            judge_failures=judge_failures,
            judge_usage=judge_usage,
            errors=errors,
            missing_evidence=list(gaps.values()),
            failing_checks=sorted(failing, key=lambda kind: _CHECK_ORDER.index(kind)),
            observations_scored=len(scored),
        )

    @staticmethod
    def _guard_event_loop(sync_name: str, async_name: str) -> None:
        """Fail fast instead of deadlocking when called from async code."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        raise RuntimeError(
            f"{sync_name}() cannot be called from a running event loop; "
            f"await {async_name}() instead."
        )


class _ScoredObservation:
    """One observation plus its scores. Internal to the service."""

    __slots__ = (
        "observation",
        "score",
        "deterministic",
        "judge",
        "judge_failed",
        "judge_usage",
        "errored",
        "outcomes",
    )

    def __init__(
        self,
        *,
        observation: SampleObservation,
        score: float,
        deterministic: float | None = None,
        judge: float | None = None,
        judge_failed: bool = False,
        judge_usage: dict[str, int] | None = None,
        errored: bool = False,
        outcomes: Sequence[CheckOutcome] | None = None,
    ) -> None:
        self.observation = observation
        self.score = score
        self.deterministic = deterministic
        self.judge = judge
        self.judge_failed = judge_failed
        self.judge_usage = dict(judge_usage or {})
        self.errored = errored
        self.outcomes = list(outcomes or [])

    def missing_evidence(self) -> list[MissingEvidence]:
        """Evidence this observation was required to supply but did not."""
        gaps: list[MissingEvidence] = []
        for outcome in self.outcomes:
            if outcome.applicable and not outcome.passed:
                kind = _MISSING_EVIDENCE_BY_CHECK.get(outcome.kind)
                if kind is None:
                    continue
                gaps.append(
                    MissingEvidence(
                        case_id=self.observation.case_id,
                        version=self.observation.version,
                        kind=kind,
                        detected_by=outcome.kind,
                        rationale=outcome.rationale,
                        evidence_ids=list(outcome.evidence_ids),
                    )
                )
        return gaps


def _merge_usage(target: dict[str, int], source: Mapping[str, int]) -> dict[str, int]:
    """Add one usage dictionary into another without losing token classes."""
    for key, value in source.items():
        target[key] = target.get(key, 0) + int(value)
    return target


def _sum_usage(values: Iterable[Mapping[str, int]]) -> dict[str, int]:
    """Sum usage dictionaries, preserving keys such as prompt_tokens."""
    total: dict[str, int] = {}
    for value in values:
        _merge_usage(total, value)
    return total


def _stable_unique(values: Iterable[str]) -> list[str]:
    """Deduplicate while preserving first-seen order."""
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered
