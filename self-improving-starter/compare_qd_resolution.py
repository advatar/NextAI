"""Ablate quality-diversity archive resolution under matched budgets."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from compare_selection import TASKS, _atomic_json, _evaluate, _mutate
from recursive_lab.selection_comparison import ComparisonBudget, run_policy
from recursive_lab.task_harness import ExecutableTaskSuite

CONFIGURATIONS = {
    "coarse_2x2x2x2": (2, 2, 2, 2),
    "current_3x3x2x2": (3, 3, 2, 2),
    "fine_4x4x4x2": (4, 4, 4, 2),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposals", type=int, default=24)
    parser.add_argument("--seeds", type=int, default=50)
    parser.add_argument("--out", default="runs/qd-resolution.json")
    args = parser.parse_args()
    if args.proposals < 1 or args.seeds < 1:
        parser.error("budgets and seeds must be positive")
    suite = ExecutableTaskSuite(TASKS, correctness_only=True)
    cache = {}
    runs = []
    for seed in range(args.seeds):
        for name, bins in CONFIGURATIONS.items():
            result = run_policy(
                policy="quality_diversity",
                initial=(0, 0, 0),
                mutate=_mutate,
                evaluate=lambda candidate: _evaluate(suite, candidate, cache),
                budget=ComparisonBudget(args.proposals, len(TASKS)),
                seed=seed,
                bins=bins,
            )
            runs.append(
                {
                    "configuration": name,
                    "bins": list(bins),
                    **{
                        "seed": result.seed,
                        "best_objective": result.best_objective,
                        "occupied_cells": result.occupied_cells,
                        "candidate_evaluations": result.candidate_evaluations,
                        "task_evaluations": result.task_evaluations,
                        "trajectory": [
                            {
                                "proposal": step.proposal,
                                "best_objective": step.best_objective,
                                "occupied_cells": step.occupied_cells,
                            }
                            for step in result.trajectory
                        ],
                    },
                }
            )
    summaries = {}
    for name in CONFIGURATIONS:
        cohort = [run for run in runs if run["configuration"] == name]
        scores = [run["best_objective"] for run in cohort]
        hits = [
            next(
                (
                    step["proposal"]
                    for step in run["trajectory"]
                    if step["best_objective"] >= 1.0
                ),
                None,
            )
            for run in cohort
        ]
        reached = [hit for hit in hits if hit is not None]
        summaries[name] = {
            "runs": len(cohort),
            "mean_best_objective": math.fsum(scores) / len(scores),
            "target_hit_rate": len(reached) / len(hits),
            "mean_proposals_to_target_when_hit": None
            if not reached
            else math.fsum(reached) / len(reached),
            "mean_occupied_cells": math.fsum(run["occupied_cells"] for run in cohort)
            / len(cohort),
        }
    report = {
        "schema_version": 1,
        "experiment_id": "E8-qd-resolution-ablation",
        "claim_boundary": "deterministic archive-resolution ablation; no general QD or recursive-improvement claim",
        "benchmark_manifest_digest": suite.manifest_digest,
        "tasks": list(TASKS),
        "seeds": list(range(args.seeds)),
        "budget": {"proposals": args.proposals, "tasks_per_evaluation": len(TASKS)},
        "matched_budget": all(
            run["candidate_evaluations"] == args.proposals
            and run["task_evaluations"] == args.proposals * len(TASKS)
            for run in runs
        ),
        "configurations": {name: list(bins) for name, bins in CONFIGURATIONS.items()},
        "scoring": {
            "correctness_gate": "executable task harness",
            "variant_quality_tiers": {
                "baseline": 0.5,
                "reviewed_improvement": 1.0,
                "broken_control": 0.0,
            },
            "identical_evaluation_cache_entries": len(cache),
        },
        "summaries": summaries,
        "runs": runs,
    }
    canonical = json.dumps(
        report, allow_nan=False, sort_keys=True, separators=(",", ":")
    )
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    output = Path(args.out)
    _atomic_json(output, report)
    for name, summary in summaries.items():
        print(
            f"{name:18} mean={summary['mean_best_objective']:.3f} hit={summary['target_hit_rate']:.0%} cells={summary['mean_occupied_cells']:.1f}"
        )
    print(f"Matched budgets: {report['matched_budget']}; wrote {output}")


if __name__ == "__main__":
    main()
