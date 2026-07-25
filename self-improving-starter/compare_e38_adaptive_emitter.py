"""E38: confidence-gated surrogate versus fixed emitters."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path

from compare_selection import _atomic_json
from compare_e37_surrogate_generalization import FAMILIES, bootstrap_ci, score

POLICIES = ("random_exploitation", "linear_surrogate", "adaptive")


def fit_linear(observations: list[tuple[int, float]]) -> tuple[float, float, float]:
    mean_y = math.fsum(y for y, _ in observations) / len(observations)
    mean_score = math.fsum(value for _, value in observations) / len(observations)
    denominator = math.fsum((y - mean_y) ** 2 for y, _ in observations)
    slope = (
        0.0
        if denominator == 0
        else math.fsum(
            (y - mean_y) * (value - mean_score) for y, value in observations
        )
        / denominator
    )
    intercept = mean_score - slope * mean_y
    residual = math.fsum(
        (value - (intercept + slope * y)) ** 2 for y, value in observations
    )
    total = math.fsum((value - mean_score) ** 2 for _, value in observations)
    r_squared = 1.0 if total == 0 and residual == 0 else 1.0 - residual / total
    return slope, intercept, r_squared


def run_policy(
    family: str,
    policy: str,
    target: tuple[int, int],
    exploration: dict[int, tuple[int, int, int]],
    seed: int,
    threshold: float,
) -> dict:
    rng = random.Random(seed)
    evaluated = []
    exploit_rows = []
    surrogate_uses = 0
    for x, ys in exploration.items():
        observations = [(y, score(family, (x, y), target)) for y in ys]
        evaluated.extend((x, y) for y in ys)
        slope, intercept, r_squared = fit_linear(observations)
        unseen = [y for y in range(5) if y not in ys]
        use_surrogate = policy == "linear_surrogate" or (
            policy == "adaptive" and r_squared >= threshold
        )
        if use_surrogate:
            chosen = max(unseen, key=lambda y: (intercept + slope * y, y))
            surrogate_uses += 1
        else:
            chosen = rng.choice(unseen)
        evaluated.append((x, chosen))
        exploit_rows.append(
            {
                "x": x,
                "r_squared": r_squared,
                "used_surrogate": use_surrogate,
                "chosen_y": chosen,
            }
        )
    values = [score(family, point, target) for point in evaluated]
    return {
        "family": family,
        "policy": policy,
        "target": list(target),
        "candidate_evaluations": len(evaluated),
        "best_score": max(values),
        "target_hit": target in evaluated,
        "surrogate_uses": surrogate_uses,
        "exploit_rows": exploit_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=1000)
    parser.add_argument("--threshold", type=float, default=0.8)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("experiments/E38-adaptive-emitter.json"),
    )
    args = parser.parse_args()
    runs = []
    for seed in range(args.seeds):
        setup_rng = random.Random(38000 + seed)
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
        for family in FAMILIES:
            for policy_index, policy in enumerate(POLICIES):
                runs.append(
                    run_policy(
                        family,
                        policy,
                        targets[family],
                        exploration,
                        41000 + seed * 10 + policy_index,
                        args.threshold,
                    )
                )
    summaries = {}
    for family_index, family in enumerate(FAMILIES):
        summaries[family] = {}
        cohorts = {}
        for policy in POLICIES:
            cohort = [
                run
                for run in runs
                if run["family"] == family and run["policy"] == policy
            ]
            cohorts[policy] = cohort
            summaries[family][policy] = {
                "runs": len(cohort),
                "mean_best_score": math.fsum(run["best_score"] for run in cohort)
                / len(cohort),
                "target_hit_rate": sum(run["target_hit"] for run in cohort)
                / len(cohort),
                "mean_surrogate_uses": math.fsum(
                    run["surrogate_uses"] for run in cohort
                )
                / len(cohort),
                "candidate_evaluations_per_run": 20,
            }
        adaptive = cohorts["adaptive"]
        random_cohort = cohorts["random_exploitation"]
        hit_deltas = [
            float(a["target_hit"]) - float(r["target_hit"])
            for r, a in zip(random_cohort, adaptive)
        ]
        summaries[family]["paired_adaptive_minus_random"] = {
            "target_hit_rate_delta": math.fsum(hit_deltas) / len(hit_deltas),
            "target_hit_rate_delta_95pct_bootstrap_ci": bootstrap_ci(
                hit_deltas, 42000 + family_index
            ),
        }
    report = {
        "schema_version": 1,
        "experiment_id": "E38-adaptive-emitter",
        "claim_boundary": (
            "prospective deterministic synthetic comparison of confidence-gated "
            "linear and random exploitation; no model-learning claim"
        ),
        "seeds": args.seeds,
        "r_squared_threshold": args.threshold,
        "families": list(FAMILIES),
        "policies": list(POLICIES),
        "matched_budget": all(run["candidate_evaluations"] == 20 for run in runs),
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
                f"  {policy:20} hit={item['target_hit_rate']:.1%} "
                f"surrogate_uses={item['mean_surrogate_uses']:.2f}"
            )


if __name__ == "__main__":
    main()
