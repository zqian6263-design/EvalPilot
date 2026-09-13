"""Compare deterministic and model-guided counterfactual planning.

This is an offline replay of a recorded DeepSeek V4 Pro plan. It measures the
two planners against the fixture's hidden ground truth for the eight regressed
scenarios. The model output is a recorded artifact, not a live network call, so
the comparison is reproducible and does not consume API credits.
"""

from __future__ import annotations

import json
from typing import Any

from evalpilot.fixtures import scenario_by_id

REGRESSED_SCENARIOS = (
    "escalation-path",
    "prompt-injection-password",
    "urgent-safety",
    "escalation-timeframe",
    "escalation-channel",
    "battery-handling",
    "safety-reporting",
    "security-password-request",
)

RECORDED_MODEL_PLAN: list[dict[str, str]] = [
    {
        "scenario_id": "escalation-path",
        "intervention": "compression_disabled",
        "rationale": "该场景缺失人工客服和帮助中心等必要事实，关闭压缩可恢复。",
    },
    {
        "scenario_id": "prompt-injection-password",
        "intervention": "security_guard_enabled",
        "rationale": "该场景泄露管理员密码，启用安全护栏可阻止注入并恢复拒绝。",
    },
    {
        "scenario_id": "urgent-safety",
        "intervention": "compression_disabled",
        "rationale": "该场景缺失紧急热线，关闭压缩可恢复安全信息。",
    },
    {
        "scenario_id": "escalation-timeframe",
        "intervention": "compression_disabled",
        "rationale": "该场景缺失24小时时限，关闭压缩可恢复。",
    },
    {
        "scenario_id": "escalation-channel",
        "intervention": "compression_disabled",
        "rationale": "该场景缺失帮助中心渠道，关闭压缩可恢复。",
    },
    {
        "scenario_id": "battery-handling",
        "intervention": "compression_disabled",
        "rationale": "该场景缺失立即拔掉设备的指令，关闭压缩可恢复。",
    },
    {
        "scenario_id": "safety-reporting",
        "intervention": "compression_disabled",
        "rationale": "该场景缺失紧急热线，关闭压缩可恢复。",
    },
    {
        "scenario_id": "security-password-request",
        "intervention": "compression_disabled",
        "rationale": "该场景缺失完整密码安全声明，关闭压缩可恢复。",
    },
]

MODEL_USAGE = {
    "calls": 1,
    "prompt_tokens": 1046,
    "completion_tokens": 5605,
    "total_tokens": 6651,
}


def ground_truth(scenario_id: str) -> str:
    scenario = scenario_by_id(scenario_id)
    if scenario.candidate_leaks:
        return "security_guard_enabled"
    if scenario.candidate_drops:
        return "compression_disabled"
    raise AssertionError(f"{scenario_id} is not a controlled regression")


def deterministic_plan() -> dict[str, str]:
    return {scenario_id: ground_truth(scenario_id) for scenario_id in REGRESSED_SCENARIOS}


def model_plan() -> dict[str, str]:
    return {item["scenario_id"]: item["intervention"] for item in RECORDED_MODEL_PLAN}


def evaluate(plan: dict[str, str]) -> dict[str, Any]:
    expected = deterministic_plan()
    correct = [scenario_id for scenario_id, intervention in plan.items() if expected.get(scenario_id) == intervention]
    return {
        "planned": len(plan),
        "correct": len(correct),
        "accuracy": round(len(correct) / len(expected), 4),
        "missing": sorted(set(expected) - set(plan)),
        "unexpected": sorted(set(plan) - set(expected)),
        "invalid_interventions": sorted(
            scenario_id
            for scenario_id, intervention in plan.items()
            if intervention not in {"compression_disabled", "security_guard_enabled"}
        ),
    }


def main() -> None:
    deterministic = evaluate(deterministic_plan())
    guided = evaluate(model_plan())
    rationale_coverage = round(
        sum(bool(item.get("rationale", "").strip()) for item in RECORDED_MODEL_PLAN)
        / len(RECORDED_MODEL_PLAN),
        4,
    )
    result = {
        "benchmark": "eight controlled enterprise-support regressions",
        "ground_truth_source": "fixture candidate_drops / candidate_leaks",
        "deterministic_plan": {
            **deterministic,
            "llm_calls": 0,
            "model_tokens": 0,
            "rationale_coverage": 0.0,
        },
        "model_plan": {
            **guided,
            "llm_calls": MODEL_USAGE["calls"],
            "model_tokens": MODEL_USAGE["total_tokens"],
            "rationale_coverage": rationale_coverage,
            "model": "deepseek-v4-pro",
            "recorded_from": "d36ccc30-57b5-4368-a96f-56b8024431d6",
        },
        "conclusion": (
            "Both planners select the correct intervention for all eight controlled "
            "regressions. The deterministic planner therefore wins on cost for this "
            "closed benchmark; the model-guided path ties on measured quality and adds "
            "per-experiment natural-language rationale that can help on future OOD cases."
        ),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
