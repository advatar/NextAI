"""Paired bootstrap evidence summary for a deceptive-search cohort."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path

from compare_selection import _atomic_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument(
        "--out", type=Path, default=Path("runs/E12-deceptive-evidence.json")
    )
    parser.add_argument("--bootstrap", type=int, default=20000)
    args = parser.parse_args()
    source = json.loads(args.report.read_text())
    by_policy = {}
    for run in source["runs"]:
        by_policy.setdefault(run["policy"], {})[run["seed"]] = run
    seeds = sorted(set.intersection(*(set(cohort) for cohort in by_policy.values())))
    if len(seeds) < 2 or args.bootstrap < 100:
        parser.error("need at least two paired seeds and 100 bootstrap draws")
    rng = random.Random(1207)
    summaries = {}
    baseline = by_policy["greedy"]
    for policy, cohort in by_policy.items():
        values = [cohort[s]["best_objective"] for s in seeds]
        summaries[policy] = {
            "runs": len(values),
            "mean_best_objective": math.fsum(values) / len(values),
            "target_hit_rate": sum(v >= 1 for v in values) / len(values),
        }
    deltas = {}
    for policy, cohort in by_policy.items():
        if policy == "greedy":
            continue
        paired = [
            (
                cohort[s]["best_objective"] - baseline[s]["best_objective"],
                (cohort[s]["best_objective"] >= 1)
                - (baseline[s]["best_objective"] >= 1),
            )
            for s in seeds
        ]
        means = []
        hit_deltas = []
        for _ in range(args.bootstrap):
            sample = [paired[rng.randrange(len(paired))] for _ in paired]
            means.append(math.fsum(x[0] for x in sample) / len(sample))
            hit_deltas.append(math.fsum(x[1] for x in sample) / len(sample))
        means.sort()
        hit_deltas.sort()
        lo = int(0.025 * len(means))
        hi = int(0.975 * len(means)) - 1
        deltas[policy] = {
            "mean_delta_vs_greedy": math.fsum(x[0] for x in paired) / len(paired),
            "bootstrap_95ci": [means[lo], means[hi]],
            "target_hit_rate_delta_vs_greedy": math.fsum(x[1] for x in paired)
            / len(paired),
            "target_hit_rate_bootstrap_95ci": [hit_deltas[lo], hit_deltas[hi]],
        }
    report = {
        "schema_version": 1,
        "experiment_id": "E12-deceptive-evidence",
        "claim_boundary": "paired bootstrap evidence for one synthetic deceptive landscape; no general capability claim",
        "source_experiment": source["experiment_id"],
        "source_report_digest": source["report_digest"],
        "paired_seeds": seeds,
        "bootstrap_draws": args.bootstrap,
        "summaries": summaries,
        "deltas_vs_greedy": deltas,
    }
    canonical = json.dumps(
        report, allow_nan=False, sort_keys=True, separators=(",", ":")
    )
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)
    for policy, delta in deltas.items():
        print(
            f"{policy}: delta={delta['mean_delta_vs_greedy']:.3f} CI=[{delta['bootstrap_95ci'][0]:.3f}, {delta['bootstrap_95ci'][1]:.3f}]"
        )


if __name__ == "__main__":
    main()
