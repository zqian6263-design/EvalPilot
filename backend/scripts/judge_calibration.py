"""Compare a live judge with human-scored rows from CSV."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
from pathlib import Path

from evalpilot.config import load_settings
from evalpilot.evaluation.calibration import calibration_metrics
from evalpilot.evaluation.judge import JudgeRequest, RubricJudge
from evalpilot.llm.judge_adapter import build_judge_callable
from evalpilot.llm.runtime import build_runtime


async def run(csv_path: Path) -> dict:
    runtime = build_runtime(load_settings())
    call = build_judge_callable(runtime)
    if call is None:
        raise RuntimeError("live judge is not configured")
    judge = RubricJudge(call)
    rows: list[tuple[float, float]] = []
    details = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"case_id", "question", "answer", "rubric", "human_score"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV missing columns: {sorted(missing)}")
        for row in reader:
            human = float(row["human_score"])
            output = await judge.judge(
                JudgeRequest(
                    case_id=row["case_id"],
                    question=row["question"],
                    answer_text=row["answer"],
                    rubric=row["rubric"],
                    criteria=[],
                )
            )
            rows.append((output.score, human))
            details.append(
                {
                    "case_id": row["case_id"],
                    "judge_score": output.score,
                    "human_score": human,
                    "delta": round(output.score - human, 6),
                }
            )
    return {
        "metrics": calibration_metrics(rows),
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = asyncio.run(run(args.csv))
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
