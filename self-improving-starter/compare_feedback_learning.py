"""E15: test whether public score feedback improves a fixed proposal budget."""

import argparse
import hashlib
import json
import random
from pathlib import Path


def score(x):
    # deceptive: x=0 is a strong local attractor; x=8 is global optimum
    return 0.82 if x == 0 else (1.0 if x == 8 else 0.15 + 0.07 * x)


def run(policy, seed, budget):
    rng = random.Random(seed)
    x = 0
    best = score(x)
    evaluations = 1
    for _ in range(budget - 1):
        proposal = (
            rng.randrange(9)
            if policy == "blind"
            else min(8, max(0, x + (1 if rng.random() < 0.8 else rng.choice((-2, 2)))))
        )
        value = score(proposal)
        evaluations += 1
        if policy == "blind" or value >= best:
            x, best = proposal, value
    return {
        "policy": policy,
        "seed": seed,
        "best": best,
        "hit": best == 1.0,
        "evaluations": evaluations,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seeds", type=int, default=1000)
    p.add_argument("--budget", type=int, default=24)
    p.add_argument(
        "--out", type=Path, default=Path("experiments/E15-feedback-learning.json")
    )
    a = p.parse_args()
    runs = [
        run(policy, seed, a.budget)
        for seed in range(a.seeds)
        for policy in ("blind", "feedback_directed")
    ]
    summaries = {}
    for policy in ("blind", "feedback_directed"):
        cohort = [r for r in runs if r["policy"] == policy]
        summaries[policy] = {
            "mean_best": sum(r["best"] for r in cohort) / len(cohort),
            "global_hit_rate": sum(r["hit"] for r in cohort) / len(cohort),
        }
    report = {
        "schema_version": 1,
        "experiment_id": "E15-feedback-learning",
        "claim_boundary": "synthetic benchmark evidence for score feedback, not model learning",
        "budget": a.budget,
        "seeds": a.seeds,
        "summaries": summaries,
        "runs": runs,
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
