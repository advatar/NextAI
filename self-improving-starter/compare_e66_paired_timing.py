"""E66: unpaired versus paired measurement, both arms in one run.

See ``preregister_e66.py`` for the frozen plan; this module reloads it,
recomputes its digest, and refuses to run on drift.  No capability claim is made
under any outcome.

Both protocols are measured on the same tasks in the same run.  Comparing across
experiments would inherit exactly the drift this experiment is about, which would
be self-defeating.
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
from environments import REGISTRY
from recursive_lab.paired_timing import (
    calibrate_reference_ratio,
    paired_measure,
    paired_reward,
)
from recursive_lab.reward_probes import best_of_k, semantic_noop_variant, spread

OPTIMIZE_REFERENCE = (
    "def solve(n):\n"
    "    if n < 2:\n"
    "        return 0\n"
    "    m = n - 1\n"
    "    return m * (m + 1) * (2 * m + 1) // 6\n"
)
OPTIMIZE_SLOWER = (
    "def solve(n):\n"
    "    total = 0\n"
    "    for i in range(n):\n"
    "        total += i * i\n"
    "    second = 0\n"
    "    for i in range(n):\n"
    "        second += i * i\n"
    "    return second\n"
)
COUNT_PRIMES_SLOWER = (
    "def solve(n):\n"
    "    total = 0\n"
    "    for value in range(n):\n"
    "        if value > 1:\n"
    "            prime = 1\n"
    "            for divisor in range(2, value):\n"
    "                if value % divisor == 0:\n"
    "                    prime = 0\n"
    "                    break\n"
    "            total += prime\n"
    "    second = 0\n"
    "    for value in range(n):\n"
    "        if value > 1:\n"
    "            prime = 1\n"
    "            for divisor in range(2, value):\n"
    "                if value % divisor == 0:\n"
    "                    prime = 0\n"
    "                    break\n"
    "            second += prime\n"
    "    return second\n"
)
POWER_MOD_SLOWER = (
    "def solve(n):\n"
    "    result = 1\n"
    "    for _step in range(n):\n"
    "        result = result * 7 % 1000000007\n"
    "    second = 1\n"
    "    for _step in range(n):\n"
    "        second = second * 7 % 1000000007\n"
    "    return second\n"
)


def task_specification(task_id: str) -> dict:
    """Anchor, held-out reference, slower probe and timing argument per task."""
    if task_id == "optimize_function":
        env = REGISTRY[task_id](correctness_only=False)
        return {
            "env": env,
            "starting": env.starting_solution,
            "reference": OPTIMIZE_REFERENCE,
            "slower": OPTIMIZE_SLOWER,
            "timing_argument": 100_000,
        }
    # Pinned explicitly. When this experiment ran, "anchored" was the only mode
    # a TimedTaskEnvironment had; E66's own result made "paired" the default.
    # Naming it here keeps the unpaired arm reproducible instead of silently
    # becoming a paired-versus-paired comparison.
    env = REGISTRY[task_id](scoring="anchored")
    slower = COUNT_PRIMES_SLOWER if task_id.startswith("count_primes") else POWER_MOD_SLOWER
    return {
        "env": env,
        "starting": env.starting_solution,
        "reference": env.reference_solution,
        "slower": slower,
        "timing_argument": env.timing_argument,
    }


def summarise(rewards, anchor_self, reference_mean, slower_reward, rng, plan):
    instrument = plan["instrument"]
    mean = statistics.fmean(rewards)
    sd = spread(rewards)
    row = {
        "anchor_self_score": anchor_self,
        "null_reward_mean": mean,
        "null_reward_sd": sd,
        "null_reward_min": min(rewards),
        "null_reward_max": max(rewards),
        "best_of_k": {
            str(k): best_of_k(rewards, k, instrument["bootstrap_samples"], rng)
            for k in instrument["best_of_k_values"]
        },
        "reference_reward_mean": reference_mean,
        "slower_probe_reward": slower_reward,
        "signal_to_noise": None if sd <= 0.0 else (reference_mean - mean) / sd,
    }
    row["best_of_5"] = row["best_of_k"]["5"]
    return row


def judge(row: dict, criteria: dict) -> dict:
    failures = []
    if abs(row["anchor_self_score"]) > criteria["maximum_absolute_anchor_self_score"]:
        failures.append(
            f"anchor_self_score {row['anchor_self_score']:+.4f} exceeds maximum "
            f"magnitude {criteria['maximum_absolute_anchor_self_score']} — the "
            "starting solution must score 0.0 against itself by definition"
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
            f"slower probe scored {row['slower_probe_reward']:+.4f}; a reward "
            "that does not fall when the program is genuinely slower is "
            "censored or insensitive"
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


def audit_task(task_id: str, plan: dict) -> dict:
    instrument = plan["instrument"]
    criteria = plan["admission_criteria"]
    spec = task_specification(task_id)
    env, starting = spec["env"], spec["starting"]
    variants = [
        semantic_noop_variant(starting, index)
        for index in range(instrument["null_variants_per_task"])
    ]
    rng = random.Random(66000 + len(task_id))

    # -- unpaired arm: the environment's own scoring
    unpaired_rewards = [env.score(variant).reward for variant in variants]
    unpaired = summarise(
        unpaired_rewards,
        env.score(starting).reward,
        statistics.fmean(
            env.score(spec["reference"]).reward
            for _ in range(instrument["reference_probes_per_task"])
        ),
        env.score(spec["slower"]).reward,
        rng,
        plan,
    )

    # -- paired arm: anchor interleaved with candidate, reward from the ratio
    reference_ratio = calibrate_reference_ratio(
        starting, spec["reference"], spec["timing_argument"]
    )
    def paired(candidate: str) -> float:
        measurement = paired_measure(starting, candidate, spec["timing_argument"])
        return paired_reward(measurement.ratio, reference_ratio)

    paired_rewards = [paired(variant) for variant in variants]
    paired_row = summarise(
        paired_rewards,
        paired(starting),
        statistics.fmean(
            paired(spec["reference"])
            for _ in range(instrument["reference_probes_per_task"])
        ),
        paired(spec["slower"]),
        rng,
        plan,
    )
    paired_row["reference_ratio"] = reference_ratio

    unpaired.update(judge(unpaired, criteria))
    paired_row.update(judge(paired_row, criteria))
    return {
        "task_id": task_id,
        "timing_argument": spec["timing_argument"],
        "unpaired": unpaired,
        "paired": paired_row,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--preregistration",
        type=Path,
        default=Path("experiments/E66-preregistration.json"),
    )
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E66-paired-timing.json")
    )
    args = parser.parse_args()

    plan = load_preregistration(args.preregistration)
    rows = [audit_task(task_id, plan) for task_id in plan["tasks"]]

    paired_admitted = [r["task_id"] for r in rows if r["paired"]["admitted"]]
    unpaired_admitted = [r["task_id"] for r in rows if r["unpaired"]["admitted"]]

    report = {
        "schema_version": 1,
        "experiment_id": "E66-paired-timing",
        "claim_boundary": plan["claim_boundary"],
        "makes_capability_claim": False,
        "preregistration_digest": plan["preregistration_digest"],
        "follows": plan["follows"],
        "question": plan["question"],
        "reproducibility_note": (
            "Measures wall-clock time; not bit-reproducible. The digest attests "
            "to the recorded report."
        ),
        "admission_criteria": plan["admission_criteria"],
        "tasks": rows,
        "paired_admitted_tasks": paired_admitted,
        "unpaired_admitted_tasks": unpaired_admitted,
    }

    def graded(identifier, supported, evidence):
        return {"id": identifier, "supported": supported, "evidence": evidence}

    criteria = plan["admission_criteria"]
    predictions = [
        graded(
            "H1",
            all(
                abs(r["paired"]["anchor_self_score"])
                <= criteria["maximum_absolute_anchor_self_score"]
                for r in rows
            ),
            "paired anchor self-scores: "
            + ", ".join(
                f"{r['task_id']}={r['paired']['anchor_self_score']:+.4f}" for r in rows
            ),
        ),
        graded(
            "H2",
            all(
                r["paired"]["null_reward_sd"] < r["unpaired"]["null_reward_sd"]
                for r in rows
            ),
            "; ".join(
                f"{r['task_id']} unpaired sd={r['unpaired']['null_reward_sd']:.4f} "
                f"-> paired {r['paired']['null_reward_sd']:.4f}"
                for r in rows
            ),
        ),
        graded(
            "H3",
            all(
                abs(r["paired"]["null_reward_mean"])
                <= criteria["maximum_absolute_null_reward_mean"]
                for r in rows
            ),
            "paired null means: "
            + ", ".join(
                f"{r['task_id']}={r['paired']['null_reward_mean']:+.4f}" for r in rows
            ),
        ),
        graded(
            "H4",
            bool(paired_admitted),
            f"paired admitted: {paired_admitted or 'none'}",
        ),
        graded(
            "H5",
            not unpaired_admitted,
            f"unpaired admitted: {unpaired_admitted or 'none'}",
        ),
    ]
    report["predictions"] = predictions

    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)

    print(f"preregistration {plan['preregistration_digest'][:16]} verified")
    for row in rows:
        print(f"\n=== {row['task_id']} ===")
        for arm in ("unpaired", "paired"):
            data = row[arm]
            print(
                f"  {arm:9} anchor={data['anchor_self_score']:+.4f} "
                f"null mean={data['null_reward_mean']:+.4f} "
                f"sd={data['null_reward_sd']:.4f} "
                f"best5={data['best_of_5']:+.4f} "
                f"ref={data['reference_reward_mean']:+.4f} "
                f"slower={data['slower_probe_reward']:+.4f} "
                f"s/n={'n/a' if data['signal_to_noise'] is None else format(data['signal_to_noise'], '.1f')}"
            )
            print(f"            {'ADMITTED' if data['admitted'] else 'REJECTED'}")
            for failure in data["failures"]:
                print(f"              - {failure}")
    print(f"\npaired admitted   = {paired_admitted or 'none'}")
    print(f"unpaired admitted = {unpaired_admitted or 'none'}")
    print("\nPREDICTIONS:")
    for item in predictions:
        mark = "supported" if item["supported"] else "NOT supported"
        print(f"  {item['id']}: {mark} — {item['evidence']}")


if __name__ == "__main__":
    main()
