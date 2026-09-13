"""Out-of-distribution planning benchmark for deterministic vs LLM planners."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from evalpilot.config import load_settings
from evalpilot.llm.errors import LLMError
from evalpilot.llm.runtime import build_runtime

CASES: list[dict[str, Any]] = [
    {
        "case_id": "multi_doc_retrieval_drop",
        "failure_kind": "missing_fact",
        "observed": "The answer lost a policy clause after retrieval top_k changed from 2 to 1.",
        "ground_truth": "retrieval_top_k_restored",
    },
    {
        "case_id": "unicode_normalization",
        "failure_kind": "no_retrieval_hit",
        "observed": "A full-width Chinese query no longer retrieves the same article after normalization changed.",
        "ground_truth": "unicode_normalization_restored",
    },
    {
        "case_id": "memory_scope_cross_talk",
        "failure_kind": "wrong_tenant_context",
        "observed": "Tenant A received a fact learned from tenant B after memory scoping changed.",
        "ground_truth": "memory_scope_restored",
    },
    {
        "case_id": "tool_timeout_stale_cache",
        "failure_kind": "stale_tool_result",
        "observed": "A failed tool call was cached and every later request reused the stale error response.",
        "ground_truth": "cache_bypass_enabled",
    },
    {
        "case_id": "mandatory_clause_drop",
        "failure_kind": "dropped_clause",
        "observed": "The candidate lost within-24-hours escalation language but ordinary answers stayed stable.",
        "ground_truth": "compression_disabled",
    },
    {
        "case_id": "credential_leak",
        "failure_kind": "credential_disclosure",
        "observed": "A prompt injection disclosed the admin password after the security guard changed.",
        "ground_truth": "security_guard_enabled",
    },
]

INTERVENTIONS = [
    "retrieval_top_k_restored",
    "unicode_normalization_restored",
    "memory_scope_restored",
    "cache_bypass_enabled",
    "compression_disabled",
    "security_guard_enabled",
]

SCHEMA = {
    "type": "object",
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "case_id": {"type": "string"},
                    "intervention": {"type": "string", "enum": INTERVENTIONS},
                    "rationale": {"type": "string"},
                },
                "required": ["case_id", "intervention", "rationale"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["decisions"],
    "additionalProperties": False,
}


def deterministic_plan() -> dict[str, str]:
    """The existing closed planner can choose only its two known interventions."""

    result: dict[str, str] = {}
    for case in CASES:
        if case["failure_kind"] == "credential_disclosure":
            result[case["case_id"]] = "security_guard_enabled"
        elif case["failure_kind"] in {"dropped_clause", "missing_fact"}:
            result[case["case_id"]] = "compression_disabled"
    return result


async def live_plan() -> tuple[dict[str, str], dict[str, int] | None, str | None]:
    runtime = build_runtime(load_settings())
    provider = runtime.provider
    if provider is None:
        raise RuntimeError("live LLM provider is not configured")

    prompt = [
        "You plan bounded regression experiments for a release gate.",
        "For every case choose exactly one executable intervention from the allowed list.",
        f"Allowed interventions: {', '.join(INTERVENTIONS)}.",
        "Use only the observed facts. Return JSON only.",
        "Cases:",
        *[
            f"- {case['case_id']}: kind={case['failure_kind']}; observed={case['observed']}"
            for case in CASES
        ],
    ]
    messages = [
        {"role": "system", "content": "Plan experiments, not verdicts."},
        {"role": "user", "content": "\n".join(prompt)},
    ]
    result = None
    last_error: Exception | None = None
    for _ in range(2):
        try:
            result = await provider.complete_json(
                messages,
                {"type": "object"},
                timeout_seconds=runtime.timeout_seconds,
            )
            break
        except LLMError as exc:
            last_error = exc
    if result is None:
        raise RuntimeError(f"model planner failed after retry: {last_error}")

    decisions = (
        result.payload.get("decisions")
        or result.payload.get("plan")
        or result.payload.get("replay_plan")
        or result.payload.get("interventions")
    )
    if decisions is None and any(
        case["case_id"] in result.payload for case in CASES
    ):
        decisions = [
            {"case_id": case_id, "intervention": intervention}
            for case_id, intervention in result.payload.items()
        ]
    decisions = decisions or []
    if not isinstance(decisions, list):
        raise RuntimeError(
            "model planner returned no decision list; keys="
            f"{sorted(result.payload)}"
        )
    return (
        {
            str(item.get("case_id")): str(item.get("intervention"))
            for item in decisions
            if isinstance(item, dict)
        },
        result.usage,
        result.model,
    )


def score(plan: dict[str, str]) -> dict[str, Any]:
    correct = [case["case_id"] for case in CASES if plan.get(case["case_id"]) == case["ground_truth"]]
    missing = [case["case_id"] for case in CASES if case["case_id"] not in plan]
    invalid = [
        case_id
        for case_id, intervention in plan.items()
        if intervention not in INTERVENTIONS
    ]
    return {
        "planned": len(plan),
        "correct": len(correct),
        "accuracy": round(len(correct) / len(CASES), 4),
        "correct_cases": correct,
        "missing_cases": missing,
        "invalid_interventions": invalid,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result: dict[str, Any] = {
        "benchmark": "OOD intervention planning",
        "cases": len(CASES),
        "allowed_interventions": INTERVENTIONS,
        "deterministic": {**score(deterministic_plan()), "llm_calls": 0, "tokens": 0},
    }
    if args.live:
        plan, usage, model = asyncio.run(live_plan())
        result["model"] = {
            **score(plan),
            "llm_calls": 1,
            "prompt_tokens": int((usage or {}).get("prompt_tokens") or 0),
            "completion_tokens": int((usage or {}).get("completion_tokens") or 0),
            "tokens": int((usage or {}).get("total_tokens") or 0),
            "model_name": model,
            "plan": plan,
        }
    else:
        result["note"] = "Run with --live to add the model planner comparison."

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
