"""Run public workload comparisons and print machine-readable evidence."""

from __future__ import annotations

import json

from evalpilot.public_workload import run_public_workloads


def main() -> int:
    results = run_public_workloads()
    payload = {
        "workloads": [
            {
                "workload": result.workload,
                "label": result.label,
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
            for result in results
        ]
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if all(result.engine_confirms_regression for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
