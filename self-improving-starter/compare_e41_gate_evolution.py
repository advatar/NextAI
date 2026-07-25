"""E41: evolve a two-feature emitter gate across six landscape families."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path

from compare_selection import _atomic_json
from compare_e37_surrogate_generalization import bootstrap_ci, score as known_score
from compare_e38_adaptive_emitter import fit_linear
from compare_e40_unseen_families import score as unseen_score

FAMILIES = ("monotone", "curved", "spike", "plateau", "checkerboard", "rugged")
R2_THRESHOLDS = (0.0, 0.5, 0.8, 0.95, 1.01)
VARIANCE_THRESHOLDS = (0.0, 0.001, 0.01, 0.03)
CANDIDATES = tuple(
    (r2, variance) for r2 in R2_THRESHOLDS for variance in VARIANCE_THRESHOLDS
)


def landscape_score(
    family: str,
    point: tuple[int, int],
    target: tuple[int, int],
    landscape_seed: int,
) -> float:
    if family in {"monotone", "curved", "spike"}:
        return known_score(family, point, target)
    return unseen_score(family, point, target, landscape_seed)


def make_case(seed: int, family: str) -> dict:
    family_index = FAMILIES.index(family)
    rng = random.Random(41000 + seed * 20 + family_index)
    exploration = {x: tuple(rng.sample(range(5), 3)) for x in range(5)}
    if family == "monotone":
        target = (rng.choice((0, 4)), rng.choice((0, 4)))
    else:
        target = (rng.randrange(5), rng.randrange(5))
    return {
        "seed": seed,
        "family": family,
        "target": target,
        "exploration": exploration,
        "landscape_seed": 51000 + seed * 20 + family_index,
    }


def evaluate_rule(case: dict, r2_threshold: float, variance_threshold: float) -> dict:
    family = case["family"]
    target = case["target"]
    landscape_seed = case["landscape_seed"]
    rng = random.Random(61000 + case["seed"] * 20 + FAMILIES.index(family))
    evaluated = []
    surrogate_uses = 0
    for x, ys in case["exploration"].items():
        observations = [
            (y, landscape_score(family, (x, y), target, landscape_seed))
            for y in ys
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
        landscape_score(family, point, target, landscape_seed) for point in evaluated
    ]
    return {
        "target_hit": target in evaluated,
        "best_score": max(values),
        "surrogate_uses": surrogate_uses,
    }


def evaluate_candidates(seed_start: int, seeds: int) -> dict:
    aggregates = {
        candidate: {
            family: {"hits": 0, "score_sum": 0.0, "surrogate_uses": 0}
            for family in FAMILIES
        }
        for candidate in CANDIDATES
    }
    for seed in range(seed_start, seed_start + seeds):
        for family in FAMILIES:
            case = make_case(seed, family)
            for candidate in CANDIDATES:
                result = evaluate_rule(case, *candidate)
                bucket = aggregates[candidate][family]
                bucket["hits"] += int(result["target_hit"])
                bucket["score_sum"] += result["best_score"]
                bucket["surrogate_uses"] += result["surrogate_uses"]
    summaries = {}
    for candidate, families in aggregates.items():
        family_summary = {
            family: {
                "target_hit_rate": values["hits"] / seeds,
                "mean_best_score": values["score_sum"] / seeds,
                "mean_surrogate_uses": values["surrogate_uses"] / seeds,
            }
            for family, values in families.items()
        }
        summaries[f"{candidate[0]}:{candidate[1]}"] = {
            "r_squared_threshold": candidate[0],
            "variance_threshold": candidate[1],
            "macro_target_hit_rate": math.fsum(
                family_summary[family]["target_hit_rate"] for family in FAMILIES
            )
            / len(FAMILIES),
            "worst_family_target_hit_rate": min(
                family_summary[family]["target_hit_rate"] for family in FAMILIES
            ),
            "families": family_summary,
        }
    return summaries


def paired_validation(
    seed_start: int,
    seeds: int,
    promoted: tuple[float, float],
    baseline: tuple[float, float],
) -> dict:
    hit_deltas = []
    score_deltas = []
    for seed in range(seed_start, seed_start + seeds):
        for family in FAMILIES:
            case = make_case(seed, family)
            winner = evaluate_rule(case, *promoted)
            control = evaluate_rule(case, *baseline)
            hit_deltas.append(
                float(winner["target_hit"]) - float(control["target_hit"])
            )
            score_deltas.append(winner["best_score"] - control["best_score"])
    return {
        "target_hit_rate_delta": math.fsum(hit_deltas) / len(hit_deltas),
        "target_hit_rate_delta_95pct_bootstrap_ci": bootstrap_ci(
            hit_deltas, 71000
        ),
        "mean_best_score_delta": math.fsum(score_deltas) / len(score_deltas),
        "mean_best_score_delta_95pct_bootstrap_ci": bootstrap_ci(
            score_deltas, 72000
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-seeds", type=int, default=1000)
    parser.add_argument("--validation-seeds", type=int, default=1000)
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E41-gate-evolution.json")
    )
    args = parser.parse_args()
    train = evaluate_candidates(0, args.train_seeds)
    winner_item = max(
        train.values(),
        key=lambda item: (
            item["macro_target_hit_rate"],
            item["worst_family_target_hit_rate"],
            item["variance_threshold"],
            item["r_squared_threshold"],
        ),
    )
    promoted = (
        winner_item["r_squared_threshold"],
        winner_item["variance_threshold"],
    )
    validation = evaluate_candidates(args.train_seeds, args.validation_seeds)
    random_baseline = (1.01, 0.0)
    paired = paired_validation(
        args.train_seeds, args.validation_seeds, promoted, random_baseline
    )
    report = {
        "schema_version": 1,
        "experiment_id": "E41-gate-evolution",
        "claim_boundary": (
            "synthetic train/promote/held-out evolution of a two-feature scaffold "
            "gate across six families; no model-weight improvement claim"
        ),
        "candidate_count": len(CANDIDATES),
        "train_seeds": args.train_seeds,
        "validation_seeds": args.validation_seeds,
        "families": list(FAMILIES),
        "promotion_objective": "macro target hit rate, then worst-family hit rate",
        "promoted": {
            "r_squared_threshold": promoted[0],
            "variance_threshold": promoted[1],
        },
        "train": train,
        "validation": validation[f"{promoted[0]}:{promoted[1]}"],
        "random_baseline_validation": validation[
            f"{random_baseline[0]}:{random_baseline[1]}"
        ],
        "paired_promoted_minus_random": paired,
        "lineage": [
            {"generation": 0, "candidate": "R2 >= 0.8", "source": "E38"},
            {"generation": 1, "candidate": "R2 >= 0.0", "source": "E39"},
            {
                "generation": 2,
                "candidate": (
                    f"R2 >= {promoted[0]} and variance >= {promoted[1]}"
                ),
                "source": "E41",
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
    print(f"paired_vs_random={paired}")


if __name__ == "__main__":
    main()
