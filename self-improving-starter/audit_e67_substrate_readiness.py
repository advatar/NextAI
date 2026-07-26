"""E67: is the executable substrate ready for a governed search run?

See ``preregister_e67.py`` for the frozen plan; this module reloads it,
recomputes its digest, and refuses to run on drift.  Readiness licenses a search
run — it is not evidence about one, and no capability claim is made here.

Every task is measured under paired scoring with the corrected harness.  E66's
figures are not carried forward: they were taken with ``PAIRED_ROUNDS=7`` and no
warm-up, and that harness had an order bias.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
from pathlib import Path

from compare_selection import _atomic_json
from compare_e60_corrected_admission import load_preregistration
from compare_e66_paired_timing import (
    COUNT_PRIMES_SLOWER,
    OPTIMIZE_REFERENCE,
    OPTIMIZE_SLOWER,
    POWER_MOD_SLOWER,
)
from environments import REGISTRY
from recursive_lab.paired_timing import (
    calibrate_reference_ratio,
    paired_measure,
    paired_reward,
)
from recursive_lab.reward_probes import best_of_k, semantic_noop_variant, spread

COUNT_DIVISORS_SLOWER = (
    "def solve(n):\n"
    "    if n <= 0:\n"
    "        return 0\n"
    "    total = 0\n"
    "    for d in range(1, n + 1):\n"
    "        if n % d == 0:\n"
    "            total += 1\n"
    "    second = 0\n"
    "    for d in range(1, n + 1):\n"
    "        if n % d == 0:\n"
    "            second += 1\n"
    "    return second\n"
)
SLOWER_PROBES = {
    "optimize_function": OPTIMIZE_SLOWER,
    "count_primes_v2": COUNT_PRIMES_SLOWER,
    "power_mod": POWER_MOD_SLOWER,
    "count_divisors": COUNT_DIVISORS_SLOWER,
}


def scorer_for(task_id: str):
    """Return (score_fn, starting_solution, reference_solution, headroom)."""
    if task_id == "optimize_function":
        env = REGISTRY[task_id](correctness_only=False)
        starting = env.starting_solution
        reference = OPTIMIZE_REFERENCE
        timing_argument = 100_000
        ratio = calibrate_reference_ratio(starting, reference, timing_argument)

        def score(source: str) -> float:
            measurement = paired_measure(starting, source, timing_argument)
            return paired_reward(measurement.ratio, ratio)

        return score, starting, reference, 1.0 / ratio

    env = REGISTRY[task_id]()
    if env.scoring != "paired":
        raise RuntimeError(f"{task_id}: expected paired scoring by default")
    return (
        lambda source: env.score(source).reward,
        env.starting_solution,
        env.reference_solution,
        env.baseline_report()["speedup_factor"],
    )


def audit_task(task_id: str, plan: dict) -> dict:
    instrument = plan["instrument"]
    score, starting, reference, headroom = scorer_for(task_id)

    anchor_scores = [
        score(starting) for _ in range(instrument["anchor_self_probes_per_task"])
    ]
    nulls = [
        score(semantic_noop_variant(starting, index))
        for index in range(instrument["null_variants_per_task"])
    ]
    references = [
        score(reference) for _ in range(instrument["reference_probes_per_task"])
    ]
    slower = score(SLOWER_PROBES[task_id])

    rng = random.Random(67000 + len(task_id))
    mean = statistics.fmean(nulls)
    sd = spread(nulls)
    row = {
        "task_id": task_id,
        "headroom_factor": headroom,
        "anchor_self_scores": anchor_scores,
        "anchor_self_score": statistics.fmean(anchor_scores),
        "null_reward_mean": mean,
        "null_reward_sd": sd,
        "null_reward_min": min(nulls),
        "null_reward_max": max(nulls),
        "best_of_k": {
            str(k): best_of_k(nulls, k, instrument["bootstrap_samples"], rng)
            for k in instrument["best_of_k_values"]
        },
        "reference_reward_mean": statistics.fmean(references),
        "slower_probe_reward": slower,
        "signal_to_noise": None
        if sd <= 0.0
        else (statistics.fmean(references) - mean) / sd,
    }
    row["best_of_5"] = row["best_of_k"]["5"]
    return row


def judge(row: dict, criteria: dict) -> dict:
    failures = []
    if abs(row["anchor_self_score"]) > criteria["maximum_absolute_anchor_self_score"]:
        failures.append(
            f"anchor_self_score {row['anchor_self_score']:+.4f} exceeds maximum "
            "magnitude — the starting solution must score 0.0 against itself"
        )
    if abs(row["null_reward_mean"]) > criteria["maximum_absolute_null_reward_mean"]:
        failures.append(
            f"null_reward_mean {row['null_reward_mean']:+.4f} exceeds maximum "
            f"magnitude {criteria['maximum_absolute_null_reward_mean']}"
        )
    if row["null_reward_sd"] > criteria["maximum_null_variant_reward_sd"]:
        failures.append(
            f"null_reward_sd {row['null_reward_sd']:.4f} exceeds maximum "
            f"{criteria['maximum_null_variant_reward_sd']}"
        )
    if row["best_of_5"] > criteria["maximum_null_best_of_5_reward"]:
        failures.append(
            f"best_of_5 {row['best_of_5']:+.4f} exceeds maximum "
            f"{criteria['maximum_null_best_of_5_reward']}"
        )
    if row["reference_reward_mean"] < criteria["minimum_reference_reward"]:
        failures.append(
            f"reference_reward_mean {row['reference_reward_mean']:.4f} is below "
            f"minimum {criteria['minimum_reference_reward']}"
        )
    if row["slower_probe_reward"] > criteria["monotonicity_threshold"]:
        failures.append(
            f"slower probe scored {row['slower_probe_reward']:+.4f}; the reward "
            "does not fall when the program is genuinely slower"
        )
    ratio = row["signal_to_noise"]
    if ratio is None:
        failures.append(
            "signal_to_noise is undefined (null spread is zero); evidence of "
            "censoring, not precision"
        )
    elif ratio < criteria["minimum_signal_to_noise"]:
        failures.append(
            f"signal_to_noise {ratio:.2f} is below minimum "
            f"{criteria['minimum_signal_to_noise']}"
        )
    return {"admitted": not failures, "failures": failures}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--preregistration",
        type=Path,
        default=Path("experiments/E67-preregistration.json"),
    )
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E67-substrate-readiness.json")
    )
    args = parser.parse_args()

    plan = load_preregistration(args.preregistration)
    criteria = plan["admission_criteria"]
    rows = []
    for task_id in plan["tasks"]:
        row = audit_task(task_id, plan)
        row.update(judge(row, criteria))
        rows.append(row)

    admitted = [row["task_id"] for row in rows if row["admitted"]]
    ready = len(admitted) >= 3

    report = {
        "schema_version": 1,
        "experiment_id": "E67-substrate-readiness",
        "claim_boundary": plan["claim_boundary"],
        "makes_capability_claim": False,
        "preregistration_digest": plan["preregistration_digest"],
        "follows": plan["follows"],
        "question": plan["question"],
        "reproducibility_note": (
            "Measures wall-clock time; not bit-reproducible. The digest attests "
            "to the recorded report."
        ),
        "admission_criteria": criteria,
        "tasks": rows,
        "admitted_tasks": admitted,
        "rejected_tasks": [r["task_id"] for r in rows if not r["admitted"]],
        "substrate_ready_for_search": ready,
    }

    def graded(identifier, supported, evidence):
        return {"id": identifier, "supported": supported, "evidence": evidence}

    by_id = {row["task_id"]: row for row in rows}
    admitted_rows = [r for r in rows if r["admitted"]]
    predictions = [
        graded(
            "H1",
            by_id["count_divisors"]["admitted"],
            f"count_divisors admitted={by_id['count_divisors']['admitted']} "
            f"failures={by_id['count_divisors']['failures']}",
        ),
        graded(
            "H2",
            all(
                abs(r["anchor_self_score"])
                <= criteria["maximum_absolute_anchor_self_score"]
                for r in rows
            ),
            "anchor self-scores: "
            + ", ".join(f"{r['task_id']}={r['anchor_self_score']:+.4f}" for r in rows),
        ),
        graded(
            "H3",
            not by_id["count_primes_v2"]["admitted"],
            f"count_primes_v2 admitted={by_id['count_primes_v2']['admitted']} "
            f"(headroom {by_id['count_primes_v2']['headroom_factor']:.0f}x)",
        ),
        graded("H4", len(admitted) >= 3, f"admitted: {admitted}"),
        graded(
            "H5",
            all(0.0 < r["best_of_5"] < 0.05 for r in admitted_rows),
            "admitted best-of-5: "
            + ", ".join(f"{r['task_id']}={r['best_of_5']:+.4f}" for r in admitted_rows),
        ),
    ]
    report["predictions"] = predictions

    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)

    print(f"preregistration {plan['preregistration_digest'][:16]} verified")
    for row in rows:
        print(f"\n=== {row['task_id']} ===  headroom {row['headroom_factor']:.0f}x")
        print(
            f"  anchor self={row['anchor_self_score']:+.4f}  "
            f"null mean={row['null_reward_mean']:+.4f} sd={row['null_reward_sd']:.4f}  "
            f"best5={row['best_of_5']:+.4f}"
        )
        ratio = row["signal_to_noise"]
        print(
            f"  reference={row['reference_reward_mean']:+.4f}  "
            f"slower={row['slower_probe_reward']:+.4f}  "
            f"s/n={'n/a' if ratio is None else format(ratio, '.1f')}"
        )
        print("  " + ("ADMITTED" if row["admitted"] else "REJECTED"))
        for failure in row["failures"]:
            print(f"    - {failure}")

    print(f"\nadmitted={admitted}")
    print(f"substrate ready for a governed search run: {ready}")
    print("\nPREDICTIONS:")
    for item in predictions:
        mark = "supported" if item["supported"] else "NOT supported"
        print(f"  {item['id']}: {mark} — {item['evidence']}")


if __name__ == "__main__":
    main()
