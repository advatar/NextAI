"""E64: re-audit the executable substrate after the E63 repairs.

See ``preregister_e64.py`` for the frozen plan; this module reloads it,
recomputes its digest, and refuses to run on drift.  It makes no capability
claim under any outcome.

Two probes per task.  **Null variants** are the task's own starting solution
with a comment appended -- semantically identical, so any reward is artefact.
**Reference probes** are a known-good strong solution, which must score well and
must be distinguishable from the nulls.  E63's criteria measured only the first
kind, so a constant reward function would have passed them; the signal-to-noise
criterion here closes that.
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

#: Strong solutions for tasks that do not expose a ``reference_solution``.
#: Recorded here rather than in the environment so the v1 tasks stay untouched.
EXTERNAL_REFERENCES = {
    "optimize_function": (
        "def solve(n):\n"
        "    if n < 2:\n"
        "        return 0\n"
        "    m = n - 1\n"
        "    return m * (m + 1) * (2 * m + 1) // 6\n"
    ),
    "count_primes": (
        "def solve(n):\n"
        "    if n <= 2:\n"
        "        return 0\n"
        "    total = 1\n"
        "    for value in range(3, n, 2):\n"
        "        prime = 1\n"
        "        divisor = 3\n"
        "        while divisor * divisor <= value:\n"
        "            if value % divisor == 0:\n"
        "                prime = 0\n"
        "                break\n"
        "            divisor += 2\n"
        "        total += prime\n"
        "    return total\n"
    ),
}


def build_environment(task_id: str):
    if task_id == "optimize_function":
        return REGISTRY[task_id](correctness_only=False)
    return REGISTRY[task_id]()


def null_variant(source: str, index: int) -> str:
    return f"{source}\n# null variant {index}\n"


def reference_source(env, task_id: str) -> str | None:
    candidate = getattr(env, "reference_solution", None)
    if isinstance(candidate, str) and candidate.strip():
        return candidate
    return EXTERNAL_REFERENCES.get(task_id)


def best_of_k(rewards, k, samples, rng):
    if not rewards:
        return None
    return statistics.fmean(
        max(rewards[rng.randrange(len(rewards))] for _ in range(k))
        for _ in range(samples)
    )


def audit_task(task_id: str, plan: dict) -> dict:
    instrument = plan["instrument"]
    env = build_environment(task_id)
    starting = env.score(env.starting_solution)

    null_rewards = []
    for index in range(instrument["null_variants_per_task"]):
        null_rewards.append(
            env.score(null_variant(env.starting_solution, index)).reward
        )

    row: dict = {
        "task_id": task_id,
        "role": plan["task_roles"][task_id],
        "starting_solution_reward": starting.reward,
        "null_variants": len(null_rewards),
        "null_reward_mean": statistics.fmean(null_rewards),
        "null_reward_sd": statistics.pstdev(null_rewards),
        "null_reward_min": min(null_rewards),
        "null_reward_max": max(null_rewards),
    }

    rng = random.Random(64000 + len(task_id))
    row["best_of_k"] = {
        str(k): best_of_k(null_rewards, k, instrument["bootstrap_samples"], rng)
        for k in instrument["best_of_k_values"]
    }

    if hasattr(env, "baseline_report"):
        row["anchors"] = env.baseline_report()

    source = reference_source(env, task_id)
    if source is None:
        row["reference_reward_mean"] = None
        row["signal_to_noise"] = None
        row["reference_probes"] = 0
    else:
        rewards = []
        correct = 0
        for _ in range(instrument["reference_probes_per_task"]):
            result = env.score(source)
            rewards.append(result.reward)
            correct += int(result.correct)
        row["reference_probes"] = len(rewards)
        row["reference_probes_correct"] = correct
        row["reference_reward_mean"] = statistics.fmean(rewards)
        row["reference_reward_sd"] = statistics.pstdev(rewards)
        spread = row["null_reward_sd"]
        row["signal_to_noise"] = (
            None
            if spread <= 0.0
            else (row["reference_reward_mean"] - row["null_reward_mean"]) / spread
        )
        if spread <= 0.0:
            # A perfectly stable null distribution means noise is below
            # measurement resolution; separation alone then decides.
            row["signal_to_noise_note"] = (
                "null sd is zero; signal-to-noise is undefined and the "
                "reference-reward criterion decides"
            )
    return row


def judge(row: dict, criteria: dict) -> dict:
    failures = []
    if row["starting_solution_reward"] > criteria["maximum_starting_solution_reward"]:
        failures.append(
            f"starting_solution_reward {row['starting_solution_reward']:.3f} "
            f"exceeds maximum {criteria['maximum_starting_solution_reward']} "
            "(ships already solved)"
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
            "manufacture this from no-op proposals)"
        )
    if abs(row["null_reward_mean"]) > criteria["maximum_absolute_null_reward_mean"]:
        failures.append(
            f"null_reward_mean {row['null_reward_mean']:+.3f} exceeds maximum "
            f"magnitude {criteria['maximum_absolute_null_reward_mean']} "
            "(a no-op change should score about zero)"
        )
    reference = row["reference_reward_mean"]
    if reference is None:
        failures.append("no reference solution available; signal is unmeasured")
    else:
        if reference < criteria["minimum_reference_reward"]:
            failures.append(
                f"reference_reward_mean {reference:.3f} is below minimum "
                f"{criteria['minimum_reference_reward']}"
            )
        ratio = row["signal_to_noise"]
        if ratio is not None and ratio < criteria["minimum_signal_to_noise"]:
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
        default=Path("experiments/E64-preregistration.json"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("experiments/E64-repaired-substrate-audit.json"),
    )
    args = parser.parse_args()

    plan = load_preregistration(args.preregistration)
    criteria = plan["admission_criteria"]

    rows = []
    for task_id in plan["tasks"]:
        row = audit_task(task_id, plan)
        row.update(judge(row, criteria))
        rows.append(row)

    by_id = {row["task_id"]: row for row in rows}
    admitted = [row["task_id"] for row in rows if row["admitted"]]
    rejected = [row["task_id"] for row in rows if not row["admitted"]]

    report: dict = {
        "schema_version": 1,
        "experiment_id": "E64-repaired-substrate-audit",
        "claim_boundary": plan["claim_boundary"],
        "makes_capability_claim": False,
        "preregistration_digest": plan["preregistration_digest"],
        "follows": plan["follows"],
        "question": plan["question"],
        "reproducibility_note": (
            "Measures wall-clock time; numbers are not bit-reproducible across "
            "machines or runs. The digest attests to the recorded report."
        ),
        "admission_criteria": criteria,
        "tasks": rows,
        "admitted_tasks": admitted,
        "rejected_tasks": rejected,
    }

    def graded(identifier, supported, evidence):
        return {"id": identifier, "supported": supported, "evidence": evidence}

    v1 = by_id.get("count_primes", {})
    v2 = by_id.get("count_primes_v2", {})
    predictions = []

    v1_best5 = v1.get("best_of_k", {}).get("5")
    v2_best5 = v2.get("best_of_k", {}).get("5")
    predictions.append(
        graded(
            "H1",
            v1_best5 is not None and v2_best5 is not None and v2_best5 < v1_best5,
            f"count_primes best_of_5={v1_best5} vs v2 best_of_5={v2_best5}",
        )
    )
    predictions.append(
        graded(
            "H2",
            abs(v2.get("null_reward_mean", 1.0)) < abs(v1.get("null_reward_mean", 0.0)),
            f"count_primes null mean={v1.get('null_reward_mean'):+.4f} vs "
            f"v2={v2.get('null_reward_mean'):+.4f}",
        )
    )
    predictions.append(
        graded(
            "H3",
            by_id.get("power_mod", {}).get("admitted", False),
            f"power_mod admitted={by_id.get('power_mod', {}).get('admitted')} "
            f"failures={by_id.get('power_mod', {}).get('failures')}",
        )
    )
    predictions.append(
        graded(
            "H4",
            not v2.get("admitted", True)
            and any("null_reward_sd" in f for f in v2.get("failures", [])),
            f"count_primes_v2 admitted={v2.get('admitted')} "
            f"failures={v2.get('failures')}",
        )
    )
    ratios = {
        task: by_id[task].get("signal_to_noise")
        for task in admitted
    }
    # H5 exists to detect the criterion being *silently skipped*, so an
    # undefined ratio must count as a failure. The originally recorded E64 run
    # used `value is None or value >= threshold`, which treated undefined as
    # passing and therefore performed the very skip H5 was written to catch:
    # both admitted tasks had a null sd of exactly zero -- from censoring, not
    # precision -- so neither had a defined ratio. The recorded report's
    # "H5: supported" must be read as NOT supported; this is the corrected rule.
    predictions.append(
        graded(
            "H5",
            bool(ratios)
            and all(
                value is not None and value >= criteria["minimum_signal_to_noise"]
                for value in ratios.values()
            ),
            f"admitted signal_to_noise: "
            f"{ {k: (round(v, 2) if v is not None else None) for k, v in ratios.items()} }",
        )
    )
    report["predictions"] = predictions

    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)

    print(f"preregistration {plan['preregistration_digest'][:16]} verified")
    for row in rows:
        print(f"\n=== {row['task_id']} ===  ({row['role']})")
        if "anchors" in row:
            anchors = row["anchors"]
            print(
                f"  anchors: start {anchors['starting_seconds'] * 1e6:.1f} us -> "
                f"reference {anchors['reference_seconds'] * 1e6:.1f} us "
                f"({anchors['speedup_factor']:.1f}x headroom)"
            )
        print(f"  starting solution reward {row['starting_solution_reward']:+.4f}")
        print(
            f"  null n={row['null_variants']} mean={row['null_reward_mean']:+.4f} "
            f"sd={row['null_reward_sd']:.4f} "
            f"range=[{row['null_reward_min']:+.3f}, {row['null_reward_max']:+.3f}]"
        )
        curve = " ".join(f"k={k}:{v:.4f}" for k, v in row["best_of_k"].items())
        print(f"  best-of-k phantom gain  {curve}")
        if row["reference_reward_mean"] is not None:
            ratio = row["signal_to_noise"]
            shown = "undefined" if ratio is None else f"{ratio:.1f}"
            print(
                f"  reference n={row['reference_probes']} "
                f"mean={row['reference_reward_mean']:+.4f}  signal/noise={shown}"
            )
        print("  " + ("ADMITTED" if row["admitted"] else "REJECTED"))
        for failure in row["failures"]:
            print(f"    - {failure}")

    print(f"\nadmitted={admitted or 'none'}  rejected={rejected or 'none'}")
    print("\nPREDICTIONS:")
    for item in predictions:
        mark = "supported" if item["supported"] else "NOT supported"
        print(f"  {item['id']}: {mark} — {item['evidence']}")


if __name__ == "__main__":
    main()
