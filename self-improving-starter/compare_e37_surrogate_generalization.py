"""E37: prospective surrogate generalization stress test under matched budgets."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path

from compare_selection import _atomic_json
from analyze_e36_surrogate import recommend

FAMILIES = ("monotone", "curved", "spike")
POLICIES = ("random_exploitation", "linear_surrogate")


def bootstrap_ci(values: list[float], seed: int, samples: int = 5000) -> list[float]:
    rng = random.Random(seed)
    size = len(values)
    estimates = sorted(
        math.fsum(values[rng.randrange(size)] for _ in range(size)) / size
        for _ in range(samples)
    )
    return [estimates[int(samples * 0.025)], estimates[int(samples * 0.975)]]


def score(
    family: str, point: tuple[int, int], target: tuple[int, int]
) -> float:
    x, y = point
    tx, ty = target
    if family == "monotone":
        x_term = x / 4 if tx == 4 else (4 - x) / 4
        y_term = y / 4 if ty == 4 else (4 - y) / 4
        return (x_term + y_term) / 2
    if family == "curved":
        return 1.0 - ((x - tx) ** 2 + (y - ty) ** 2) / 32
    return 1.0 if point == target else 0.2 + 0.02 * ((x + y) % 5)


def run_policy(
    family: str,
    policy: str,
    target: tuple[int, int],
    exploration: dict[int, tuple[int, int]],
    seed: int,
) -> dict:
    rng = random.Random(seed)
    evaluated = []
    observations = {}
    for x, ys in exploration.items():
        observations[x] = [(y, score(family, (x, y), target)) for y in ys]
        evaluated.extend((x, y) for y in ys)
    exploitation = []
    for x in range(5):
        observed = observations[x]
        unseen = [y for y in range(5) if y not in {item[0] for item in observed}]
        if policy == "linear_surrogate":
            chosen, slope, predicted = recommend(observed)
        else:
            chosen = rng.choice(unseen)
            slope = None
            predicted = None
        exploitation.append(
            {
                "x": x,
                "y": chosen,
                "estimated_slope": slope,
                "predicted_score": predicted,
                "actual_score": score(family, (x, chosen), target),
            }
        )
        evaluated.append((x, chosen))
    values = [score(family, point, target) for point in evaluated]
    return {
        "family": family,
        "policy": policy,
        "target": list(target),
        "candidate_evaluations": len(evaluated),
        "best_score": max(values),
        "target_hit": target in evaluated,
        "exploitation": exploitation,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=1000)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("experiments/E37-surrogate-generalization.json"),
    )
    args = parser.parse_args()
    runs = []
    for seed in range(args.seeds):
        setup_rng = random.Random(37000 + seed)
        exploration = {
            x: tuple(setup_rng.sample(range(5), 2)) for x in range(5)
        }
        targets = {
            "monotone": (
                setup_rng.choice((0, 4)),
                setup_rng.choice((0, 4)),
            ),
            "curved": (setup_rng.randrange(5), setup_rng.randrange(5)),
            "spike": (setup_rng.randrange(5), setup_rng.randrange(5)),
        }
        for family in FAMILIES:
            for policy_index, policy in enumerate(POLICIES):
                runs.append(
                    run_policy(
                        family,
                        policy,
                        targets[family],
                        exploration,
                        38000 + seed * 10 + policy_index,
                    )
                )
    summaries = {}
    for family in FAMILIES:
        summaries[family] = {}
        for policy in POLICIES:
            cohort = [
                run
                for run in runs
                if run["family"] == family and run["policy"] == policy
            ]
            summaries[family][policy] = {
                "runs": len(cohort),
                "mean_best_score": math.fsum(run["best_score"] for run in cohort)
                / len(cohort),
                "target_hit_rate": sum(run["target_hit"] for run in cohort)
                / len(cohort),
                "candidate_evaluations_per_run": 15,
            }
        # Runs are appended in seed/policy order, so pair by cohort position.
        random_cohort = [
            run
            for run in runs
            if run["family"] == family and run["policy"] == "random_exploitation"
        ]
        surrogate_cohort = [
            run
            for run in runs
            if run["family"] == family and run["policy"] == "linear_surrogate"
        ]
        score_deltas = [
            surrogate["best_score"] - random_run["best_score"]
            for random_run, surrogate in zip(random_cohort, surrogate_cohort)
        ]
        hit_deltas = [
            float(surrogate["target_hit"]) - float(random_run["target_hit"])
            for random_run, surrogate in zip(random_cohort, surrogate_cohort)
        ]
        summaries[family]["paired_linear_minus_random"] = {
            "mean_best_score_delta": math.fsum(score_deltas) / len(score_deltas),
            "mean_best_score_delta_95pct_bootstrap_ci": bootstrap_ci(
                score_deltas, 39000 + FAMILIES.index(family)
            ),
            "target_hit_rate_delta": math.fsum(hit_deltas) / len(hit_deltas),
            "target_hit_rate_delta_95pct_bootstrap_ci": bootstrap_ci(
                hit_deltas, 40000 + FAMILIES.index(family)
            ),
        }
    report = {
        "schema_version": 1,
        "experiment_id": "E37-surrogate-generalization",
        "claim_boundary": (
            "prospective deterministic synthetic stress test of a two-sample "
            "linear surrogate; no model-learning claim"
        ),
        "seeds": args.seeds,
        "families": list(FAMILIES),
        "policies": list(POLICIES),
        "matched_budget": all(run["candidate_evaluations"] == 15 for run in runs),
        "summaries": summaries,
        "runs": runs,
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)
    for family in FAMILIES:
        print(family)
        for policy in POLICIES:
            item = summaries[family][policy]
            print(
                f"  {policy:20} mean={item['mean_best_score']:.3f} "
                f"hit={item['target_hit_rate']:.1%}"
            )


if __name__ == "__main__":
    main()
