"""E40: audit E39's promoted emitter on unseen landscape families."""
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

FAMILIES = ("plateau", "checkerboard", "rugged")
POLICIES = ("random_exploitation", "e39_promoted_surrogate")


def score(
    family: str, point: tuple[int, int], target: tuple[int, int], seed: int
) -> float:
    if point == target:
        return 1.0
    x, y = point
    if family == "plateau":
        return 0.4
    if family == "checkerboard":
        return 0.55 if (x + y) % 2 == 0 else 0.25
    digest = hashlib.sha256(f"{seed}:{x}:{y}".encode()).digest()
    return 0.1 + 0.7 * int.from_bytes(digest[:2], "big") / 65535


def run(
    family: str,
    policy: str,
    target: tuple[int, int],
    exploration: dict[int, tuple[int, int, int]],
    seed: int,
    landscape_seed: int,
) -> dict:
    rng = random.Random(seed)
    evaluated = []
    for x, ys in exploration.items():
        observations = [
            (y, score(family, (x, y), target, landscape_seed)) for y in ys
        ]
        evaluated.extend((x, y) for y in ys)
        unseen = [y for y in range(5) if y not in ys]
        if policy == "e39_promoted_surrogate":
            slope, intercept, _ = fit_linear(observations)
            chosen = max(unseen, key=lambda y: (intercept + slope * y, y))
        else:
            chosen = rng.choice(unseen)
        evaluated.append((x, chosen))
    values = [score(family, point, target, landscape_seed) for point in evaluated]
    return {
        "family": family,
        "policy": policy,
        "target": list(target),
        "candidate_evaluations": len(evaluated),
        "best_score": max(values),
        "target_hit": target in evaluated,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=1000)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("experiments/E40-unseen-families.json"),
    )
    args = parser.parse_args()
    runs = []
    for seed in range(args.seeds):
        rng = random.Random(40000 + seed)
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
                        45000 + seed * 10 + family_index * 2 + policy_index,
                        47000 + seed * 10 + family_index,
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
                "runs": len(cohort),
                "target_hit_rate": sum(item["target_hit"] for item in cohort)
                / len(cohort),
                "mean_best_score": math.fsum(item["best_score"] for item in cohort)
                / len(cohort),
                "candidate_evaluations_per_run": 20,
            }
        deltas = [
            float(s["target_hit"]) - float(r["target_hit"])
            for r, s in zip(
                cohorts["random_exploitation"],
                cohorts["e39_promoted_surrogate"],
            )
        ]
        summaries[family]["paired_promoted_minus_random"] = {
            "target_hit_rate_delta": math.fsum(deltas) / len(deltas),
            "target_hit_rate_delta_95pct_bootstrap_ci": bootstrap_ci(
                deltas, 46000 + family_index
            ),
        }
    report = {
        "schema_version": 1,
        "experiment_id": "E40-unseen-families",
        "claim_boundary": (
            "held-out synthetic family audit of E39's promoted scaffold policy; "
            "no model-weight improvement claim"
        ),
        "source_policy": "E39 promoted R2 threshold 0.0",
        "seeds": args.seeds,
        "families": list(FAMILIES),
        "matched_budget": all(item["candidate_evaluations"] == 20 for item in runs),
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
            f"{family:12} random={item['random_exploitation']['target_hit_rate']:.1%} "
            f"promoted={item['e39_promoted_surrogate']['target_hit_rate']:.1%} "
            f"delta={delta['target_hit_rate_delta']:+.1%}"
        )


if __name__ == "__main__":
    main()
