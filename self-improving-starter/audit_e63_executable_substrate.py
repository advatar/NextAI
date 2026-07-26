"""E63: audit whether the executable task substrate can measure an improvement.

See ``preregister_e63.py`` for the frozen plan; this module reloads it,
recomputes its digest, and refuses to run on drift.

This makes no capability claim under any outcome. It measures properties of the
reward function using **null variants** -- each environment's own starting
solution with a trailing comment appended, so it is semantically identical and
every non-zero reward it earns is measurement artefact by construction.

The most consequential probe is the best-of-k curve. A search loop that proposes
k candidates and keeps the highest scorer is taking a maximum over the reward
distribution. If the null-variant reward has a wide, positively-clamped noise
distribution, that maximum grows with k and the loop books a phantom improvement
for changing nothing at all.
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


def build_environment(task_id: str):
    """Construct an environment with timing enabled where it is optional."""
    if task_id == "optimize_function":
        return REGISTRY[task_id](correctness_only=False)
    return REGISTRY[task_id]()


def null_variant(source: str, index: int) -> str:
    """Semantically identical to ``source``; textually distinct."""
    return f"{source}\n# null variant {index}\n"


def best_of_k(rewards, k, samples, rng):
    """Expected score of keeping the best of k no-op proposals."""
    if not rewards:
        return None
    return statistics.fmean(
        max(rewards[rng.randrange(len(rewards))] for _ in range(k))
        for _ in range(samples)
    )


def audit_task(task_id: str, variants: int, k_values, samples: int) -> dict:
    env = build_environment(task_id)
    starting = env.score(env.starting_solution)

    rewards = []
    raws = []
    correct_count = 0
    for index in range(variants):
        result = env.score(null_variant(env.starting_solution, index))
        rewards.append(result.reward)
        raws.append(result.raw)
        correct_count += int(result.correct)

    row: dict = {
        "task_id": task_id,
        "starting_solution_reward": starting.reward,
        "starting_solution_correct": starting.correct,
        "null_variants": variants,
        "null_variants_correct": correct_count,
        "null_reward_mean": statistics.fmean(rewards),
        "null_reward_sd": statistics.pstdev(rewards),
        "null_reward_min": min(rewards),
        "null_reward_max": max(rewards),
        "null_reward_spread": max(rewards) - min(rewards),
    }

    rng = random.Random(63000 + len(task_id))
    row["best_of_k"] = {
        str(k): best_of_k(rewards, k, samples, rng) for k in k_values
    }

    # Rectification bias, where a raw metric and a fixed reference exist.
    baseline = getattr(env, "_baseline_time", None)
    if baseline and all(value is not None for value in raws):
        unclamped = [(baseline - value) / baseline for value in raws]
        clamped = [max(0.0, min(1.0, value)) for value in unclamped]
        row["reference_baseline_seconds"] = baseline
        row["reference_baseline_source"] = (
            "single measurement taken once at environment construction"
        )
        row["null_raw_seconds_mean"] = statistics.fmean(raws)
        row["null_raw_seconds_sd"] = statistics.pstdev(raws)
        row["null_unclamped_reward_mean"] = statistics.fmean(unclamped)
        row["null_unclamped_reward_sd"] = statistics.pstdev(unclamped)
        row["rectification_bias"] = statistics.fmean(clamped) - statistics.fmean(
            unclamped
        )
        # Is the fixed reference itself representative of the null distribution?
        row["reference_vs_null_median_ratio"] = baseline / statistics.median(raws)
    else:
        row["rectification_bias"] = None

    return row


def judge(row: dict, criteria: dict) -> dict:
    failures = []
    if row["starting_solution_reward"] > criteria["maximum_starting_solution_reward"]:
        failures.append(
            f"starting_solution_reward {row['starting_solution_reward']:.3f} "
            f"exceeds maximum {criteria['maximum_starting_solution_reward']} "
            "(ships already solved; no headroom)"
        )
    if row["null_reward_sd"] > criteria["maximum_null_variant_reward_sd"]:
        failures.append(
            f"null_reward_sd {row['null_reward_sd']:.3f} exceeds maximum "
            f"{criteria['maximum_null_variant_reward_sd']}"
        )
    best5 = row["best_of_k"].get("5")
    if best5 is not None and best5 > criteria["maximum_null_best_of_5_reward"]:
        failures.append(
            f"best_of_5 null reward {best5:.3f} exceeds maximum "
            f"{criteria['maximum_null_best_of_5_reward']} (search can "
            "manufacture this much from no-op proposals)"
        )
    bias = row["rectification_bias"]
    if bias is not None and abs(bias) > criteria["maximum_absolute_rectification_bias"]:
        failures.append(
            f"rectification_bias {bias:+.3f} exceeds maximum magnitude "
            f"{criteria['maximum_absolute_rectification_bias']}"
        )
    return {"admitted": not failures, "failures": failures}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--preregistration",
        type=Path,
        default=Path("experiments/E63-preregistration.json"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("experiments/E63-executable-substrate-audit.json"),
    )
    args = parser.parse_args()

    plan = load_preregistration(args.preregistration)
    instrument = plan["instrument"]
    criteria = plan["admission_criteria"]
    variants = instrument["null_variants_per_task"]
    k_values = instrument["best_of_k_values"]
    samples = instrument["bootstrap_samples"]

    rows = []
    for task_id in plan["tasks"]:
        row = audit_task(task_id, variants, k_values, samples)
        row.update(judge(row, criteria))
        rows.append(row)

    admitted = [row["task_id"] for row in rows if row["admitted"]]
    rejected = [row["task_id"] for row in rows if not row["admitted"]]

    report: dict = {
        "schema_version": 1,
        "experiment_id": "E63-executable-substrate-audit",
        "claim_boundary": plan["claim_boundary"],
        "makes_capability_claim": False,
        "preregistration_digest": plan["preregistration_digest"],
        "follows": plan["follows"],
        "question": plan["question"],
        "reproducibility_note": (
            "This experiment measures wall-clock time, so its numbers are not "
            "bit-reproducible across machines or runs. The report digest attests "
            "to the recorded report, not to a deterministic computation."
        ),
        "admission_criteria": criteria,
        "null_variant_definition": plan["null_variant_definition"],
        "null_variants_per_task": variants,
        "tasks": rows,
        "admitted_tasks": admitted,
        "rejected_tasks": rejected,
    }

    def graded(identifier, supported, evidence):
        return {"id": identifier, "supported": supported, "evidence": evidence}

    by_id = {row["task_id"]: row for row in rows}
    predictions = []

    sum_digits = by_id.get("sum_digits", {})
    predictions.append(
        graded(
            "H1",
            not sum_digits.get("admitted", True)
            and any("already solved" in f for f in sum_digits.get("failures", [])),
            f"sum_digits starting reward="
            f"{sum_digits.get('starting_solution_reward')} "
            f"failures={sum_digits.get('failures')}",
        )
    )

    primes = by_id.get("count_primes", {})
    predictions.append(
        graded(
            "H2",
            primes.get("null_reward_sd", 0.0) > 0.05,
            f"count_primes null_reward_sd={primes.get('null_reward_sd'):.4f}",
        )
    )
    primes_best5 = primes.get("best_of_k", {}).get("5")
    predictions.append(
        graded(
            "H3",
            primes_best5 is not None and primes_best5 >= 0.10,
            f"count_primes best_of_5={primes_best5}",
        )
    )
    primes_bias = primes.get("rectification_bias")
    predictions.append(
        graded(
            "H4",
            primes_bias is not None and primes_bias >= 0.05,
            f"count_primes rectification_bias={primes_bias}",
        )
    )
    predictions.append(
        graded("H5", not admitted, f"admitted tasks: {admitted or 'none'}")
    )
    report["predictions"] = predictions

    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)

    print(f"preregistration {plan['preregistration_digest'][:16]} verified")
    for row in rows:
        print(f"\n=== {row['task_id']} ===")
        print(
            f"  starting solution reward {row['starting_solution_reward']:+.4f} "
            f"(correct={row['starting_solution_correct']})"
        )
        print(
            f"  null variants n={row['null_variants']} "
            f"mean={row['null_reward_mean']:+.4f} sd={row['null_reward_sd']:.4f} "
            f"range=[{row['null_reward_min']:.3f}, {row['null_reward_max']:.3f}]"
        )
        curve = " ".join(
            f"k={k}:{value:.4f}" for k, value in row["best_of_k"].items()
        )
        print(f"  best-of-k phantom gain  {curve}")
        if row["rectification_bias"] is not None:
            print(
                f"  unclamped mean {row['null_unclamped_reward_mean']:+.4f} "
                f"sd {row['null_unclamped_reward_sd']:.4f}"
            )
            print(f"  rectification bias {row['rectification_bias']:+.4f}")
            print(
                f"  fixed reference {row['reference_baseline_seconds'] * 1e3:.2f} ms "
                f"vs null median ratio {row['reference_vs_null_median_ratio']:.3f}"
            )
        verdict = "ADMITTED" if row["admitted"] else "REJECTED"
        print(f"  {verdict}")
        for failure in row["failures"]:
            print(f"    - {failure}")

    print(f"\nadmitted={admitted or 'none'}  rejected={rejected}")
    print("\nPREDICTIONS:")
    for item in predictions:
        mark = "supported" if item["supported"] else "NOT supported"
        print(f"  {item['id']}: {mark} — {item['evidence']}")


if __name__ == "__main__":
    main()
