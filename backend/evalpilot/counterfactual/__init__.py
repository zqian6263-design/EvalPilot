"""Pure counterfactual replay for the autonomous investigation layer.

The interface the investigation backend consumes
-----------------------------------------------

```python
from evalpilot.counterfactual import (
    CounterfactualEngine, CounterfactualTarget, Intervention,
)

engine = CounterfactualEngine(source=reading_source)   # one instance, stateless
experiment = engine.replay(
    CounterfactualTarget(
        scenario_id="urgent-safety",        # the matched key, not a case row id
        run_id=run_id,
        test_case_id=candidate_row_id,      # the row the finding cites
        intervention=Intervention.COMPRESSION_DISABLED,
        expected=candidate_row.expected,    # the expectation the run scored against
        original_evidence_ids=[first_evidence_id_for_that_row],
    ),
    investigation_id=investigation_id,
)
```

``experiment.verdict`` is the ``CounterfactualExperiment.verdict`` from
``docs/V2_INTERFACES.md``; ``experiment.evidence_ids`` is the list that row
persists; ``experiment.rationale`` is human-readable and rendered from the
measured scores. Nothing is written outside the injected ``source``, and this
package imports no routes, no repository and no application module.

Reading source implementations
------------------------------

``CounterfactualEngine`` takes any object satisfying
:class:`~evalpilot.counterfactual.reading.InvestigationReadingSource`:
``get_evidence``, ``add_evidence`` and ``write_artifact``. The investigation
backend supplies one backed by the real repository; tests use
:class:`~evalpilot.counterfactual.reading.InMemoryReadingSource`.
"""

from .engine import (
    FULL_FAILURE_SCORE,
    MIN_EFFECT_DELTA,
    PASS_SCORE,
    CounterfactualEngine,
)
from .models import (
    CounterfactualModel,
    CounterfactualTarget,
    ExperimentResult,
    ExperimentVerdict,
    Intervention,
    ReplayRunResult,
    ReplayRunSummary,
    coerce_intervention,
    intervention_executor_value,
    intervention_name,
)
from .reading import (
    REPLAY_CONDITION_KEY,
    REPLAY_EVIDENCE_KIND,
    InMemoryReadingSource,
    InvestigationReadingSource,
    resolve_evidence,
)

__all__ = [
    "FULL_FAILURE_SCORE",
    "MIN_EFFECT_DELTA",
    "PASS_SCORE",
    "REPLAY_CONDITION_KEY",
    "REPLAY_EVIDENCE_KIND",
    "CounterfactualEngine",
    "CounterfactualModel",
    "CounterfactualTarget",
    "ExperimentResult",
    "ExperimentVerdict",
    "InMemoryReadingSource",
    "Intervention",
    "InvestigationReadingSource",
    "ReplayRunResult",
    "ReplayRunSummary",
    "coerce_intervention",
    "intervention_executor_value",
    "intervention_name",
    "resolve_evidence",
]
