"""E59: re-run the E43 router protocol on a benchmark that has headroom.

E43 evolved a confidence-gated router over nine synthetic families and reported
a paired promoted-minus-random target-hit advantage of ``0.0038``.  E51 later
audited that cohort and rejected it: random exploration alone already reached
the target 80% of the time, because the 5x5 grid let every run evaluate 20 of
25 cells.  The near-zero effect was a property of the instrument, not of the
router.

This experiment keeps E43's protocol -- evolve a router over the same candidate
threshold grid on training seeds, then validate on disjoint held-out seeds --
and changes only the instrument, using :mod:`recursive_lab.scaled_landscape`.
Two things differ:

* the grid is wide enough that a run evaluates a small fraction of the space;
* the reported quantity is continuous ``regret`` rather than binary
  ``target_hit``, because a binary hit rate saturates at the ceiling on a narrow
  grid and at the floor on a wide one.

Admission is decided **before** the comparison and **only** from the random
baseline's behaviour, via :mod:`recursive_lab.admission`.  A family on which
random search already succeeds, or on which no policy can differ, is reported as
not admitted and is excluded from the headline claim rather than being allowed
to dilute it.  Families are admitted individually, so a null result on one
family does not suppress a real effect on another.

Claim boundary: this is a synthetic landscape study of one exploitation rule.
It says nothing about model self-improvement, and a positive result here is a
statement about search policy on smooth score surfaces only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from compare_selection import _atomic_json
from recursive_lab.admission import (
    AdmissionCriteria,
    CohortObservations,
    evaluate_admission,
)
from recursive_lab.scaled_landscape import (
    ALWAYS_SURROGATE_POLICY,
    FAMILIES,
    RANDOM_POLICY,
    RouterPolicy,
    SearchBudget,
    bootstrap_ci,
    make_spec,
    mean,
    run_policy,
)

#: The same threshold grid E43 searched, so the comparison is like-for-like.
CANDIDATES = tuple(
    (r_squared, variance)
    for r_squared in (0.0, 0.5, 0.8, 0.95, 1.01)
    for variance in (0.0, 0.001, 0.01, 0.03)
)


def policy_for(candidate: tuple[float, float]) -> RouterPolicy:
    return RouterPolicy(f"{candidate[0]}:{candidate[1]}", candidate[0], candidate[1])


def admission_for_family(
    family: str,
    grid_size: int,
    budget: SearchBudget,
    seeds: int,
    seed_start: int,
    criteria: AdmissionCriteria,
) -> dict:
    """Judge a family using the random baseline only, before any comparison.

    Deciding admission from the policy under test would be circular, so the
    disagreement count is measured between two *reference* policies (never
    exploit versus always exploit), not between a candidate and its control.
    """
    hits = 0
    disagreements = 0
    for seed in range(seed_start, seed_start + seeds):
        spec = make_spec(family, grid_size, seed=seed)
        baseline = run_policy(spec, budget, RANDOM_POLICY, seed=seed)
        reference = run_policy(spec, budget, ALWAYS_SURROGATE_POLICY, seed=seed)
        hits += int(baseline.target_hit)
        if abs(baseline.regret - reference.regret) > 1e-12:
            disagreements += 1

    observations = CohortObservations(
        exploration_target_rate=hits / seeds,
        policy_disagreements=disagreements,
        tasks=seeds,
    )
    result = evaluate_admission(observations, criteria)
    return {
        "family": family,
        "admitted": result.admitted,
        "failures": list(result.failures),
        "observed": {
            "exploration_target_rate": observations.exploration_target_rate,
            "policy_disagreements": observations.policy_disagreements,
            "tasks": observations.tasks,
        },
    }


def evaluate_cohort(
    families: tuple[str, ...],
    grid_size: int,
    budget: SearchBudget,
    seeds: int,
    seed_start: int,
) -> dict:
    """Mean regret per candidate router per family."""
    totals = {
        candidate: {family: [] for family in families} for candidate in CANDIDATES
    }
    for seed in range(seed_start, seed_start + seeds):
        for family in families:
            spec = make_spec(family, grid_size, seed=seed)
            for candidate in CANDIDATES:
                run = run_policy(spec, budget, policy_for(candidate), seed=seed)
                totals[candidate][family].append(run.regret)

    summaries = {}
    for candidate, per_family in totals.items():
        family_means = {
            family: mean(values) for family, values in per_family.items()
        }
        summaries[f"{candidate[0]}:{candidate[1]}"] = {
            "r_squared_threshold": candidate[0],
            "variance_threshold": candidate[1],
            "macro_mean_regret": mean(family_means.values()),
            "worst_family_mean_regret": max(family_means.values()),
            "families": family_means,
        }
    return summaries


def paired_regret_delta(
    families: tuple[str, ...],
    grid_size: int,
    budget: SearchBudget,
    seeds: int,
    seed_start: int,
    promoted: tuple[float, float],
    baseline: tuple[float, float],
    bootstrap_seed: int,
) -> dict:
    """Paired promoted-minus-baseline regret, per family and pooled.

    Negative means the promoted router leaves less regret, i.e. it is better.
    """
    promoted_policy = policy_for(promoted)
    baseline_policy = policy_for(baseline)
    per_family: dict[str, list[float]] = {family: [] for family in families}
    pooled: list[float] = []
    for seed in range(seed_start, seed_start + seeds):
        for family in families:
            spec = make_spec(family, grid_size, seed=seed)
            winner = run_policy(spec, budget, promoted_policy, seed=seed)
            control = run_policy(spec, budget, baseline_policy, seed=seed)
            delta = winner.regret - control.regret
            per_family[family].append(delta)
            pooled.append(delta)
    return {
        "pooled_regret_delta": mean(pooled),
        "pooled_regret_delta_95pct_bootstrap_ci": bootstrap_ci(
            pooled, bootstrap_seed
        ),
        "per_family": {
            family: {
                "regret_delta": mean(values),
                "regret_delta_95pct_bootstrap_ci": bootstrap_ci(
                    values, bootstrap_seed + index
                ),
            }
            for index, (family, values) in enumerate(per_family.items())
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid-size", type=int, default=128)
    parser.add_argument("--exploration-per-column", type=int, default=3)
    parser.add_argument("--train-seeds", type=int, default=120)
    parser.add_argument("--validation-seeds", type=int, default=120)
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E59-scaled-router.json")
    )
    args = parser.parse_args()

    budget = SearchBudget(args.grid_size, args.exploration_per_column)
    criteria = AdmissionCriteria()

    # Step 1: admission, decided from the random baseline alone, before any
    # candidate router is compared to anything.
    admission_rows = [
        admission_for_family(
            family,
            args.grid_size,
            budget,
            args.train_seeds,
            0,
            criteria,
        )
        for family in FAMILIES
    ]
    admitted = tuple(row["family"] for row in admission_rows if row["admitted"])
    rejected = tuple(row["family"] for row in admission_rows if not row["admitted"])

    report: dict = {
        "schema_version": 1,
        "experiment_id": "E59-scaled-router",
        "claim_boundary": (
            "synthetic landscape study of one exploitation rule on a "
            "headroom-checked benchmark; families are admitted from random "
            "baseline behaviour only; no model self-improvement claim"
        ),
        "supersedes_instrument_of": ["E43-risk-router", "E45-support-guard"],
        "grid_size": args.grid_size,
        "exploration_per_column": args.exploration_per_column,
        "budget": {
            "evaluations_per_run": budget.evaluations,
            "search_space": budget.search_space,
            "coverage": budget.coverage,
            "legacy_coverage_at_grid_5": SearchBudget(5, 3).coverage,
        },
        "primary_metric": "regret (1.0 - best_score); lower is better",
        "train_seeds": args.train_seeds,
        "validation_seeds": args.validation_seeds,
        "admission_criteria": {
            "maximum_exploration_target_rate": (
                criteria.maximum_exploration_target_rate
            ),
            "minimum_policy_disagreements": criteria.minimum_policy_disagreements,
            "minimum_tasks": criteria.minimum_tasks,
        },
        "admission": admission_rows,
        "admitted_families": list(admitted),
        "rejected_families": list(rejected),
    }

    if not admitted:
        report["decision"] = "no admitted family; cohort produces no claim"
        canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
        report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
        _atomic_json(args.out, report)
        print("no family admitted; no comparison run")
        return

    # Step 2: evolve a router on training seeds over admitted families only.
    train = evaluate_cohort(
        admitted, args.grid_size, budget, args.train_seeds, 0
    )
    winner = min(
        train.values(),
        key=lambda item: (
            item["worst_family_mean_regret"],
            item["macro_mean_regret"],
            item["r_squared_threshold"],
            item["variance_threshold"],
        ),
    )
    promoted = (winner["r_squared_threshold"], winner["variance_threshold"])
    baseline = (1.01, 0.0)

    # Step 3: validate on disjoint held-out seeds.
    validation_start = args.train_seeds
    validation = evaluate_cohort(
        admitted, args.grid_size, budget, args.validation_seeds, validation_start
    )

    report["promotion_objective"] = "worst-family mean regret, then macro regret"
    report["promoted"] = {
        "r_squared_threshold": promoted[0],
        "variance_threshold": promoted[1],
    }
    report["train"] = train
    report["validation"] = validation[f"{promoted[0]}:{promoted[1]}"]
    report["random_baseline_validation"] = validation[
        f"{baseline[0]}:{baseline[1]}"
    ]
    report["paired_promoted_minus_random"] = paired_regret_delta(
        admitted,
        args.grid_size,
        budget,
        args.validation_seeds,
        validation_start,
        promoted,
        baseline,
        87001,
    )

    pooled = report["paired_promoted_minus_random"]["pooled_regret_delta"]
    interval = report["paired_promoted_minus_random"][
        "pooled_regret_delta_95pct_bootstrap_ci"
    ]
    report["verdict"] = (
        "promoted router reduces regret"
        if interval[1] < 0
        else "promoted router increases regret"
        if interval[0] > 0
        else "inconclusive: interval spans zero"
    )

    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)

    print(f"coverage={budget.coverage:.4f} (legacy 0.8000)")
    print(f"admitted={list(admitted)}")
    print(f"rejected={list(rejected)}")
    print(f"promoted={report['promoted']}")
    print(f"pooled regret delta={pooled:+.5f} ci={interval}")
    print(f"verdict={report['verdict']}")
    for family, row in report["paired_promoted_minus_random"][
        "per_family"
    ].items():
        print(
            f"  {family:14} {row['regret_delta']:+.5f} "
            f"{row['regret_delta_95pct_bootstrap_ci']}"
        )


if __name__ == "__main__":
    main()
