"""E47: exact fallback enumeration over E46's real-Gemma exploration archive."""
from __future__ import annotations

import hashlib
import itertools
import json
import math
from pathlib import Path

from compare_selection import _atomic_json
from compare_e37_surrogate_generalization import score


def main() -> None:
    source = json.loads(Path("experiments/E46-real-router.json").read_text())
    tasks = []
    for task in source["tasks"]:
        family = task["family"]
        target = tuple(task["target"])
        explored = {
            (int(row["x"]), int(row["y"]))
            for row in task["exploration"]
            if row["y"] is not None
        }
        unseen_by_x = {
            x: [y for y in range(5) if (x, y) not in explored] for x in range(5)
        }
        combinations = list(
            itertools.product(*(unseen_by_x[x] for x in range(5)))
        )
        counterfactuals = []
        for ys in combinations:
            points = explored | {(x, y) for x, y in enumerate(ys)}
            values = [score(family, point, target) for point in points]
            counterfactuals.append(
                {
                    "ys": list(ys),
                    "target_hit": target in points,
                    "best_score": max(values),
                }
            )
        guard = task["summaries"]["support_guard"]
        random_hit_rate = sum(item["target_hit"] for item in counterfactuals) / len(
            counterfactuals
        )
        random_mean_best = math.fsum(
            item["best_score"] for item in counterfactuals
        ) / len(counterfactuals)
        tasks.append(
            {
                "family": family,
                "counterfactual_count": len(counterfactuals),
                "guard_target_hit": guard["target_hit"],
                "guard_best_score": guard["best_score"],
                "exact_random_target_hit_rate": random_hit_rate,
                "exact_random_mean_best_score": random_mean_best,
                "guard_minus_random_expected_best_score": guard["best_score"]
                - random_mean_best,
                "counterfactuals": counterfactuals,
            }
        )
    report = {
        "schema_version": 1,
        "experiment_id": "E47-exact-counterfactual",
        "claim_boundary": (
            "exact enumeration of fallback exploitation choices over E46's "
            "single real-model exploration archives"
        ),
        "source_experiment": "E46-real-router",
        "tasks": tasks,
        "guard_target_hits": sum(task["guard_target_hit"] for task in tasks),
        "mean_exact_random_target_hit_rate": math.fsum(
            task["exact_random_target_hit_rate"] for task in tasks
        )
        / len(tasks),
        "mean_guard_minus_random_expected_best_score": math.fsum(
            task["guard_minus_random_expected_best_score"] for task in tasks
        )
        / len(tasks),
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(Path("experiments/E47-exact-counterfactual.json"), report)
    for task in tasks:
        print(
            f"{task['family']}: guard={task['guard_best_score']:.3f} "
            f"random_hit={task['exact_random_target_hit_rate']:.1%} "
            f"expected_delta={task['guard_minus_random_expected_best_score']:+.3f}"
        )


if __name__ == "__main__":
    main()
