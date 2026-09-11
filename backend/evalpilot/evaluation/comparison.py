"""Matched baseline/candidate comparison with uncertainty quantification.

Design notes
------------
**Pairing.** Every statistic here is computed on *difference scores within
matched test cases*. A case that is intrinsically hard contributes the same
difficulty to both arms, so it cancels. This is what stops a hard candidate
test set from reading as a regression.

**Collapsing repeats first.** Trials are collapsed to a per-case mean before
differences are formed. Treating every trial as an independent pair would
inflate the sample size, shrink the interval, and manufacture significance out
of pure sampling noise. Collapsing makes the unit of analysis the case, which
is the unit the intervention actually acts on.

**Effect size.** Cohen's *d* for paired (collapsed) data: mean difference over
the standard deviation of the difference scores. Hedges' *g* for *unpaired*
samples is deliberately not used: it is a between-groups statistic and would
reintroduce exactly the case-difficulty variance that matching removes.

**Bootstrap.** A seeded multiplicative-congruential generator, so results are
bit-for-bit reproducible with no numpy/scipy dependency. The seed moves the
interval only; point estimates never depend on it.

**Decision rule.** Compare the (1 - 2*alpha) confidence interval of the mean
difference against a practical-significance threshold:

- whole interval below ``-threshold`` -> regression
- whole interval above ``+threshold`` -> improvement
- otherwise                        -> inconclusive

This is a confidence-interval rule rather than a p-value test. It answers the
question the product actually asks ("is the drop big enough to matter, and are
we sure?") and reports the degree of belief in ``confidence`` instead of a
binary that hides how close the call was.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from pydantic import Field

from .models import ComparisonDirection, EvaluationModel

#: Smallest mean drop that counts as a real regression rather than drift.
#: 0.05 on a 0..1 score is half of one judge rubric step.
DEFAULT_REGRESSION_THRESHOLD = 0.05

#: One-sided tail probability. 0.025 gives a 95% two-sided interval.
DEFAULT_ALPHA = 0.025

#: Bootstrap resamples. 2000 keeps the interval stable to ~0.002 while staying
#: well under a second for demo-sized case counts.
DEFAULT_RESAMPLES = 2000

#: Below this many matched cases the bootstrap cannot resolve an interval
#: worth acting on, so the result is reported as inconclusive regardless.
MIN_CASES_FOR_SIGNIFICANCE = 3

_LCG_MODULUS = 2**31


class SeedRandom:
    """Deterministic pseudo-random generator.

    A multiplicative congruential generator, implemented locally so that
    bootstrap intervals are reproducible across machines and across Python
    versions without pulling in numpy or scipy.
    """

    __slots__ = ("_state",)

    def __init__(self, seed: int) -> None:
        self._state = seed % _LCG_MODULUS or 1

    def _next(self) -> int:
        self._state = (1103515245 * self._state + 12345) % _LCG_MODULUS
        return self._state

    def random(self) -> float:
        """A float in [0, 1)."""
        return self._next() / _LCG_MODULUS

    def below(self, n: int) -> int:
        """An int in [0, n)."""
        return int(self.random() * n) % n


class ConfidenceInterval(EvaluationModel):
    """A point estimate with a two-sided confidence interval."""

    point: float
    lower: float
    upper: float
    level: float = Field(default=1 - 2 * DEFAULT_ALPHA, ge=0.0, le=1.0)

    @property
    def excludes_zero(self) -> bool:
        """True when the interval lies entirely on one side of zero."""
        return self.lower > 0 or self.upper < 0


class ComparisonResult(EvaluationModel):
    """A matched comparison verdict with its supporting statistics."""

    direction: ComparisonDirection
    mean_difference: float
    std_difference: float
    ci_lower: float
    ci_upper: float
    effect_size: float
    confidence: float = Field(ge=0.0, le=1.0)
    is_significant: bool
    sample_size: int = Field(ge=0)
    trial_count: int = Field(default=0, ge=0)
    threshold: float
    baseline_mean: float = 0.0
    candidate_mean: float = 0.0
    rationale: str = ""


def mean(values: Sequence[float]) -> float:
    """Arithmetic mean; 0.0 for an empty sequence."""
    if not values:
        return 0.0
    return math.fsum(values) / len(values)


def stdev(values: Sequence[float]) -> float:
    """Sample standard deviation (n-1); 0.0 for fewer than two values."""
    if len(values) < 2:
        return 0.0
    centre = mean(values)
    variance = math.fsum((value - centre) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def mean_confidence_interval(
    values: Sequence[float],
    *,
    seed: int = 0,
    alpha: float = DEFAULT_ALPHA,
    resamples: int = DEFAULT_RESAMPLES,
) -> ConfidenceInterval:
    """Percentile bootstrap interval for the mean of ``values``.

    Degenerate for 0 or 1 values (there is no resampling distribution), and
    fully deterministic for a fixed ``seed``.
    """
    level = 1 - 2 * alpha
    if not values:
        return ConfidenceInterval(point=0.0, lower=0.0, upper=0.0, level=level)

    point = mean(values)
    if len(values) == 1:
        return ConfidenceInterval(point=point, lower=point, upper=point, level=level)

    rng = SeedRandom(seed)
    size = len(values)
    bootstrap_means: list[float] = []
    for _ in range(resamples):
        total = 0.0
        for _ in range(size):
            total += values[rng.below(size)]
        bootstrap_means.append(total / size)

    bootstrap_means.sort()
    return ConfidenceInterval(
        point=point,
        lower=_percentile(bootstrap_means, alpha),
        upper=_percentile(bootstrap_means, 1 - alpha),
        level=level,
    )


def _percentile(sorted_values: Sequence[float], quantile: float) -> float:
    """Linear-interpolated percentile of an already-sorted sequence."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]

    position = quantile * (len(sorted_values) - 1)
    low_index = math.floor(position)
    high_index = math.ceil(position)
    if low_index == high_index:
        return sorted_values[int(position)]

    weight = position - low_index
    return sorted_values[low_index] * (1 - weight) + sorted_values[high_index] * weight


def paired_effect_size(differences: Sequence[float]) -> float:
    """Cohen's *d* for paired data: mean difference / SD of differences.

    Returns 0.0 when the differences have no spread, which is the correct
    reading: with zero variance the standardised magnitude is undefined, and
    the decision is already carried by the mean and its interval.
    """
    if len(differences) < 2:
        return 0.0
    spread = stdev(differences)
    if spread == 0:
        return 0.0
    return mean(differences) / spread


def normal_cdf(z: float) -> float:
    """Standard normal CDF via the complementary error function."""
    return 0.5 * math.erfc(-z / math.sqrt(2.0))


def compare_matched_cases(
    pairs: Sequence[tuple[float, float]],
    *,
    seed: int = 0,
    threshold: float = DEFAULT_REGRESSION_THRESHOLD,
    alpha: float = DEFAULT_ALPHA,
    resamples: int = DEFAULT_RESAMPLES,
) -> ComparisonResult:
    """Compare matched ``(baseline, candidate)`` score pairs.

    Args:
        pairs: One ``(baseline_score, candidate_score)`` tuple per matched test
            case. Callers must pass per-case aggregates across trials, not raw
            trials; see the module docstring.
        seed: Bootstrap seed. Reproducible for a fixed seed.
        threshold: Practical-significance threshold for the mean difference.
        alpha: One-sided tail probability.
        resamples: Number of bootstrap resamples.

    Returns:
        A :class:`ComparisonResult`. Fewer than
        :data:`MIN_CASES_FOR_SIGNIFICANCE` matched cases is always inconclusive
        however clean the numbers look.
    """
    if not pairs:
        return ComparisonResult(
            direction=ComparisonDirection.INCONCLUSIVE,
            mean_difference=0.0,
            std_difference=0.0,
            ci_lower=0.0,
            ci_upper=0.0,
            effect_size=0.0,
            confidence=0.0,
            is_significant=False,
            sample_size=0,
            trial_count=0,
            threshold=threshold,
            rationale="No matched cases to compare.",
        )

    differences = [candidate - baseline for baseline, candidate in pairs]
    baselines = [baseline for baseline, _ in pairs]
    candidates = [candidate for _, candidate in pairs]

    mean_difference = mean(differences)
    spread = stdev(differences)
    effect_size = paired_effect_size(differences)
    interval = mean_confidence_interval(
        differences, seed=seed, alpha=alpha, resamples=resamples
    )
    confidence = _confidence_that_difference_clears_threshold(
        mean_difference, spread, len(differences), threshold
    )

    direction, is_significant, rationale = _decide(
        mean_difference=mean_difference,
        ci_lower=interval.lower,
        ci_upper=interval.upper,
        threshold=threshold,
        sample_size=len(pairs),
        confidence=confidence,
    )

    return ComparisonResult(
        direction=direction,
        mean_difference=mean_difference,
        std_difference=spread,
        ci_lower=interval.lower,
        ci_upper=interval.upper,
        effect_size=effect_size,
        confidence=confidence,
        is_significant=is_significant,
        sample_size=len(pairs),
        threshold=threshold,
        baseline_mean=mean(baselines),
        candidate_mean=mean(candidates),
        rationale=rationale,
    )


def _confidence_that_difference_clears_threshold(
    mean_difference: float, spread: float, sample_size: int, threshold: float
) -> float:
    """Confidence that the true mean difference clears a threshold on the
    side the point estimate leans toward.

    With fewer than two matched cases the spread is unknown, so confidence
    stays at chance rather than being invented.

    When the spread is exactly zero *and* the mean clears the threshold, every
    matched case moved by the same amount. That is the strongest possible
    evidence, not the weakest: the interval collapses onto the point estimate,
    so the confidence is total. Returning 0.0 here would invert the meaning of
    the number and mis-downgrade severity for a perfectly consistent
    regression.
    """
    if sample_size < 2:
        return 0.0

    if spread <= 0:
        return 1.0 if abs(mean_difference) > threshold else 0.0

    standard_error = spread / math.sqrt(sample_size)
    if mean_difference < 0:
        # Confidence that the true difference is below -threshold.
        z = (-threshold - mean_difference) / standard_error
    elif mean_difference > 0:
        # Confidence that the true difference is above +threshold.
        z = (mean_difference - threshold) / standard_error
    else:
        return 0.0

    return min(1.0, max(0.0, normal_cdf(z)))


def _decide(
    *,
    mean_difference: float,
    ci_lower: float,
    ci_upper: float,
    threshold: float,
    sample_size: int,
    confidence: float,
) -> tuple[ComparisonDirection, bool, str]:
    """Apply the confidence-interval decision rule."""
    if sample_size < MIN_CASES_FOR_SIGNIFICANCE:
        return (
            ComparisonDirection.INCONCLUSIVE,
            False,
            (
                f"Only {sample_size} matched case(s); at least "
                f"{MIN_CASES_FOR_SIGNIFICANCE} are needed before a change is called."
            ),
        )

    if ci_upper < -threshold:
        return (
            ComparisonDirection.REGRESSION,
            True,
            (
                f"Mean score fell {abs(mean_difference):.3f} "
                f"(95% CI {ci_lower:.3f} to {ci_upper:.3f}), entirely below the "
                f"-{threshold:.3f} regression threshold."
            ),
        )

    if ci_lower > threshold:
        return (
            ComparisonDirection.IMPROVEMENT,
            True,
            (
                f"Mean score rose {mean_difference:.3f} "
                f"(95% CI {ci_lower:.3f} to {ci_upper:.3f}), entirely above the "
                f"+{threshold:.3f} improvement threshold."
            ),
        )

    return (
        ComparisonDirection.INCONCLUSIVE,
        False,
        (
            f"Mean difference {mean_difference:+.3f} "
            f"(95% CI {ci_lower:.3f} to {ci_upper:.3f}) does not clear the "
            f"±{threshold:.3f} threshold at {confidence:.0%} confidence."
        ),
    )
