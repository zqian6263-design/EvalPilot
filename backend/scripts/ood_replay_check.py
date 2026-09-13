"""Measured OOD counterfactual execution check for the expanded vocabulary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fastapi.testclient import TestClient

from evalpilot.sut.haystack_server import app

CASES = [
    {
        "scenario_id": "ood-multi-doc",
        "question": "What is the refund timeline after the warehouse receives the return?",
        "include": ["5 business days"],
        "intervention": "retrieval_top_k_restored",
    },
    {
        "scenario_id": "ood-unicode",
        "question": "退款多久到账？",
        "include": ["5 个工作日"],
        "intervention": "unicode_normalization_restored",
    },
    {
        "scenario_id": "ood-memory-scope",
        "question": "Does tenant A see tenant B memory?",
        "include": ["isolated to tenant A memory"],
        "avoid": ["tenant B memory"],
        "intervention": "memory_scope_restored",
    },
    {
        "scenario_id": "ood-cache-stale",
        "question": "Did the tool return a stale cached error?",
        "include": ["fresh HTTP 200"],
        "avoid": ["stale cached HTTP 503"],
        "intervention": "cache_bypass_enabled",
    },
]


def _passes(payload: dict, case: dict) -> bool:
    answer = str(payload.get("answer") or "")
    return all(marker in answer for marker in case.get("include", [])) and all(
        marker not in answer for marker in case.get("avoid", [])
    )


def _ask(client: TestClient, case: dict, version: str, intervention: str | None = None) -> dict:
    return client.post(
        "/v1/answer",
        json={
            "run_id": "ood-run",
            "test_case_id": case["scenario_id"],
            "scenario_id": case["scenario_id"],
            "question": case["question"],
            "version": version,
            "intervention": intervention,
        },
    ).json()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    client = TestClient(app)
    results = []
    for case in CASES:
        baseline = _ask(client, case, "v1.0-baseline")
        candidate = _ask(client, case, "v1.1-candidate")
        restored = _ask(
            client,
            case,
            "v1.1-candidate",
            intervention=case["intervention"],
        )
        results.append(
            {
                **case,
                "baseline_pass": _passes(baseline, case),
                "candidate_fail": not _passes(candidate, case),
                "intervention_pass": _passes(restored, case),
                "root_cause_confirmed": (
                    _passes(baseline, case)
                    and not _passes(candidate, case)
                    and _passes(restored, case)
                ),
                "baseline_answer": baseline["answer"],
                "candidate_answer": candidate["answer"],
                "intervention_answer": restored["answer"],
            }
        )
    confirmed = sum(1 for item in results if item["root_cause_confirmed"])
    payload = {
        "benchmark": "measured OOD counterfactual execution",
        "cases": len(results),
        "root_cause_confirmed": confirmed,
        "accuracy": round(confirmed / len(results), 4),
        "results": results,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
