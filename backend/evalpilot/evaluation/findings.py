"""Severity assignment and finding construction.

The repository contract requires that every evaluation finding links to
evidence. That invariant is enforced in two places:

1. :class:`~evalpilot.evaluation.models.Finding` rejects an empty
   ``evidence_ids`` list at validation time.
2. The builders in this module raise ``ValueError`` when a caller supplies no
   evidence ids, rather than emitting a finding with an empty list.

The second guard exists because builders are the API the service calls: failing
loudly there turns "we forgot to attach evidence" into a visible error instead
of a finding that quietly violates the product contract.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from .models import (
    CheckKind,
    ComparisonDirection,
    EvidenceKind,
    Finding,
    MissingEvidence,
    Severity,
)
from .comparison import ComparisonResult

#: Mean-difference magnitudes that separate severity bands for a regression.
#: A drop smaller than the regression threshold is not a regression at all, so
#: it never reaches these bands.
_SEVERITY_BANDS: tuple[tuple[float, Severity], ...] = (
    (0.40, Severity.CRITICAL),
    (0.25, Severity.HIGH),
    (0.10, Severity.MEDIUM),
)

#: Confidence below which a finding is downgraded one band: an effect we are
#: unsure about should not be reported as loudly as one we are sure about.
_LOW_CONFIDENCE = 0.90


def severity_for(comparison: ComparisonResult) -> Severity:
    """Severity for a comparison result.

    An inconclusive or improving comparison is informational: only a confirmed
    regression is a defect.
    """
    if comparison.direction is not ComparisonDirection.REGRESSION:
        return Severity.INFO

    magnitude = abs(comparison.mean_difference)
    severity = Severity.LOW
    for threshold, band in _SEVERITY_BANDS:
        if magnitude >= threshold:
            severity = band
            break

    if comparison.confidence < _LOW_CONFIDENCE:
        severity = _downgrade(severity)
    return severity


def _downgrade(severity: Severity) -> Severity:
    """Move one band down, never below LOW."""
    order = [Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
    index = order.index(severity)
    return order[max(index - 1, order.index(Severity.LOW))]


#: Severity for each kind of missing evidence.
_MISSING_EVIDENCE_SEVERITY: dict[EvidenceKind, Severity] = {
    EvidenceKind.CITATION: Severity.HIGH,
    EvidenceKind.TRACE: Severity.MEDIUM,
    EvidenceKind.TEXT: Severity.LOW,
    EvidenceKind.LOG: Severity.LOW,
    EvidenceKind.SCREENSHOT: Severity.LOW,
    EvidenceKind.METRIC: Severity.LOW,
}

_MISSING_EVIDENCE_LABEL: dict[EvidenceKind, str] = {
    EvidenceKind.CITATION: "citation",
    EvidenceKind.TRACE: "tool trace",
    EvidenceKind.TEXT: "answer text",
    EvidenceKind.LOG: "log",
    EvidenceKind.SCREENSHOT: "screenshot",
    EvidenceKind.METRIC: "metric",
}


def _require_evidence(evidence_ids: Sequence[str], context: str) -> list[str]:
    """Validate that a finding will carry usable evidence ids."""
    cleaned = [evidence_id for evidence_id in evidence_ids if evidence_id and evidence_id.strip()]
    if not cleaned:
        raise ValueError(
            f"Cannot build a finding for {context} without evidence ids. "
            "Every finding must link to evidence per the product contract."
        )
    return cleaned


def build_comparison_findings(
    *,
    comparison: ComparisonResult,
    case_ids: Sequence[str],
    evidence_ids: Sequence[str],
    title: str,
    description: str,
    recommendation: str | None = None,
    run_id: str | None = None,
) -> list[Finding]:
    """Build findings for a matched comparison.

    Returns a single-element list for a confirmed regression, and an empty list
    for an improvement or an inconclusive result.

    Raises:
        ValueError: if no evidence ids were given. This is checked before the
            direction, so a caller that forgot to attach evidence always hears
            about it rather than having the error masked by an inconclusive
            result.
    """
    evidence = _require_evidence(evidence_ids, f"comparison '{title}'")

    severity = severity_for(comparison)
    if severity is Severity.INFO:
        return []

    finding = Finding(
        run_id=run_id,
        case_id=case_ids[0] if len(case_ids) == 1 else None,
        severity=severity,
        title=title,
        description=description,
        confidence=comparison.confidence,
        evidence_ids=evidence,
        rationale=comparison.rationale,
        recommendation=recommendation
        or (
            "Re-run the affected cases against the previous version to confirm the "
            "regression persists, then inspect the retrieval and prompting changes "
            "that landed between the two versions."
        ),
        metrics={
            "mean_difference": comparison.mean_difference,
            "ci_lower": comparison.ci_lower,
            "ci_upper": comparison.ci_upper,
            "effect_size": comparison.effect_size,
            "sample_size": comparison.sample_size,
            "threshold": comparison.threshold,
            "direction": comparison.direction.value,
        },
    )
    return [finding]


def build_missing_evidence_findings(
    *,
    missing_evidence: Iterable[MissingEvidence],
    evidence_ids_by_case: dict[str, Sequence[str]],
    run_id: str | None = None,
) -> list[Finding]:
    """Build one finding per deduplicated missing-evidence gap.

    Raises:
        ValueError: if any gap has no evidence ids in ``evidence_ids_by_case``.
    """
    findings: list[Finding] = []
    for gap in missing_evidence:
        label = _MISSING_EVIDENCE_LABEL.get(gap.kind, gap.kind.value)
        evidence = _require_evidence(
            evidence_ids_by_case.get(gap.case_id, []),
            f"case {gap.case_id} missing {label}",
        )
        findings.append(
            Finding(
                run_id=run_id,
                case_id=gap.case_id,
                severity=_MISSING_EVIDENCE_SEVERITY.get(gap.kind, Severity.MEDIUM),
                title=f"Missing {label} on {gap.version}",
                description=(
                    f"{gap.rationale} Observed in {gap.occurrences} of the sampled "
                    f"trials for this case."
                ),
                confidence=1.0,  # the absence is deterministic, not estimated
                evidence_ids=evidence,
                rationale=gap.rationale,
                recommendation=(
                    f"Attach {label} evidence to this case before trusting its score, "
                    "or mark the case as not requiring it."
                ),
                metrics={"occurrences": gap.occurrences, "detected_by": gap.detected_by.value},
            )
        )
    return findings


def build_check_failure_findings(
    *,
    case_id: str,
    versions: Sequence[str],
    failing_kinds: Sequence[CheckKind],
    evidence_ids: Sequence[str],
    run_id: str | None = None,
) -> list[Finding]:
    """Build findings for deterministic checks a case failed in both versions.

    Raises:
        ValueError: if no evidence ids were given.
    """
    if not failing_kinds:
        return []

    label = ", ".join(kind.value for kind in failing_kinds)
    evidence = _require_evidence(evidence_ids, f"case {case_id} failing checks '{label}'")

    return [
        Finding(
            run_id=run_id,
            case_id=case_id,
            severity=Severity.MEDIUM,
            title=f"Case fails deterministic checks on {', '.join(versions)}",
            description=(
                f"Checks failed on every compared version: {label}. "
                "The case cannot discriminate between versions until it passes somewhere."
            ),
            confidence=1.0,
            evidence_ids=evidence,
            rationale=f"Deterministic checks {label} failed on all of: {', '.join(versions)}.",
            recommendation=(
                "Fix the case or the shared upstream behaviour; a case that fails "
                "everywhere contributes no regression signal."
            ),
            metrics={"failing_checks": [kind.value for kind in failing_kinds]},
        )
    ]
