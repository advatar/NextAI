"""E11: matched-budget search on a landscape with a greedy local optimum."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict
from pathlib import Path

from compare_selection import _atomic_json
from recursive_lab.quality_diversity import CandidateEvaluation
from recursive_lab.selection_comparison import (
    ComparisonBudget,
    run_archive_recombination,
    run_policy,
)


def evaluate(point):
    x, y = point
    if point == (0, 0):
        objective = 0.8
    elif point == (4, 4):
        objective = 1.0
    else:
        objective = 0.1 + 0.6 * ((x + y) / 8)
    return CandidateEvaluation(objective, (x / 4, y / 4), {"x": x / 4, "y": y / 4})


def mutate(point, rng):
    values = list(point)
    axis = rng.randrange(2)
    values[axis] = max(0, min(4, values[axis] + rng.choice((-1, 1))))
    return tuple(values)


def crossover(a, b, rng):
    return (a[0] if rng.random() < 0.5 else b[0], a[1] if rng.random() < 0.5 else b[1])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--proposals", type=int, default=100)
    p.add_argument("--seeds", type=int, default=100)
    p.add_argument("--out", default="runs/E11-deceptive-search.json")
    a = p.parse_args()
    budget = ComparisonBudget(a.proposals, 1)
    results = []
    for seed in range(a.seeds):
        for policy in ("greedy", "random_mutation", "quality_diversity"):
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
    summaries = {}
    for policy in (
        "greedy",
        "random_mutation",
        "quality_diversity",
        "archive_recombination",
    ):
        cohort = [r for r in results if r.policy == policy]
        scores = [r.best_objective for r in cohort]
        summaries[policy] = {
            "runs": len(cohort),
            "mean_best_objective": math.fsum(scores) / len(scores),
            "global_optimum_hit_rate": sum(s >= 1 for s in scores) / len(scores),
        }
    report = {
        "schema_version": 1,
        "experiment_id": "E11-deceptive-search",
        "claim_boundary": "synthetic deceptive-landscape search-policy evidence only",
        "landscape": {"grid": "5x5", "start_local_optimum": 0.8, "global_optimum": 1.0},
        "seeds": list(range(a.seeds)),
        "budget": asdict(budget),
        "matched_budget": all(r.candidate_evaluations == a.proposals for r in results),
        "summaries": summaries,
        "runs": [
            {
                "policy": r.policy,
                "seed": r.seed,
                "best_objective": r.best_objective,
                "candidate_evaluations": r.candidate_evaluations,
                "task_evaluations": r.task_evaluations,
                "occupied_cells": r.occupied_cells,
            }
            for r in results
        ],
    }
    canonical = json.dumps(
        report, allow_nan=False, sort_keys=True, separators=(",", ":")
    )
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(Path(a.out), report)
    for k, v in summaries.items():
        print(
            f"{k:23} mean={v['mean_best_objective']:.3f} hit={v['global_optimum_hit_rate']:.0%}"
        )


if __name__ == "__main__":
    main()
