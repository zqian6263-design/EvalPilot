"""Run the public SQuAD workload and print machine-readable evidence."""

from __future__ import annotations

import json

from evalpilot.public_workload import run_public_workload


def main() -> int:
    result = run_public_workload()
    payload = {
        "workload": "rajpurkar/squad validation",
        "rows": result.rows,
        "authored_regressions": result.authored_regressions,
        "controls": result.controls,
        "naive": {
            "baseline_pass_rate": result.baseline_pass_rate,
            "candidate_pass_rate": result.candidate_pass_rate,
            "detects_regression": result.naive_detects_regression,
        },
        "evalpilot": {
            "direction": result.engine_direction,
            "mean_difference": result.engine_mean_difference,
            "ci_lower": result.engine_ci_lower,
            "ci_upper": result.engine_ci_upper,
            "confidence": result.engine_confidence,
            "confirms_regression": result.engine_confirms_regression,
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if result.engine_confirms_regression else 1


if __name__ == "__main__":
    raise SystemExit(main())
