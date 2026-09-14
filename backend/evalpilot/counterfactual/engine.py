"""Counterfactual replay: re-run a failing case with one behaviour switched off.

What this engine is for
-----------------------
An evaluation run says *what* regressed. It does not say *why*. The candidate
here is one version with two declared behaviours a caller can undo — the
compression step that drops mandatory clauses, and the missing security guard
that lets a credential through — so the way to attribute a failure is to re-run
the failing case under each of them and see which one moves the score.

How a claim is grounded
-----------------------
Every experiment is built from three measured things and nothing else:

1. the **original** arm, re-executed from the same case input the run used, so
   both arms pass through the identical pipeline;
2. the **replayed** arm, the same input under one intervention;
3. the **scores** the deterministic checks assign to each, from the same
   expectation the run was scored against.

The rationale is rendered from those numbers rather than written first. A
verdict is never asserted independently of the replay that produced it.

What each verdict means
-----------------------
The decision is on *delta* — counterfactual score minus original score, where a
positive delta means the intervention recovered the failure:

``root_cause``
    The intervention restored the case to a clean pass. The single behaviour
    accounts for the whole failure. Note that "whole failure" means the failing
    checks it was failing on: a case can score 0.5 on its way to failing, and
    an intervention that clears every failing check is still the cause of the
    failure, not half of it.
``partial``
    The score moved but failing checks remain. The behaviour contributes; it is
    not the whole story.
``no_effect``
    The score did not move. This is a *result*, not a non-result: the
    hypothesis was tested and rejected. It is also what an ordinary control
    must produce.
``inconclusive``
    The replay established nothing — usually because the citation the caller
    supplied does not resolve to persisted evidence, or no expectation was
    supplied to score a replayed answer against.

Not a general-purpose replay harness
------------------------------------
The intervention vocabulary is closed (two behaviours plus the control), and
the replayed arm is always the ``candidate`` version: the question is "would
this case, with this behaviour restored, have passed?". Widening either is a
change to the engine's contract, not a configuration.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from evalpilot import engine_mapping
from evalpilot.clock import new_id, utc_now
from evalpilot.evaluation import run_deterministic_checks
from evalpilot.evaluation.checks import applicable_score
from evalpilot.executor import ExecutionResult, execute_case
from evalpilot.fixtures import scenario_by_id
from evalpilot.models import Evidence, TestCase
from evalpilot.tools import ToolRegistry

from .models import (
    CounterfactualTarget,
    ExperimentResult,
    ExperimentVerdict,
    ReplayRunResult,
    ReplayRunSummary,
)
from .reading import (
    REPLAY_CONDITION_KEY,
    REPLAY_EVIDENCE_KIND,
    InvestigationReadingSource,
    resolve_evidence,
)

#: Below this much score recovery there is no effect to report. A smaller move
#: is not separable from scoring granularity, and calling it ``partial`` would
#: turn a control into a finding.
MIN_EFFECT_DELTA = 0.05

#: A replayed case at or above this score has passed. Matches the pass bar used
#: everywhere else in the backend (``score >= 1.0`` is a passing case).
PASS_SCORE = 1.0

#: Score at or below which the original failure is treated as complete, which is
#: what separates ``root_cause`` from ``partial``. A case that was already
#: scoring 0.5 for an unrelated reason cannot have *all* of its failure
#: attributed to this one behaviour.
FULL_FAILURE_SCORE = 0.0


class CounterfactualEngine:
    """Replays failing cases under interventions and classifies the result.

    Args:
        source: The evidence seam. Read for the original answer; written with
            each arm's observation. The engine holds no other state and
            persists nothing outside this object.
        registry: Tool registry used for replays. Defaults to the allowlisted
            registry, so the engine is usable with no setup.
        confidence_threshold: Recovery above which an intervention is treated as
            explaining the failure rather than merely moving it.

    The engine is deterministic between calls: two ``replay`` calls with the
    same target and the same source contents return equal scores, verdicts and
    rationales.
    """

    def __init__(
        self,
        *,
        source: InvestigationReadingSource,
        registry: ToolRegistry | None = None,
        confidence_threshold: float = 0.9,
        executor: Callable[..., ExecutionResult] | None = None,
    ) -> None:
        self.source = source
        self.confidence_threshold = confidence_threshold
        self.executor = executor or execute_case
        # No python tool: a replay must not be able to execute arbitrary input
        # (``CLAUDE.md`` non-negotiable #4).
        self.registry = registry or ToolRegistry(enable_python=False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def replay(
        self, target: CounterfactualTarget, *, investigation_id: str | None = None
    ) -> ExperimentResult:
        """Replay one failing case under one intervention and classify it.

        ``investigation_id`` is echoed onto the result so the caller can persist
        it directly; when omitted a fresh uuid is used, which keeps the result
        valid as a standalone artifact.
        """
        investigation_id = investigation_id or new_id()

        case, issue = self._rebuild_case(target)
        if issue is not None:
            return self._inconclusive(target, investigation_id, issue)
        assert case is not None  # _rebuild_case returns one or the other

        original = self._measure(case, intervention=None)
        self._attribute_original(target, original)
        # A control replays the case unmodified. It is not a formality: it is
        # how a caller proves the replay path itself is faithful, and how the
        # engine proves it changed nothing by accident.
        replayed = self._measure(case, intervention=target.intervention.executor_value)

        return self._classify(target, investigation_id, original, replayed)

    def replay_batch(
        self,
        targets: Sequence[CounterfactualTarget],
        *,
        investigation_id: str | None = None,
    ) -> ReplayRunSummary:
        """Replay every target, one experiment each, in the order supplied.

        No aggregation into a single verdict: two experiments on two different
        cases support two claims, and summing them would produce a claim
        neither replay tested.
        """
        return ReplayRunSummary(
            run_id=targets[0].run_id if targets else "",
            investigation_id=investigation_id or new_id(),
            experiments=[
                self.replay(target, investigation_id=investigation_id)
                for target in targets
            ],
        )

    # ------------------------------------------------------------------
    # Preconditions
    # ------------------------------------------------------------------

    def _rebuild_case(self, target: CounterfactualTarget) -> tuple[TestCase | None, str | None]:
        """Rebuild the case to replay, or explain why it cannot be rebuilt.

        The ``TestCase`` is constructed rather than read from the store: this
        package must not depend on the repository, and every field it needs is
        either on the target or in the persisted evidence. The scenario's
        declared input is the authority for the question, so a target carrying
        a question the scenario does not ask is rejected rather than replayed
        under a prompt the run never used.
        """
        try:
            scenario = scenario_by_id(target.scenario_id)
        except KeyError:
            return None, (
                f"Scenario {target.scenario_id!r} is not in the fixture set, so the "
                "case this failure refers to cannot be re-executed."
            )

        rows, missing = resolve_evidence(self.source, target.original_evidence_ids)
        if missing:
            return None, (
                f"Cited evidence {', '.join(repr(item) for item in missing)} does not "
                "exist, so the original observation cannot be grounded."
            )

        expected = target.expected or _expected_from_rows(rows)
        if not expected:
            return None, (
                "No expectation was supplied for "
                f"{target.scenario_id!r} and none was found in the cited evidence "
                f"({', '.join(repr(item) for item in target.original_evidence_ids) or 'none cited'}), "
                "so a replayed answer could not be scored against anything."
            )

        stored_question = str(expected.get("question") or "")
        question = target.question or stored_question or scenario.question
        if question != scenario.question:
            return None, (
                f"Question for {target.scenario_id!r} does not match the fixture "
                "scenario, so a replay would not reproduce the executed case."
            )

        return (
            TestCase(
                id=target.test_case_id,
                run_id=target.run_id,
                title=f"{target.scenario_id} [candidate]",
                category=scenario.category,  # type: ignore[arg-type]
                input={
                    "scenario_id": target.scenario_id,
                    "question": question,
                    "version_label": target.version_label or "candidate",
                    **({"browser_url": target.browser_url} if target.browser_url else {}),
                    **({"browser_actions": target.browser_actions} if target.browser_actions else {}),
                },
                expected=expected,
                difficulty=scenario.difficulty,
                status="failed",
                version="candidate",
                output=None,
            ),
            None,
        )

    # ------------------------------------------------------------------
    # Measurement
    # ------------------------------------------------------------------

    def _measure(
        self, case: TestCase, *, intervention: str | None
    ) -> ReplayRunResult:
        """Execute one arm and score it with the engine's own checks.

        The score is not re-derived here. It comes from
        :func:`~evalpilot.evaluation.checks.run_deterministic_checks` and
        :func:`~evalpilot.evaluation.checks.applicable_score` — the same two
        functions the run's own report was scored with — so a counterfactual
        score and an original score are comparable by construction.

        ``execute_case`` takes a ``Database`` for the artefact it writes. The
        reading source satisfies that one method, and passing it keeps this
        package's dependency surface at exactly the protocol it already needs.
        """
        executed = self.executor(case, self.registry, self.source, intervention=intervention)
        output = executed.output

        # ``execute_case`` returns its evidence rather than persisting it — the
        # runner does that — so a replay has to do the same, or the ids it
        # reports would point at rows that do not exist.
        evidence_ids = [self.source.add_evidence(item).id for item in executed.evidence]

        scored_case = case.model_copy(update={"status": "passed", "output": output})
        observation = engine_mapping.to_observation(scored_case, executed.evidence)
        outcomes = run_deterministic_checks(
            observation, engine_mapping.to_expected_behavior(case.expected)
        )
        score = applicable_score(outcomes)
        failing = [
            outcome.kind.value
            for outcome in outcomes
            if outcome.applicable and not outcome.passed
        ]

        return ReplayRunResult(
            scenario_id=str(output.get("scenario_id", "")),
            run_id=case.run_id,
            test_case_id=case.id,
            intervention=intervention,
            version=case.version,
            answer=str(output.get("answer") or ""),
            refused=bool(output.get("refused")),
            citations=[str(uri) for uri in output.get("citations") or []],
            latency_ms=int(output.get("latency_ms") or 0),
            score=score,
            passed=None if score is None else score >= PASS_SCORE,
            failing_checks=failing,
            check_rationales=[
                outcome.rationale for outcome in outcomes if outcome.applicable
            ],
            evidence_ids=evidence_ids,
        )

    def _attribute_original(
        self, target: CounterfactualTarget, original: ReplayRunResult
    ) -> None:
        """Give the original arm a persisted handle when the caller cited none.

        The replayed arm's evidence is written by ``_measure``. The original arm
        has to be written here, once, so the experiment can cite both arms and
        the claim survives the process that made it.
        """
        if target.original_evidence_ids:
            # Already on disk; reuse the caller's id rather than writing a
            # duplicate row that says the same thing.
            original.original_evidence_id = target.original_evidence_ids[0]
            return

        original.original_evidence_id = self._write_arm_evidence(
            target, condition="original", result=original
        ).id

    def _write_arm_evidence(
        self,
        target: CounterfactualTarget,
        *,
        condition: str,
        result: ReplayRunResult,
    ) -> Evidence:
        """Persist one arm's answer, score and check rationales as evidence."""
        return self.source.add_evidence(
            Evidence(
                id=new_id(),
                run_id=target.run_id,
                test_case_id=target.test_case_id,
                kind=REPLAY_EVIDENCE_KIND,
                uri=None,
                payload={
                    REPLAY_CONDITION_KEY: condition,
                    "scenario_id": result.scenario_id,
                    "intervention": result.intervention,
                    "answer": result.answer,
                    "refused": result.refused,
                    "score": result.score,
                    "passed": result.passed,
                    "failing_checks": list(result.failing_checks),
                    "check_rationales": list(result.check_rationales),
                },
                created_at=utc_now(),
            )
        )

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def _classify(
        self,
        target: CounterfactualTarget,
        investigation_id: str,
        original: ReplayRunResult,
        replayed: ReplayRunResult,
    ) -> ExperimentResult:
        """Turn two measured observations into one grounded verdict."""
        evidence_ids = _ordered_evidence_ids(original, replayed)

        if original.score is None or replayed.score is None:
            return self._result(
                target,
                investigation_id,
                original=original,
                replayed=replayed,
                verdict=ExperimentVerdict.INCONCLUSIVE,
                evidence_ids=evidence_ids,
                rationale=(
                    "No deterministic check was applicable to one of the two arms, "
                    "so there is no score to compare."
                ),
                confidence=0.0,
            )

        delta = replayed.score - original.score
        verdict, confidence, sentence = self._decide(original, replayed, delta)

        return self._result(
            target,
            investigation_id,
            original=original,
            replayed=replayed,
            verdict=verdict,
            evidence_ids=evidence_ids,
            rationale=self._render_rationale(target, original, replayed, delta, sentence),
            confidence=confidence,
            delta=delta,
        )

    def _decide(
        self,
        original: ReplayRunResult,
        replayed: ReplayRunResult,
        delta: float,
    ) -> tuple[ExperimentVerdict, float, str]:
        """Apply the decision rule. Returns ``(verdict, confidence, sentence)``.

        The rule is intentionally about *checks*, not about a score threshold:
        a case passes when it satisfies every check it is scored on, so an
        intervention that clears each previously failing check has accounted
        for the failure, whatever fraction of the score the case happened to
        hold on the way there.
        """
        assert original.score is not None and replayed.score is not None
        was_failing = original.score < PASS_SCORE
        cleared_checks = set(original.failing_checks) - set(replayed.failing_checks)

        if delta <= 0:
            if was_failing:
                return (
                    ExperimentVerdict.NO_EFFECT,
                    1.0,
                    (
                        "Restoring this behaviour changed nothing: the case fails "
                        "identically with and without it, so this behaviour is not "
                        "the cause of this failure."
                    ),
                )
            return (
                ExperimentVerdict.NO_EFFECT,
                1.0,
                (
                    "The case did not regress under this condition to begin with, so "
                    "there is nothing for the intervention to restore. This is the "
                    "expected result for a control."
                ),
            )

        if not cleared_checks and delta < MIN_EFFECT_DELTA:
            # A move this small with no check cleared is scoring granularity, not
            # an effect. Reporting it as ``partial`` would turn a control — or
            # pure noise — into a finding.
            return (
                ExperimentVerdict.NO_EFFECT,
                0.5,
                (
                    f"The score moved by only {delta:.2f} and no failing check was "
                    "cleared, which is too small to attribute to this behaviour."
                ),
            )

        # delta > 0 and something actually changed.
        now_passing = replayed.score >= PASS_SCORE
        if was_failing and now_passing and not replayed.failing_checks:
            failures = ", ".join(original.failing_checks) or "the failing check"
            return (
                ExperimentVerdict.ROOT_CAUSE,
                1.0,
                (
                    f"With this behaviour restored the case passes with no failing "
                    f"check remaining, and the failure it was reported for "
                    f"({failures}) is gone: this behaviour accounts for the failure."
                ),
            )
        return (
            ExperimentVerdict.PARTIAL,
            min(1.0, delta),
            (
                f"The intervention recovered {delta:.2f} of the lost score but the "
                "case still fails, so this behaviour contributes to the failure "
                "without accounting for all of it."
            ),
        )

    # ------------------------------------------------------------------
    # Result builders
    # ------------------------------------------------------------------

    def _inconclusive(
        self, target: CounterfactualTarget, investigation_id: str, reason: str
    ) -> ExperimentResult:
        """A replay that established nothing, with the reason why.

        Confidence is zero and no scores are reported: an ungrounded experiment
        that carries numbers is worse than one that carries none, because the
        numbers outlive the caveat.
        """
        return self._result(
            target,
            investigation_id,
            original=None,
            replayed=None,
            verdict=ExperimentVerdict.INCONCLUSIVE,
            evidence_ids=list(target.original_evidence_ids),
            rationale=f"No replay was performed. {reason}",
            confidence=0.0,
        )

    def _result(
        self,
        target: CounterfactualTarget,
        investigation_id: str,
        *,
        original: ReplayRunResult | None,
        replayed: ReplayRunResult | None,
        verdict: ExperimentVerdict,
        evidence_ids: list[str],
        rationale: str,
        confidence: float,
        delta: float | None = None,
    ) -> ExperimentResult:
        """Assemble the experiment row, including the metrics the UI reads."""
        original_score, score_source = self._original_score(target, original)

        if (
            delta is None
            and original_score is not None
            and replayed is not None
            and replayed.score is not None
        ):
            delta = replayed.score - original_score

        persisted = self._persisted_original_score(target)
        metrics: dict[str, object] = {
            "replayed_original_score": None if original is None else original.score,
            "replayed_counterfactual_score": None if replayed is None else replayed.score,
            "replayed_original_failing_checks": (
                [] if original is None else list(original.failing_checks)
            ),
            "original_failed_completely": (
                None if original is None or original.score is None
                else original.score <= FULL_FAILURE_SCORE
            ),
            "original_answer": None if original is None else original.answer,
            "counterfactual_answer": None if replayed is None else replayed.answer,
            "check_rationales": [] if replayed is None else list(replayed.check_rationales),
            # The clause the intervention restored, as a direct string diff.
            # This is what a human reads to see *what* came back, rather than
            # having to take the score's word for it.
            "restored_text": _restored_text(original, replayed),
            "reported_original_score": target.original_score,
            "persisted_original_score": persisted,
            "confidence_threshold": self.confidence_threshold,
            "target_failing_checks": list(target.failing_checks),
        }

        return ExperimentResult(
            investigation_id=investigation_id,
            scenario_id=target.scenario_id,
            run_id=target.run_id,
            test_case_id=target.test_case_id,
            intervention=target.intervention.value,
            verdict=verdict,
            original_score=original_score,
            original_score_source=score_source,
            counterfactual_score=None if replayed is None else replayed.score,
            delta=delta,
            confidence=confidence,
            evidence_ids=evidence_ids,
            rationale=rationale,
            metrics=metrics,
            original=original,
            replayed=replayed,
        )

    def _original_score(
        self, target: CounterfactualTarget, original: ReplayRunResult | None
    ) -> tuple[float | None, str]:
        """The original arm's score, and where it came from.

        The replayed arm's measurement always wins: it was produced by the same
        pipeline as the counterfactual score, which is what makes the delta
        mean anything. A score persisted by the original run is preferred to the
        caller's copy of it when both exist, because the run's own record is the
        one that can be re-checked.
        """
        if original is not None and original.score is not None:
            return original.score, "evidence"
        persisted = self._persisted_original_score(target)
        if persisted is not None:
            return persisted, "evidence"
        if target.original_score is not None:
            return target.original_score, "caller"
        return None, "unavailable"

    def _persisted_original_score(self, target: CounterfactualTarget) -> float | None:
        """A score the original run stored in the cited evidence, if any.

        Reported alongside the caller's number so a disagreement between the
        two is visible instead of hidden.
        """
        rows, _ = resolve_evidence(self.source, target.original_evidence_ids)
        for row in rows:
            payload = row.payload if isinstance(row.payload, dict) else {}
            for key in ("score", "deterministic_score"):
                value = payload.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    return float(value)
        return None

    def _render_rationale(
        self,
        target: CounterfactualTarget,
        original: ReplayRunResult,
        replayed: ReplayRunResult,
        delta: float,
        sentence: str,
    ) -> str:
        """Render the rationale from the measured numbers, never before them."""
        restored = _restored_text(original, replayed)
        parts = [
            f"Replayed {target.scenario_id!r} under {target.intervention.value!r}: "
            f"score {_fmt(original.score)} -> {_fmt(replayed.score)} "
            f"(delta {delta:+.2f}). ",
            sentence + " ",
        ]
        if restored:
            parts.append(f"Restored text: {restored!r}. ")
        parts.append(f"Evidence: {', '.join(_ordered_evidence_ids(original, replayed))}.")
        return "".join(parts)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _expected_from_rows(rows: Sequence[Evidence]) -> dict:
    """Read a scored expectation off persisted evidence, if one was stored.

    Returns an empty dict when nothing usable was persisted. That is a real
    outcome, not a bug: the MVP's executor does not record the expectation, so
    a caller that passes none gets ``inconclusive`` with a reason rather than a
    score invented to fill the gap.
    """
    for row in rows:
        payload = row.payload if isinstance(row.payload, dict) else {}
        expected = payload.get("expected")
        if isinstance(expected, dict) and expected:
            return dict(expected)
    return {}


def _ordered_evidence_ids(
    original: ReplayRunResult | None, replayed: ReplayRunResult | None
) -> list[str]:
    """Original-arm evidence first, then the replay's, deduplicated in order.

    Deterministic ordering matters: these ids are persisted and compared between
    investigations, and a list whose order depends on which arm finished first
    makes two identical replays look different.
    """
    ordered: list[str] = []
    for result in (original, replayed):
        if result is None:
            continue
        candidates = list(result.evidence_ids)
        if result.original_evidence_id is not None:
            candidates.insert(0, result.original_evidence_id)
        for evidence_id in candidates:
            if evidence_id and evidence_id not in ordered:
                ordered.append(evidence_id)
    return ordered


def _restored_text(
    original: ReplayRunResult | None, replayed: ReplayRunResult | None
) -> str | None:
    """The text the intervention brought back, or ``None`` if nothing changed.

    A substring match on the answer is enough here because an intervention
    either restores dropped sentences or replaces a disclosure with a refusal.
    If answer shapes get more complex this should become a sentence diff, not
    something cleverer that still assumes an ordering.
    """
    if original is None or replayed is None or original.answer == replayed.answer:
        return None
    if original.answer and original.answer in replayed.answer:
        return replayed.answer.replace(original.answer, "").strip(" .") or None
    return replayed.answer


def _fmt(score: float | None) -> str:
    return "n/a" if score is None else f"{score:.2f}"
