"""E49: route between linear, quadratic, and random exploitation."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path

from compare_selection import _atomic_json
from compare_e37_surrogate_generalization import FAMILIES, bootstrap_ci, score
from compare_e38_adaptive_emitter import fit_linear

POLICIES = ("random", "linear", "quadratic", "shape_router")


def quadratic_predict(observations: list[tuple[int, float]], y: int) -> float:
    prediction = 0.0
    for index, (yi, value) in enumerate(observations):
        basis = 1.0
        for other_index, (yj, _) in enumerate(observations):
            if index != other_index:
                basis *= (y - yj) / (yi - yj)
        prediction += value * basis
    return prediction


def quadratic_coefficient(observations: list[tuple[int, float]]) -> float:
    points = sorted(observations)
    first_left = (points[1][1] - points[0][1]) / (points[1][0] - points[0][0])
    first_right = (points[2][1] - points[1][1]) / (
        points[2][0] - points[1][0]
    )
    return (first_right - first_left) / (points[2][0] - points[0][0])


def choose(
    policy: str,
    observations: list[tuple[int, float]],
    unseen: list[int],
    rng: random.Random,
) -> tuple[int, str]:
    slope, intercept, r_squared = fit_linear(observations)
    mean = math.fsum(value for _, value in observations) / len(observations)
    variance = math.fsum(
        (value - mean) ** 2 for _, value in observations
    ) / len(observations)
    curvature = quadratic_coefficient(observations)
    selected = policy
    if policy == "shape_router":
        if curvature < -0.01:
            selected = "quadratic"
        elif r_squared >= 0.5 and variance >= 0.01:
            selected = "linear"
        else:
            selected = "random"
    if selected == "quadratic":
        return (
            max(unseen, key=lambda y: (quadratic_predict(observations, y), y)),
            selected,
        )
    if selected == "linear":
        return max(unseen, key=lambda y: (intercept + slope * y, y)), selected
    return rng.choice(unseen), selected


def run(
    family: str,
    policy: str,
    target: tuple[int, int],
    exploration: dict[int, tuple[int, int, int]],
    seed: int,
) -> dict:
    rng = random.Random(seed)
    evaluated = []
    choices = []
    for x, ys in exploration.items():
        observations = [(y, score(family, (x, y), target)) for y in ys]
        evaluated.extend((x, y) for y in ys)
        unseen = [y for y in range(5) if y not in ys]
        chosen, selected = choose(policy, observations, unseen, rng)
        evaluated.append((x, chosen))
        choices.append({"x": x, "selected_model": selected, "chosen_y": chosen})
    values = [score(family, point, target) for point in evaluated]
    return {
        "family": family,
        "policy": policy,
        "target_hit": target in evaluated,
        "best_score": max(values),
        "candidate_evaluations": len(evaluated),
        "choices": choices,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=1000)
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E49-shape-router.json")
    )
    args = parser.parse_args()
    runs = []
    for seed in range(args.seeds):
        rng = random.Random(49000 + seed)
        exploration = {x: tuple(rng.sample(range(5), 3)) for x in range(5)}
        targets = {
            "monotone": (rng.choice((0, 4)), rng.choice((0, 4))),
            "curved": (rng.randrange(5), rng.randrange(5)),
            "spike": (rng.randrange(5), rng.randrange(5)),
        }
        for family_index, family in enumerate(FAMILIES):
            for policy_index, policy in enumerate(POLICIES):
                runs.append(
                    run(
                        family,
                        policy,
                        targets[family],
                        exploration,
                        89000 + seed * 20 + family_index * 4 + policy_index,
                    )
                )
    summaries = {}
    for family_index, family in enumerate(FAMILIES):
        summaries[family] = {}
        cohorts = {}
        for policy in POLICIES:
            cohort = [
                item
                for item in runs
                if item["family"] == family and item["policy"] == policy
            ]
            cohorts[policy] = cohort
            summaries[family][policy] = {
                "target_hit_rate": sum(item["target_hit"] for item in cohort)
                / len(cohort),
                "mean_best_score": math.fsum(item["best_score"] for item in cohort)
                / len(cohort),
            }
        for control_name in ("random", "linear"):
            deltas = [
                float(router["target_hit"]) - float(control["target_hit"])
                for control, router in zip(
                    cohorts[control_name], cohorts["shape_router"]
                )
            ]
            summaries[family][f"paired_router_minus_{control_name}"] = {
                "target_hit_rate_delta": math.fsum(deltas) / len(deltas),
                "target_hit_rate_delta_95pct_bootstrap_ci": bootstrap_ci(
                    deltas,
                    90000 + family_index * 2 + (control_name == "linear"),
                ),
            }
    report = {
        "schema_version": 1,
        "experiment_id": "E49-shape-router",
        "claim_boundary": (
            "prospective synthetic comparison of linear, quadratic, random, "
            "and shape-routed scaffold exploitation"
        ),
        "seeds": args.seeds,
        "families": list(FAMILIES),
        "policies": list(POLICIES),
        "matched_budget": all(item["candidate_evaluations"] == 20 for item in runs),
        "summaries": summaries,
        "runs": runs,
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)
    for family in FAMILIES:
        print(family)
        for policy in POLICIES:
            print(
                f"  {policy:12} {summaries[family][policy]['target_hit_rate']:.1%}"
            )


if __name__ == "__main__":
    main()
