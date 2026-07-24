"""E28: staged deceptive search with generation-by-generation controls."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict
from pathlib import Path

from compare_deceptive_search import crossover, evaluate, mutate
from compare_selection import _atomic_json
from recursive_lab.selection_comparison import (
    ComparisonBudget,
    run_archive_recombination,
    run_policy,
)

POLICIES = ("greedy", "random_mutation", "quality_diversity", "archive_recombination")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=1000)
    parser.add_argument("--generations", type=int, default=5)
    parser.add_argument("--proposals-per-generation", type=int, default=20)
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E28-staged-deceptive.json")
    )
    args = parser.parse_args()
    proposals = args.generations * args.proposals_per_generation
    budget = ComparisonBudget(proposals, 1)
    results = []
    for seed in range(args.seeds):
        for policy in POLICIES[:-1]:
            results.append(
                run_policy(
                    policy=policy,
                    initial=(0, 0),
                    mutate=mutate,
                    evaluate=evaluate,
                    budget=budget,
                    seed=seed,
                    bins=(5, 5),
                )
            )
        results.append(
            run_archive_recombination(
                initial=(0, 0),
                crossover=crossover,
                mutate=mutate,
                evaluate=evaluate,
                budget=budget,
                seed=seed,
                bins=(5, 5),
            )
        )

    generations = []
    for generation in range(1, args.generations + 1):
        checkpoint = generation * args.proposals_per_generation
        policies = {}
        for policy in POLICIES:
            cohort = [result for result in results if result.policy == policy]
            objectives = [
                result.trajectory[checkpoint - 1].best_objective for result in cohort
            ]
            policies[policy] = {
                "mean_best_objective": math.fsum(objectives) / len(objectives),
                "global_optimum_hit_rate": sum(value >= 1.0 for value in objectives)
                / len(objectives),
            }
        generations.append(
            {
                "generation": generation,
                "cumulative_proposals": checkpoint,
                "policies": policies,
            }
        )

    report = {
        "schema_version": 1,
        "experiment_id": "E28-staged-deceptive",
        "claim_boundary": (
            "synthetic staged-search control used to select a real-model "
            "benchmark; no model-learning claim"
        ),
        "seeds": args.seeds,
        "generations": args.generations,
        "proposals_per_generation": args.proposals_per_generation,
        "budget": asdict(budget),
        "matched_budget": all(
            result.candidate_evaluations == proposals for result in results
        ),
        "trajectory": generations,
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)
    for point in generations:
        summary = " ".join(
            f"{policy}={values['global_optimum_hit_rate']:.1%}"
            for policy, values in point["policies"].items()
        )
        print(f"generation={point['generation']} {summary}")


if __name__ == "__main__":
    main()
