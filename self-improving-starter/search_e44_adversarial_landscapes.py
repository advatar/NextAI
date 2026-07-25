"""E44: search random finite landscapes for E43 router counterexamples."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path

from compare_selection import _atomic_json
from compare_e37_surrogate_generalization import bootstrap_ci
from compare_e38_adaptive_emitter import fit_linear


def evaluate(
    table: list[list[float]],
    exploration: dict[int, tuple[int, int, int]],
    policy: str,
    seed: int,
) -> dict:
    rng = random.Random(seed)
    evaluated = []
    for x, ys in exploration.items():
        observations = [(y, table[x][y]) for y in ys]
        evaluated.extend((x, y) for y in ys)
        slope, intercept, r_squared = fit_linear(observations)
        mean = math.fsum(value for _, value in observations) / len(observations)
        variance = math.fsum(
            (value - mean) ** 2 for _, value in observations
        ) / len(observations)
        unseen = [y for y in range(5) if y not in ys]
        if policy == "promoted" and r_squared >= 0.5 and variance >= 0.03:
            chosen = max(unseen, key=lambda y: (intercept + slope * y, y))
        else:
            chosen = rng.choice(unseen)
        evaluated.append((x, chosen))
    target = max(
        ((x, y) for x in range(5) for y in range(5)),
        key=lambda point: table[point[0]][point[1]],
    )
    return {
        "target_hit": target in evaluated,
        "best_score": max(table[x][y] for x, y in evaluated),
        "target": target,
        "evaluated": evaluated,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--landscapes", type=int, default=10000)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("experiments/E44-adversarial-landscapes.json"),
    )
    args = parser.parse_args()
    rows = []
    for landscape_seed in range(args.landscapes):
        rng = random.Random(44000 + landscape_seed)
        table = [[rng.random() for _ in range(5)] for _ in range(5)]
        exploration = {x: tuple(rng.sample(range(5), 3)) for x in range(5)}
        action_seed = 84000 + landscape_seed
        control = evaluate(table, exploration, "random", action_seed)
        promoted = evaluate(table, exploration, "promoted", action_seed)
        rows.append(
            {
                "landscape_seed": landscape_seed,
                "target": list(control["target"]),
                "random_target_hit": control["target_hit"],
                "promoted_target_hit": promoted["target_hit"],
                "target_hit_delta": int(promoted["target_hit"])
                - int(control["target_hit"]),
                "random_best_score": control["best_score"],
                "promoted_best_score": promoted["best_score"],
                "best_score_delta": promoted["best_score"]
                - control["best_score"],
                "table": table,
            }
        )
    hit_deltas = [row["target_hit_delta"] for row in rows]
    score_deltas = [row["best_score_delta"] for row in rows]
    worst = sorted(rows, key=lambda row: row["best_score_delta"])[:50]
    report = {
        "schema_version": 1,
        "experiment_id": "E44-adversarial-landscapes",
        "claim_boundary": (
            "adversarial search over deterministic random 5x5 score tables for "
            "counterexamples to E43's scaffold router"
        ),
        "source_policy": "E43 R2 >= 0.5 and variance >= 0.03",
        "landscapes": args.landscapes,
        "promoted_minus_random_target_hit_delta": math.fsum(hit_deltas)
        / len(hit_deltas),
        "target_hit_delta_95pct_bootstrap_ci": bootstrap_ci(hit_deltas, 85000),
        "promoted_minus_random_mean_best_score_delta": math.fsum(score_deltas)
        / len(score_deltas),
        "best_score_delta_95pct_bootstrap_ci": bootstrap_ci(score_deltas, 86000),
        "promoted_missed_random_hit": sum(
            row["target_hit_delta"] == -1 for row in rows
        ),
        "promoted_hit_random_missed": sum(
            row["target_hit_delta"] == 1 for row in rows
        ),
        "worst_counterexamples": worst,
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)
    print(
        f"hit_delta={report['promoted_minus_random_target_hit_delta']:+.2%} "
        f"score_delta={report['promoted_minus_random_mean_best_score_delta']:+.4f}"
    )
    print(
        f"promoted_missed={report['promoted_missed_random_hit']} "
        f"promoted_found={report['promoted_hit_random_missed']} "
        f"worst_score_delta={worst[0]['best_score_delta']:+.4f}"
    )


if __name__ == "__main__":
    main()
