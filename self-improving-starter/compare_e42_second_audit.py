"""E42: second unseen-family audit of E41's promoted gate."""
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

FAMILIES = ("ridge", "sinusoidal", "decoy")
POLICIES = ("random", "always_surrogate", "e41_promoted")


def score(
    family: str, point: tuple[int, int], target: tuple[int, int]
) -> float:
    if point == target:
        return 1.0
    x, y = point
    tx, ty = target
    if family == "ridge":
        return 0.2 + 0.6 * (1 - abs((x - y) - (tx - ty)) / 8)
    if family == "sinusoidal":
        return 0.5 + 0.3 * math.sin((x + 1) * (y + 1))
    decoy = (4 - tx, 4 - ty)
    if point == decoy:
        return 0.9
    return 0.1 + 0.1 * ((x + 2 * y) % 5)


def run(
    family: str,
    policy: str,
    target: tuple[int, int],
    exploration: dict[int, tuple[int, int, int]],
    seed: int,
) -> dict:
    rng = random.Random(seed)
    evaluated = []
    surrogate_uses = 0
    for x, ys in exploration.items():
        observations = [(y, score(family, (x, y), target)) for y in ys]
        evaluated.extend((x, y) for y in ys)
        slope, intercept, r_squared = fit_linear(observations)
        mean = math.fsum(value for _, value in observations) / len(observations)
        variance = math.fsum(
            (value - mean) ** 2 for _, value in observations
        ) / len(observations)
        unseen = [y for y in range(5) if y not in ys]
        use_surrogate = policy == "always_surrogate" or (
            policy == "e41_promoted"
            and r_squared >= 0.5
            and variance >= 0.01
        )
        if use_surrogate:
            chosen = max(unseen, key=lambda y: (intercept + slope * y, y))
            surrogate_uses += 1
        else:
            chosen = rng.choice(unseen)
        evaluated.append((x, chosen))
    values = [score(family, point, target) for point in evaluated]
    return {
        "family": family,
        "policy": policy,
        "target_hit": target in evaluated,
        "best_score": max(values),
        "surrogate_uses": surrogate_uses,
        "candidate_evaluations": len(evaluated),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=1000)
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E42-second-audit.json")
    )
    args = parser.parse_args()
    runs = []
    for seed in range(args.seeds):
        rng = random.Random(42000 + seed)
        exploration = {x: tuple(rng.sample(range(5), 3)) for x in range(5)}
        targets = {family: (rng.randrange(5), rng.randrange(5)) for family in FAMILIES}
        for family_index, family in enumerate(FAMILIES):
            for policy_index, policy in enumerate(POLICIES):
                runs.append(
                    run(
                        family,
                        policy,
                        targets[family],
                        exploration,
                        73000 + seed * 10 + family_index * 3 + policy_index,
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
                "mean_surrogate_uses": math.fsum(
                    item["surrogate_uses"] for item in cohort
                )
                / len(cohort),
            }
        deltas = [
            float(promoted["target_hit"]) - float(control["target_hit"])
            for control, promoted in zip(
                cohorts["random"], cohorts["e41_promoted"]
            )
        ]
        summaries[family]["paired_promoted_minus_random"] = {
            "target_hit_rate_delta": math.fsum(deltas) / len(deltas),
            "target_hit_rate_delta_95pct_bootstrap_ci": bootstrap_ci(
                deltas, 74000 + family_index
            ),
        }
    report = {
        "schema_version": 1,
        "experiment_id": "E42-second-audit",
        "claim_boundary": (
            "second held-out synthetic family audit of E41's promoted scaffold "
            "gate; no model-weight improvement claim"
        ),
        "source_policy": "E41 R2 >= 0.5 and variance >= 0.01",
        "seeds": args.seeds,
        "families": list(FAMILIES),
        "matched_budget": all(run["candidate_evaluations"] == 20 for run in runs),
        "summaries": summaries,
        "runs": runs,
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)
    for family in FAMILIES:
        item = summaries[family]
        delta = item["paired_promoted_minus_random"]
        print(
            f"{family:10} random={item['random']['target_hit_rate']:.1%} "
            f"promoted={item['e41_promoted']['target_hit_rate']:.1%} "
            f"delta={delta['target_hit_rate_delta']:+.1%}"
        )


if __name__ == "__main__":
    main()
