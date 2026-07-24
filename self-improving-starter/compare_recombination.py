"""E9: full local AlphaEvolve-style loop versus matched-budget controls."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict
from pathlib import Path

from compare_selection import TASKS, _atomic_json, _evaluate, _mutate
from recursive_lab.alphaevolve import EvolutionBudget, evolve_programs, text_fingerprint
from recursive_lab.selection_comparison import ComparisonBudget, run_policy
from recursive_lab.task_harness import ExecutableTaskSuite


class Explorer:
    name = "explorer"

    def propose(self, sample, rng):
        sources = (sample.parent, *sample.inspirations)
        child = tuple(rng.choice(sources).candidate[i] for i in range(3))
        return _mutate(child, rng)


class Exploiter:
    name = "exploiter"

    def propose(self, sample, rng):
        sources = (sample.parent, *sample.inspirations)
        child = list(sample.parent.candidate)
        for i in range(3):
            if any(item.candidate[i] == 1 for item in sources):
                child[i] = 1
        remaining = [i for i, value in enumerate(child) if value != 1]
        if remaining:
            child[rng.choice(remaining)] = 1
        return tuple(child)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposals", type=int, default=24)
    parser.add_argument("--seeds", type=int, default=50)
    parser.add_argument("--out", default="runs/alphaevolve-local.json")
    args = parser.parse_args()
    if args.proposals < 1 or args.seeds < 1:
        parser.error("budgets and seeds must be positive")
    suite = ExecutableTaskSuite(TASKS, correctness_only=True)
    cache = {}

    def evaluator(candidate):
        return _evaluate(suite, candidate, cache)

    budget = ComparisonBudget(args.proposals, 3)
    runs = []
    for seed in range(args.seeds):
        for policy in ("greedy", "quality_diversity"):
            result = run_policy(
                policy=policy,
                initial=(0, 0, 0),
                mutate=_mutate,
                evaluate=evaluator,
                budget=budget,
                seed=seed,
                bins=(2, 2, 2, 2),
            )
            runs.append(
                {
                    "policy": policy,
                    "seed": seed,
                    "best_objective": result.best_objective,
                    "model_calls": args.proposals,
                    "candidate_evaluations": result.candidate_evaluations,
                    "task_evaluations": result.task_evaluations,
                }
            )
        evolved = evolve_programs(
            initial=(0, 0, 0),
            proposers=(Explorer(), Exploiter()),
            evaluate=evaluator,
            fingerprint=text_fingerprint,
            budget=EvolutionBudget(args.proposals, 3, 2),
            seed=seed,
            bins=(2, 2, 2, 2),
        )
        runs.append(
            {
                "policy": "alphaevolve_local",
                "seed": seed,
                "best_objective": evolved.best.evaluation.objective,
                "model_calls": evolved.model_calls,
                "candidate_evaluations": evolved.candidate_evaluations,
                "task_evaluations": evolved.task_evaluations,
                "program_database_size": len(evolved.records),
                "proposer_calls": evolved.proposer_calls,
            }
        )
    summaries = {}
    for policy in ("greedy", "quality_diversity", "alphaevolve_local"):
        cohort = [r for r in runs if r["policy"] == policy]
        scores = [r["best_objective"] for r in cohort]
        summaries[policy] = {
            "runs": len(cohort),
            "mean_best_objective": math.fsum(scores) / len(scores),
            "target_hit_rate": sum(score >= 1 for score in scores) / len(scores),
        }
    report = {
        "schema_version": 2,
        "experiment_id": "E9-alphaevolve-local",
        "claim_boundary": "full deterministic AlphaEvolve-style architecture validation; no Gemini, discovery, or recursive-improvement claim",
        "paper_components": {
            "program_database": True,
            "parent_and_inspiration_sampling": True,
            "proposer_ensemble": ["explorer", "exploiter"],
            "whole_program_candidates": True,
            "external_multi_metric_evaluation": True,
            "evolutionary_readmission": True,
        },
        "benchmark_manifest_digest": suite.manifest_digest,
        "tasks": list(TASKS),
        "seeds": list(range(args.seeds)),
        "budget": asdict(budget),
        "matched_budget": all(
            r["model_calls"] == args.proposals
            and r["candidate_evaluations"] == args.proposals
            and r["task_evaluations"] == args.proposals * 3
            for r in runs
        ),
        "summaries": summaries,
        "runs": runs,
    }
    canonical = json.dumps(
        report, allow_nan=False, sort_keys=True, separators=(",", ":")
    )
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    output = Path(args.out)
    _atomic_json(output, report)
    for name, s in summaries.items():
        print(
            f"{name:22} mean={s['mean_best_objective']:.3f} hit={s['target_hit_rate']:.0%}"
        )
    print(f"Matched budgets: {report['matched_budget']}; wrote {output}")


if __name__ == "__main__":
    main()
