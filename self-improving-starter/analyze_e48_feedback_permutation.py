"""E48: exact score-label permutation audit of E46's learned exploitation."""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import random
from pathlib import Path

from compare_selection import _atomic_json
from compare_e37_surrogate_generalization import score
from compare_e38_adaptive_emitter import fit_linear


def exploit(
    observations: dict[int, list[tuple[int, float]]], family_index: int
) -> list[tuple[int, int]]:
    rng = random.Random(4600 + family_index)
    chosen = []
    for x in range(5):
        items = observations[x]
        seen = {y for y, _ in items}
        unseen = [y for y in range(5) if y not in seen]
        slope, intercept, r_squared = fit_linear(items)
        mean = math.fsum(value for _, value in items) / len(items)
        variance = math.fsum((value - mean) ** 2 for _, value in items) / len(items)
        if r_squared >= 0.5 and variance >= 0.01:
            y = max(unseen, key=lambda value: (intercept + slope * value, value))
        else:
            y = rng.choice(unseen)
        chosen.append((x, y))
        # E46 also drew the matched random-control candidate after each guard
        # decision, advancing this deterministic counterfactual stream.
        rng.choice(unseen)
    return chosen


def main() -> None:
    source = json.loads(Path("experiments/E46-real-router.json").read_text())
    results = []
    for family_index, task in enumerate(source["tasks"]):
        family = task["family"]
        target = tuple(task["target"])
        observations = {x: [] for x in range(5)}
        for row in task["exploration"]:
            observations[int(row["x"])].append((int(row["y"]), float(row["score"])))
        explored = {
            (x, y) for x, items in observations.items() for y, _ in items
        }
        true_points = explored | set(exploit(observations, family_index))
        true_best = max(score(family, point, target) for point in true_points)
        row_permutations = [
            list(itertools.permutations([value for _, value in observations[x]]))
            for x in range(5)
        ]
        null_hits = 0
        null_best_sum = 0.0
        null_count = 0
        for permutation_set in itertools.product(*row_permutations):
            permuted = {
                x: [
                    (observations[x][index][0], permutation_set[x][index])
                    for index in range(3)
                ]
                for x in range(5)
            }
            points = explored | set(exploit(permuted, family_index))
            null_hits += int(target in points)
            null_best_sum += max(score(family, point, target) for point in points)
            null_count += 1
        results.append(
            {
                "family": family,
                "permutations": null_count,
                "true_target_hit": target in true_points,
                "true_best_score": true_best,
                "permuted_target_hit_rate": null_hits / null_count,
                "permuted_mean_best_score": null_best_sum / null_count,
                "true_minus_permuted_expected_best_score": true_best
                - null_best_sum / null_count,
            }
        )
    report = {
        "schema_version": 1,
        "experiment_id": "E48-feedback-permutation",
        "claim_boundary": (
            "exact within-row score-label permutation audit over E46's single "
            "real-model exploration archives"
        ),
        "source_experiment": "E46-real-router",
        "tasks": results,
        "all_true_target_hits": all(item["true_target_hit"] for item in results),
        "mean_permuted_target_hit_rate": math.fsum(
            item["permuted_target_hit_rate"] for item in results
        )
        / len(results),
        "mean_true_minus_permuted_expected_best_score": math.fsum(
            item["true_minus_permuted_expected_best_score"] for item in results
        )
        / len(results),
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(Path("experiments/E48-feedback-permutation.json"), report)
    for item in results:
        print(
            f"{item['family']}: true={item['true_best_score']:.3f} "
            f"permuted_hit={item['permuted_target_hit_rate']:.1%} "
            f"score_delta={item['true_minus_permuted_expected_best_score']:+.3f}"
        )


if __name__ == "__main__":
    main()
