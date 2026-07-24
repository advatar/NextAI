"""Measure selection-policy performance across matched budget checkpoints."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from compare_selection import TASKS, _atomic_json, _evaluate, _mutate
from recursive_lab.selection_comparison import (
    ComparisonBudget,
    budget_curve,
    compare_policies,
)
from recursive_lab.task_harness import ExecutableTaskSuite


def _parse_budgets(text: str) -> tuple[int, ...]:
    try:
        values = tuple(int(value.strip()) for value in text.split(","))
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "budgets must be comma-separated integers"
        ) from error
    if (
        not values
        or any(value < 1 for value in values)
        or tuple(sorted(set(values))) != values
    ):
        raise argparse.ArgumentTypeError(
            "budgets must be unique increasing positive integers"
        )
    return values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--budgets", type=_parse_budgets, default=(3, 6, 12, 24))
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--out", default="runs/budget-scaling.json")
    args = parser.parse_args()
    if args.seeds < 1:
        parser.error("--seeds must be positive")
    suite = ExecutableTaskSuite(TASKS, correctness_only=True)
    cache = {}
    base = compare_policies(
        initial=(0, 0, 0),
        mutate=_mutate,
        evaluate=lambda candidate: _evaluate(suite, candidate, cache),
        budget=ComparisonBudget(args.budgets[-1], len(TASKS)),
        seeds=tuple(range(args.seeds)),
        bins=(3, 3, 2, 2),
    )
    report = {
        "schema_version": 1,
        "experiment_id": "E7-budget-scaling",
        "claim_boundary": "deterministic budget-scaling ablation; no general selection or recursive-improvement claim",
        "benchmark_manifest_digest": suite.manifest_digest,
        "tasks": list(TASKS),
        "seeds": list(range(args.seeds)),
        "maximum_budget": args.budgets[-1],
        "matched_budget": base["matched_budget"],
        "scoring": {
            "correctness_gate": "executable task harness",
            "variant_quality_tiers": {
                "baseline": 0.5,
                "reviewed_improvement": 1.0,
                "broken_control": 0.0,
            },
            "identical_evaluation_cache_entries": len(cache),
        },
        "curve": budget_curve(base, args.budgets),
        "runs": base["runs"],
    }
    canonical = json.dumps(
        report, allow_nan=False, sort_keys=True, separators=(",", ":")
    )
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    output = Path(args.out)
    _atomic_json(output, report)
    for point in report["curve"]["points"]:
        means = ", ".join(
            f"{name}={values['mean_best_objective']:.3f}"
            for name, values in point["policies"].items()
        )
        print(f"budget {point['proposal_budget']:>2}: {means}")
    print(f"Matched budgets: {report['matched_budget']}; wrote {output}")


if __name__ == "__main__":
    main()
