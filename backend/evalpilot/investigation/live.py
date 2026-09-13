"""Live-mode augmentation for the investigation engine.

Everything the investigation does with a model lives here. Model output can
affect control flow only through a bounded, validated replay plan; it never
writes a measured value. :class:`~evalpilot.investigation.service.InvestigationService`
produces the deterministic steps exactly as before; this module adds two more
beside them when — and only when — a provider is installed:

``model_hypotheses``
    A ``risk`` step carrying structured hypotheses the model proposed, plus
    one child ``risk`` step per surviving proposal.
``model_rationale``
    A second ``decision`` step carrying the model's evidence-grounded
    explanation of the decision the engine already reached.

Four invariants hold, and the tests assert each one:

1. **Nothing measured is overwritten.** Model output is merged into a *new*
   step's ``data``; the deterministic steps are never touched, and the release
   decision is persisted before the rationale call is made.
2. **Every claim cites existing evidence.** A proposal citing a scenario that
   does not exist in the run is discarded, and the child step's evidence ids
   come from the run, not from the model.
3. **A failure is a fallback, not an error.** An investigation with an
   unreachable model still completes, and the step records
   ``data.fallback_reason``.
4. **Provenance is recorded.** Every step the model contributed to carries
   ``data.source``, ``data.model`` and ``data.llm_call_id``.
"""

from __future__ import annotations

import asyncio
from typing import Any

from evalpilot.llm.apply import (
    sanitize_hypotheses,
    sanitize_rationale,
    sanitize_replay_interventions,
)
from evalpilot.llm.errors import (
    LLMError,
    LLMResponseError,
    LLMSchemaError,
    LLMTimeoutError,
)
from evalpilot.llm.prompts import (
    HYPOTHESIS_KINDS,
    HYPOTHESIS_SCHEMA,
    RATIONALE_SCHEMA,
    REPLAY_INTERVENTIONS,
    build_hypothesis_prompt,
    build_rationale_prompt,
)
from evalpilot.models import (
    EventType,
    InvestigationStep,
    InvestigationStepKind,
    ReleaseDecision,
    StepStatus,
)

from .sources import (
    LLM_DATA_KEYS,
    MEASURED_DATA_KEYS,
    SOURCE_DETERMINISTIC,
    SOURCE_LLM,
)


def _service_helpers():
    """The engine's own aggregation helpers, imported lazily.

    ``service`` imports this module's :class:`LiveLLMAugmenter`, so a
    top-level back-import here would be a cycle. Deferring it keeps the
    dependency one-way at import time while still reusing one implementation of
    ``_ordered_unique`` and friends rather than copying them.
    """
    from .service import _dominant_intervention, _ordered_unique, _tally

    return _ordered_unique, _tally, _dominant_intervention

#: The two steps live mode adds.
MODEL_HYPOTHESES_TITLE = "Model-proposed risk hypotheses"
MODEL_REPLAY_PLAN_TITLE = "Model-guided counterfactual plan"
MODEL_REASONING_TITLE = "Model release rationale"


class LiveLLMAugmenter:
    """Adds model-proposed hypotheses and a model rationale to an investigation.

    Constructed with the collaborators it needs rather than reaching into the
    service, so the service's own surface does not grow.
    """

    def __init__(self, *, repo: Any, runtime: Any) -> None:
        self.repo = repo
        self.runtime = runtime

    # -- entry points --------------------------------------------------------

    async def hypotheses(
        self,
        recorder: Any,
        root: InvestigationStep,
        intake: Any,
        deterministic: dict[str, InvestigationStep],
    ) -> dict[str, str]:
        """Ask for risk hypotheses and a bounded replay plan.

        A valid replay choice can affect which experiment the execution layer
        runs next. It cannot write a score or verdict: the chosen experiment is
        executed and its measured result is what enters the decision.
        """
        if not self.runtime.live:
            return {}

        objective = self.repo.get_investigation(root.investigation_id).objective
        known_scenarios = {item.scenario_id for item in intake.scenarios}
        step = recorder.open(
            InvestigationStepKind.RISK,
            MODEL_HYPOTHESES_TITLE,
            "Requesting additional risk hypotheses from the configured model.",
            data={
                "source": SOURCE_LLM,
                "model": self.runtime.model,
                "objective": objective,
            },
            parent_id=root.id,
            status=StepStatus.RUNNING,
        )

        messages = build_hypothesis_prompt(
            objective=objective,
            baseline_version=intake.run.baseline_version,
            candidate_version=intake.run.candidate_version,
            matched_scenarios=intake.matched_scenarios,
            baseline_pass_rate=intake.baseline_pass_rate,
            candidate_pass_rate=intake.candidate_pass_rate,
            direction=intake.direction,
            regressed=[
                {
                    "scenario_id": item.scenario_id,
                    "category": item.category,
                    "baseline_score": round(item.baseline_score, 4),
                    "candidate_score": round(item.candidate_score, 4),
                    "missing_facts": list(item.missing_facts),
                    "leaked_markers": list(item.leaked_markers),
                    "failed_checks": list(item.failed_checks),
                }
                for item in intake.regressed
            ],
            controls=[
                item.scenario_id
                for item in intake.scenarios
                if item.delta == 0 and item.candidate_score >= 1.0
            ],
            existing_hypotheses=[
                str(existing.data.get("kind") or existing.title)
                for existing in deterministic.values()
            ],
        )

        result = None
        last_repairable: Exception | None = None
        planner_attempts = 0
        for attempt in range(1, 3):
            planner_attempts = attempt
            try:
                result = await self._complete_json(messages, HYPOTHESIS_SCHEMA)
                break
            except (LLMResponseError, LLMSchemaError) as exc:
                # A malformed or schema-invalid response is repairable: retry
                # once before abandoning the bounded planning path.
                last_repairable = exc
                continue
            except LLMError as exc:
                self._fallback(recorder, step, root, _failure("hypotheses", exc))
                return {}
        if result is None:
            assert last_repairable is not None
            self._fallback(
                recorder,
                step,
                root,
                _failure("hypotheses", last_repairable),
                provenance={"planner_attempts": planner_attempts},
            )
            return {}

        ordered_unique, _, _ = _service_helpers()
        proposals, discarded = sanitize_hypotheses(
            result.payload,
            known_scenarios=known_scenarios,
            known_kinds=HYPOTHESIS_KINDS,
        )
        regressed_scenarios = {item.scenario_id for item in intake.regressed}
        replay_plan, replay_discarded = sanitize_replay_interventions(
            result.payload,
            known_scenarios=regressed_scenarios,
            allowed_interventions=REPLAY_INTERVENTIONS,
        )
        if not proposals and not replay_plan:
            reasons = [*discarded, *replay_discarded]
            self._fallback(
                recorder,
                step,
                root,
                (
                    "the model proposed no usable hypothesis or replay action"
                    if not reasons
                    else "every model contribution was discarded: " + "; ".join(reasons)
                ),
                provenance=result.provenance(),
            )
            return {}

        created: list[dict[str, Any]] = []
        for proposal in proposals:
            scenarios = [
                item
                for item in intake.scenarios
                if item.scenario_id in proposal["scenarios"]
            ]
            evidence_ids = ordered_unique(
                eid for item in scenarios for eid in item.regression_evidence()
            )
            if not evidence_ids:
                discarded.append(
                    f"hypothesis {proposal['kind']!r} had no evidence to cite"
                )
                continue
            confidence = proposal["confidence"]
            recorded = recorder.open(
                InvestigationStepKind.RISK,
                proposal["claim"],
                (
                    f"Model-proposed hypothesis ({proposal['kind']}): "
                    f"{proposal['mechanism']}"
                    + (
                        f" Confidence {confidence:.2f}."
                        if confidence is not None
                        else ""
                    )
                ),
                data={
                    "source": SOURCE_LLM,
                    "model": result.model,
                    "llm_call_id": result.call_id,
                    "kind": proposal["kind"],
                    "label": proposal["claim"],
                    "mechanism": proposal["mechanism"],
                    "scenarios": proposal["scenarios"],
                    "model_confidence": confidence,
                    # The rule does not change with the mode: this is a
                    # hypothesis, not a finding, and it is recorded as such.
                    "authoritative": False,
                },
                evidence_ids=evidence_ids,
                parent_id=root.id,
                status=StepStatus.COMPLETED,
            )
            created.append(
                {
                    "step_id": recorded.id,
                    "kind": proposal["kind"],
                    "scenarios": proposal["scenarios"],
                }
            )

        plan_map: dict[str, str] = {}
        if replay_plan:
            plan_ids = {entry["scenario_id"] for entry in replay_plan}
            plan_scenarios = [
                item for item in intake.regressed if item.scenario_id in plan_ids
            ]
            plan_evidence = ordered_unique(
                eid
                for item in plan_scenarios
                for eid in item.regression_evidence()
            )
            if plan_evidence:
                plan_map = {
                    entry["scenario_id"]: entry["intervention"]
                    for entry in replay_plan
                }
                recorder.open(
                    InvestigationStepKind.COUNTERFACTUAL,
                    MODEL_REPLAY_PLAN_TITLE,
                    (
                        f"The model proposed {len(replay_plan)} bounded counterfactual "
                        "experiment(s). Each choice is executed and measured; it is "
                        "not treated as causal until the replay recovers the failure."
                    ),
                    data={
                        "source": SOURCE_LLM,
                        "model": result.model,
                        "llm_call_id": result.call_id,
                        "replay_plan": replay_plan,
                        "authoritative": False,
                    },
                    evidence_ids=plan_evidence,
                    parent_id=root.id,
                    status=StepStatus.COMPLETED,
                )
            else:
                replay_discarded.append(
                    "the replay plan had no evidence linked to its scenarios"
                )
                replay_plan = []

        if not created and not plan_map:
            self._fallback(
                recorder,
                step,
                root,
                "no model contribution could cite existing evidence",
                provenance=result.provenance(),
            )
            return {}

        self._merge(
            step,
            {
                "proposals": created,
                "discarded": discarded,
                "replay_plan": replay_plan,
                "replay_plan_rejected": replay_discarded,
                "authoritative": False,
                "deterministic_hypothesis_count": len(deterministic),
                "planner_attempts": planner_attempts,
                "planner_repaired": planner_attempts > 1,
                # The step itself is model-generated, so it carries the same
                # provenance its child steps do.
                **result.provenance(),
            },
        )
        recorder.close(
            step,
            (
                f"The model proposed {len(created)} additional hypothesis(es) "
                f"and {len(plan_map)} bounded replay experiment(s) alongside "
                f"the {len(deterministic)} deterministic hypothesis(es). The "
                "release decision still comes from measured scenarios and "
                "counterfactual results."
            ),
        )
        self._event(
            root.investigation_id,
            EventType.TASK_COMPLETED,
            (
                f"{len(created)} model hypothesis(es) and {len(plan_map)} "
                "model-guided replay experiment(s) recorded as advisory."
            ),
            {
                "model": result.model,
                "llm_call_id": result.call_id,
                "kinds": [item["kind"] for item in created],
                "replay_plan": replay_plan,
                "replay_plan_rejected": replay_discarded,
                "discarded": discarded,
            },
        )
        return plan_map

    async def rationale(
        self,
        recorder: Any,
        root: InvestigationStep,
        intake: Any,
        decision: ReleaseDecision,
    ) -> None:
        """Ask for an explanation of the measured decision. No-op when offline.

        The decision is already persisted by the caller, and this cannot change
        it: the step records the measured verdict alongside whatever the model
        said, and a disagreement is surfaced rather than acted on.
        """
        if not self.runtime.live:
            return

        objective = self.repo.get_investigation(root.investigation_id).objective
        step = recorder.open(
            InvestigationStepKind.OBSERVATION,
            MODEL_REASONING_TITLE,
            "Requesting an evidence-grounded rationale for the measured decision.",
            data={
                "source": SOURCE_LLM,
                "model": self.runtime.model,
                "verdict": decision.verdict,
                "risk_level": decision.risk_level,
            },
            parent_id=root.id,
            status=StepStatus.RUNNING,
        )

        blocking_ids = set(decision.blocking_findings)
        blocking_findings = [
            {
                "id": finding.id,
                "severity": finding.severity,
                "title": finding.title,
                "description": finding.description,
                "evidence_ids": list(finding.evidence_ids),
            }
            for finding in intake.run_findings
            if finding.id in blocking_ids
        ]
        # The ids the model may cite. Sanitization intersects against this set,
        # so a citation the model invents is dropped rather than persisted as
        # though the run had produced it.
        ordered_unique, tally, dominant_intervention = _service_helpers()
        allowed_evidence = ordered_unique(
            [
                *(
                    eid
                    for finding in blocking_findings
                    for eid in finding["evidence_ids"]
                ),
                *(
                    eid
                    for item in (*intake.disclosed, *intake.dropped_clause)
                    for eid in item.regression_evidence()
                ),
            ]
        )

        experiments = self.repo.list_counterfactuals(root.investigation_id)
        messages = build_rationale_prompt(
            objective=objective,
            verdict=decision.verdict,
            risk_level=decision.risk_level,
            confidence=decision.confidence,
            measured_summary=decision.summary,
            blocking_findings=blocking_findings,
            dominant_intervention=dominant_intervention(experiments),
            counterfactual_tally=tally(item.verdict for item in experiments),
            evidence_ids=allowed_evidence,
            deterministic_actions=list(decision.recommended_actions),
        )

        try:
            result = await self._complete_json(messages, RATIONALE_SCHEMA)
        except LLMError as exc:
            self._fallback(recorder, step, root, _failure("rationale", exc))
            return

        parsed = sanitize_rationale(
            result.payload,
            allowed_evidence=allowed_evidence,
            measured_verdict=decision.verdict,
            measured_risk=decision.risk_level,
        )
        if not parsed["rationale"]:
            self._fallback(
                recorder,
                step,
                root,
                "the model returned an empty rationale",
                provenance=result.provenance(),
            )
            return

        self._merge(
            step,
            {
                "rationale": parsed["rationale"],
                "llm_evidence_ids": parsed["evidence_ids"],
                "llm_recommendations": parsed["recommendations"],
                "proposed_verdict": parsed["proposed_verdict"],
                "proposed_risk_level": parsed["proposed_risk_level"],
                "verdict_disagreement": parsed["verdict_disagreement"],
                "authoritative": False,
                # The actions a reader acts on, with any model additions
                # appended after the deterministic ones.
                "recommended_actions": ordered_unique(
                    [*parsed["recommendations"], *decision.recommended_actions]
                ),
                **result.provenance(),
            },
        )
        recorder.close(step, parsed["rationale"])

        if parsed["verdict_disagreement"]:
            self._event(
                root.investigation_id,
                EventType.TASK_COMPLETED,
                "Model rationale disagreed with the measured verdict; the measured "
                "verdict stands.",
                {
                    "model": result.model,
                    "llm_call_id": result.call_id,
                    "verdict_disagreement": parsed["verdict_disagreement"],
                },
            )

    # -- internals -----------------------------------------------------------

    async def _complete_json(
        self, messages: list[dict[str, str]], schema: dict[str, Any]
    ):
        """Call the provider under the configured timeout.

        ``asyncio.wait_for`` is belt-and-braces alongside the client's own
        httpx timeout: the client bounds the socket, this bounds the whole
        call. The caller catches :class:`LLMError`; a ``wait_for`` expiry is a
        builtin :class:`TimeoutError` (an ``OSError``, not an ``LLMError``), so
        it is converted here rather than allowed to escape and fail the
        investigation. A provider that ignores ``timeout_seconds`` must still
        produce a recorded fallback.
        """
        provider = self.runtime.provider
        assert provider is not None  # guarded by the `live` check
        try:
            return await asyncio.wait_for(
                provider.complete_json(
                    messages, schema, timeout_seconds=self.runtime.timeout_seconds
                ),
                timeout=self.runtime.timeout_seconds,
            )
        except TimeoutError as exc:
            raise LLMTimeoutError(
                f"LLM call exceeded the {self.runtime.timeout_seconds:g}s timeout"
            ) from exc

    def _merge(self, step: InvestigationStep, data: dict[str, Any]) -> None:
        """Merge model-contributed keys into a step's ``data`` and persist them.

        A merge, not a replacement, and a *filtered* one: a model contribution
        may not write a measured key, and may not introduce a key outside the
        known set. The deterministic keys the step already carries stay exactly
        as written, so adding model commentary can never rewrite a measured
        value — even if an injected provider returns a payload carrying one.

        ``save_step_data`` persists the payload and returns the stored row,
        which is the authoritative copy; keep the merged data on the step the
        caller holds so the in-memory narrative and the persisted row agree.
        """
        measured = MEASURED_DATA_KEYS & set(data)
        if measured:
            raise LLMError(
                "refusing to write measured key(s) from a model contribution: "
                f"{sorted(measured)}"
            )
        unknown = set(data) - LLM_DATA_KEYS
        if unknown:
            raise LLMError(
                f"refusing to write unrecognized key(s) from a model contribution: "
                f"{sorted(unknown)}"
            )
        merged = {**step.data, **data}
        step.data = merged
        stored = self.repo.save_step_data(step.id, merged)
        step.data = stored.data

    def _fallback(
        self,
        recorder: Any,
        step: InvestigationStep,
        root: InvestigationStep,
        reason: str,
        *,
        provenance: dict[str, Any] | None = None,
    ) -> None:
        """Record that the deterministic path stood in, and why.

        The step is kept and closed as completed: an investigation that fell
        back still did what it promised, and hiding the step would hide that a
        model was consulted and declined. ``data.fallback_reason`` is the field
        ``docs/V3_LLM_INTERFACES.md`` asks for.
        """
        self.runtime.record_fallback(reason)
        self._merge(
            step,
            {"fallback_reason": reason, "fallback": True, **(provenance or {})},
        )
        recorder.close(
            step, f"Model unavailable; the deterministic analysis stands. {reason}"
        )
        self._event(
            root.investigation_id,
            EventType.TASK_COMPLETED,
            f"LLM fallback: {reason}",
            {"fallback_reason": reason, "phase": "live-llm"},
        )

    def _event(
        self,
        investigation_id: str,
        type_: EventType,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        self.repo.append_event(
            investigation_id,
            type_,
            message,
            {"investigation_id": investigation_id, **(data or {})},
        )


def _failure(phase: str, exc: BaseException) -> str:
    """One line saying which call failed and how, safe to persist.

    The message comes from :class:`~evalpilot.llm.errors.LLMError`, which never
    contains the API key.
    """
    name = type(exc).__name__
    detail = str(exc).strip()
    return (
        f"{phase} call failed: {name}: {detail}"
        if detail
        else f"{phase} call failed: {name}"
    )


__all__ = [
    "LiveLLMAugmenter",
    "MODEL_HYPOTHESES_TITLE",
    "MODEL_REPLAY_PLAN_TITLE",
    "MODEL_REASONING_TITLE",
    "SOURCE_DETERMINISTIC",
    "SOURCE_LLM",
]
