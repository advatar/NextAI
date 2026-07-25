"""E43: evolve a worst-family-first router across nine landscape families."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path

from compare_selection import _atomic_json
from compare_e37_surrogate_generalization import bootstrap_ci, score as base_score
from compare_e38_adaptive_emitter import fit_linear
from compare_e40_unseen_families import score as unseen_score
from compare_e42_second_audit import score as audit_score

FAMILIES = (
    "monotone",
    "curved",
    "spike",
    "plateau",
    "checkerboard",
    "rugged",
    "ridge",
    "sinusoidal",
    "decoy",
)
CANDIDATES = tuple(
    (r2, variance)
    for r2 in (0.0, 0.5, 0.8, 0.95, 1.01)
    for variance in (0.0, 0.001, 0.01, 0.03)
)


def score(
    family: str,
    point: tuple[int, int],
    target: tuple[int, int],
    landscape_seed: int,
) -> float:
    if family in {"monotone", "curved", "spike"}:
        return base_score(family, point, target)
    if family in {"plateau", "checkerboard", "rugged"}:
        return unseen_score(family, point, target, landscape_seed)
    return audit_score(family, point, target)


def make_case(seed: int, family: str) -> dict:
    index = FAMILIES.index(family)
    rng = random.Random(43000 + seed * 20 + index)
    exploration = {x: tuple(rng.sample(range(5), 3)) for x in range(5)}
    target = (
        (rng.choice((0, 4)), rng.choice((0, 4)))
        if family == "monotone"
        else (rng.randrange(5), rng.randrange(5))
    )
    return {
        "seed": seed,
        "family": family,
        "target": target,
        "exploration": exploration,
        "landscape_seed": 53000 + seed * 20 + index,
    }


def evaluate(case: dict, candidate: tuple[float, float]) -> dict:
    r2_threshold, variance_threshold = candidate
    family = case["family"]
    target = case["target"]
    rng = random.Random(63000 + case["seed"] * 20 + FAMILIES.index(family))
    evaluated = []
    surrogate_uses = 0
    for x, ys in case["exploration"].items():
        observations = [
            (y, score(family, (x, y), target, case["landscape_seed"])) for y in ys
        ]
        evaluated.extend((x, y) for y in ys)
        slope, intercept, r_squared = fit_linear(observations)
        mean = math.fsum(value for _, value in observations) / len(observations)
        variance = math.fsum(
            (value - mean) ** 2 for _, value in observations
        ) / len(observations)
        unseen = [y for y in range(5) if y not in ys]
        if r_squared >= r2_threshold and variance >= variance_threshold:
            chosen = max(unseen, key=lambda y: (intercept + slope * y, y))
            surrogate_uses += 1
        else:
            chosen = rng.choice(unseen)
        evaluated.append((x, chosen))
    values = [
        score(family, point, target, case["landscape_seed"]) for point in evaluated
    ]
    return {
        "target_hit": target in evaluated,
        "best_score": max(values),
        "surrogate_uses": surrogate_uses,
    }


def evaluate_cohort(seed_start: int, seeds: int) -> dict:
    totals = {
        candidate: {
            family: {"hits": 0, "scores": 0.0, "uses": 0}
            for family in FAMILIES
        }
        for candidate in CANDIDATES
    }
    for seed in range(seed_start, seed_start + seeds):
        for family in FAMILIES:
            case = make_case(seed, family)
            for candidate in CANDIDATES:
                result = evaluate(case, candidate)
                item = totals[candidate][family]
                item["hits"] += int(result["target_hit"])
                item["scores"] += result["best_score"]
                item["uses"] += result["surrogate_uses"]
    summaries = {}
    for candidate, family_totals in totals.items():
        families = {
            family: {
                "target_hit_rate": values["hits"] / seeds,
                "mean_best_score": values["scores"] / seeds,
                "mean_surrogate_uses": values["uses"] / seeds,
            }
            for family, values in family_totals.items()
        }
        summaries[f"{candidate[0]}:{candidate[1]}"] = {
            "r_squared_threshold": candidate[0],
            "variance_threshold": candidate[1],
            "macro_target_hit_rate": math.fsum(
                families[family]["target_hit_rate"] for family in FAMILIES
            )
            / len(FAMILIES),
            "worst_family_target_hit_rate": min(
                families[family]["target_hit_rate"] for family in FAMILIES
            ),
            "families": families,
        }
    return summaries


def paired(
    seed_start: int,
    seeds: int,
    promoted: tuple[float, float],
    baseline: tuple[float, float],
) -> dict:
    deltas = []
    for seed in range(seed_start, seed_start + seeds):
        for family in FAMILIES:
            case = make_case(seed, family)
            winner = evaluate(case, promoted)
            control = evaluate(case, baseline)
            deltas.append(
                float(winner["target_hit"]) - float(control["target_hit"])
            )
    return {
        "target_hit_rate_delta": math.fsum(deltas) / len(deltas),
        "target_hit_rate_delta_95pct_bootstrap_ci": bootstrap_ci(deltas, 75000),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-seeds", type=int, default=1000)
    parser.add_argument("--validation-seeds", type=int, default=1000)
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E43-risk-router.json")
    )
    args = parser.parse_args()
    train = evaluate_cohort(0, args.train_seeds)
    winner = max(
        train.values(),
        key=lambda item: (
            item["worst_family_target_hit_rate"],
            item["macro_target_hit_rate"],
            item["variance_threshold"],
            item["r_squared_threshold"],
        ),
    )
    promoted = (winner["r_squared_threshold"], winner["variance_threshold"])
    validation = evaluate_cohort(args.train_seeds, args.validation_seeds)
    baseline = (1.01, 0.0)
    report = {
        "schema_version": 1,
        "experiment_id": "E43-risk-router",
        "claim_boundary": (
            "synthetic worst-family-first evolution and held-out validation of "
            "a scaffold router across nine known families"
        ),
        "candidate_count": len(CANDIDATES),
        "train_seeds": args.train_seeds,
        "validation_seeds": args.validation_seeds,
        "families": list(FAMILIES),
        "promotion_objective": "worst-family hit rate, then macro hit rate",
        "promoted": {
            "r_squared_threshold": promoted[0],
            "variance_threshold": promoted[1],
        },
        "train": train,
        "validation": validation[f"{promoted[0]}:{promoted[1]}"],
        "random_baseline_validation": validation[f"{baseline[0]}:{baseline[1]}"],
        "paired_promoted_minus_random": paired(
            args.train_seeds, args.validation_seeds, promoted, baseline
        ),
        "lineage": [
            {"generation": 2, "candidate": "R2 >= 0.5, variance >= 0.01", "source": "E41"},
            {
                "generation": 3,
                "candidate": f"R2 >= {promoted[0]}, variance >= {promoted[1]}",
                "source": "E43",
            },
        ],
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)
    print(f"promoted={report['promoted']}")
    print(
        f"validation macro={report['validation']['macro_target_hit_rate']:.1%} "
        f"worst={report['validation']['worst_family_target_hit_rate']:.1%}"
    )
    print(report["paired_promoted_minus_random"])


if __name__ == "__main__":
    main()
