"""E39: tune an adaptive-emitter threshold, promote it, then validate held out."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path

from compare_selection import _atomic_json
from compare_e37_surrogate_generalization import FAMILIES, bootstrap_ci
from compare_e38_adaptive_emitter import run_policy

THRESHOLDS = (0.0, 0.25, 0.5, 0.75, 0.9, 1.01)


def cohort(seed_start: int, seeds: int, thresholds: tuple[float, ...]) -> list[dict]:
    runs = []
    for offset in range(seeds):
        seed = seed_start + offset
        setup_rng = random.Random(39000 + seed)
        exploration = {
            x: tuple(setup_rng.sample(range(5), 3)) for x in range(5)
        }
        targets = {
            "monotone": (
                setup_rng.choice((0, 4)),
                setup_rng.choice((0, 4)),
            ),
            "curved": (setup_rng.randrange(5), setup_rng.randrange(5)),
            "spike": (setup_rng.randrange(5), setup_rng.randrange(5)),
        }
        for family_index, family in enumerate(FAMILIES):
            for candidate_index, threshold in enumerate(thresholds):
                run = run_policy(
                    family,
                    "adaptive",
                    targets[family],
                    exploration,
                    43000 + seed * 100 + family_index * 10 + candidate_index,
                    threshold,
                )
                run["threshold"] = threshold
                run["seed"] = seed
                runs.append(run)
    return runs


def summarize(runs: list[dict], thresholds: tuple[float, ...]) -> dict:
    result = {}
    for threshold in thresholds:
        threshold_runs = [run for run in runs if run["threshold"] == threshold]
        families = {}
        for family in FAMILIES:
            family_runs = [
                run for run in threshold_runs if run["family"] == family
            ]
            families[family] = {
                "target_hit_rate": sum(run["target_hit"] for run in family_runs)
                / len(family_runs),
                "mean_best_score": math.fsum(
                    run["best_score"] for run in family_runs
                )
                / len(family_runs),
                "mean_surrogate_uses": math.fsum(
                    run["surrogate_uses"] for run in family_runs
                )
                / len(family_runs),
            }
        result[str(threshold)] = {
            "macro_target_hit_rate": math.fsum(
                families[family]["target_hit_rate"] for family in FAMILIES
            )
            / len(FAMILIES),
            "worst_family_target_hit_rate": min(
                families[family]["target_hit_rate"] for family in FAMILIES
            ),
            "families": families,
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-seeds", type=int, default=1000)
    parser.add_argument("--validation-seeds", type=int, default=1000)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("experiments/E39-threshold-evolution.json"),
    )
    args = parser.parse_args()
    train_runs = cohort(0, args.train_seeds, THRESHOLDS)
    train_summary = summarize(train_runs, THRESHOLDS)
    winner = max(
        THRESHOLDS,
        key=lambda threshold: (
            train_summary[str(threshold)]["macro_target_hit_rate"],
            train_summary[str(threshold)]["worst_family_target_hit_rate"],
            threshold,
        ),
    )
    validation_candidates = tuple(dict.fromkeys((winner, 0.0, 1.01)))
    validation_runs = cohort(
        args.train_seeds, args.validation_seeds, validation_candidates
    )
    validation_summary = summarize(validation_runs, validation_candidates)
    winner_runs = [
        run for run in validation_runs if run["threshold"] == winner
    ]
    random_runs = [
        run for run in validation_runs if run["threshold"] == 1.01
    ]
    hit_deltas = [
        float(w["target_hit"]) - float(r["target_hit"])
        for w, r in zip(winner_runs, random_runs)
    ]
    report = {
        "schema_version": 1,
        "experiment_id": "E39-threshold-evolution",
        "claim_boundary": (
            "synthetic train/promote/held-out validation loop for one emitter "
            "hyperparameter; improves the scaffold, not model weights"
        ),
        "candidate_thresholds": list(THRESHOLDS),
        "train_seeds": args.train_seeds,
        "validation_seeds": args.validation_seeds,
        "promotion_objective": "macro target hit rate, then worst-family hit rate",
        "promoted_threshold": winner,
        "train": train_summary,
        "validation": validation_summary,
        "validation_promoted_minus_random_target_delta": math.fsum(hit_deltas)
        / len(hit_deltas),
        "validation_promoted_minus_random_95pct_bootstrap_ci": bootstrap_ci(
            hit_deltas, 44000
        ),
        "lineage": [
            {
                "generation": 0,
                "candidate": "R2 threshold 0.8",
                "source": "E38",
            },
            {
                "generation": 1,
                "candidate": f"R2 threshold {winner}",
                "source": "E39 training promotion",
            },
        ],
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)
    print(f"promoted_threshold={winner}")
    print(
        "validation_delta="
        f"{report['validation_promoted_minus_random_target_delta']:+.1%} "
        f"ci={report['validation_promoted_minus_random_95pct_bootstrap_ci']}"
    )
    for threshold in validation_candidates:
        item = validation_summary[str(threshold)]
        print(
            f"threshold={threshold} macro={item['macro_target_hit_rate']:.1%} "
            f"worst={item['worst_family_target_hit_rate']:.1%}"
        )


if __name__ == "__main__":
    main()
