"""E68: replicate the admission audit K times and classify by consistency.

See ``preregister_e68.py`` for the frozen plan; this module reloads it,
recomputes its digest, and refuses to run on drift.  No capability claim is made
under any outcome.

A task is **solid** only if it is admitted in every round.  A verdict that
changes between rounds is reported as **marginal** and does not count toward
readiness -- it is not a half-admitted task, it is a task whose verdict is not
yet a measurement.
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
from audit_e67_substrate_readiness import COUNT_DIVISORS_SLOWER, judge
from environments import REGISTRY
from recursive_lab.paired_timing import (
    calibrate_reference_ratio,
    paired_measure,
    paired_reward,
)
from recursive_lab.reward_probes import best_of_k, semantic_noop_variant, spread

GCD_SLOWER = (
    "def solve(n):\n"
    "    if n <= 0:\n"
    "        return 0\n"
    "    best = 1\n"
    "    d = 1\n"
    "    while d <= n:\n"
    "        if n % d == 0 and 963761198400 % d == 0:\n"
    "            best = d\n"
    "        d += 1\n"
    "    second = 1\n"
    "    d = 1\n"
    "    while d <= n:\n"
    "        if n % d == 0 and 963761198400 % d == 0:\n"
    "            second = d\n"
    "        d += 1\n"
    "    return second\n"
)
SLOWER_PROBES = {
    "optimize_function": OPTIMIZE_SLOWER,
    "count_primes_v2": COUNT_PRIMES_SLOWER,
    "power_mod": POWER_MOD_SLOWER,
    "count_divisors": COUNT_DIVISORS_SLOWER,
    "gcd_fixed": GCD_SLOWER,
}


def scorer_for(task_id: str):
    """Return (score_fn, starting, reference, headroom).

    ``optimize_function`` is not a TimedTaskEnvironment, so it uses the paired
    harness directly.  E67 did the same but scored timing without checking the
    candidate was correct, which would credit a fast wrong program.  The
    environment's own correctness gate is applied here first.
    """
    if task_id == "optimize_function":
        env = REGISTRY[task_id](correctness_only=False)
        starting = env.starting_solution
        reference = OPTIMIZE_REFERENCE
        timing_argument = 100_000
        ratio = calibrate_reference_ratio(starting, reference, timing_argument)

        def score(source: str) -> float:
            checked = env.score_correctness(source)
            if not checked.correct:
                return -1.0
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


def measure_round(task_id: str, plan: dict, round_index: int, score, starting, reference):
    instrument = plan["instrument"]
    anchors = [
        score(starting) for _ in range(instrument["anchor_self_probes_per_round"])
    ]
    nulls = [
        score(semantic_noop_variant(starting, round_index * 100 + index))
        for index in range(instrument["null_variants_per_round"])
    ]
    references = [
        score(reference) for _ in range(instrument["reference_probes_per_round"])
    ]
    slower = score(SLOWER_PROBES[task_id])

    rng = random.Random(68000 + round_index * 17 + len(task_id))
    mean = statistics.fmean(nulls)
    sd = spread(nulls)
    row = {
        "round": round_index,
        "anchor_self_score": statistics.fmean(anchors),
        "null_reward_mean": mean,
        "null_reward_sd": sd,
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


def classify(verdicts: list[bool]) -> str:
    if all(verdicts):
        return "solid"
    if any(verdicts):
        return "marginal"
    return "rejected"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--preregistration",
        type=Path,
        default=Path("experiments/E68-preregistration.json"),
    )
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E68-replicated-admission.json")
    )
    args = parser.parse_args()

    plan = load_preregistration(args.preregistration)
    criteria = plan["admission_criteria"]
    rounds = plan["instrument"]["rounds"]

    tasks = []
    for task_id in plan["tasks"]:
        score, starting, reference, headroom = scorer_for(task_id)
        round_rows = []
        for index in range(rounds):
            row = measure_round(task_id, plan, index, score, starting, reference)
            row.update(judge(row, criteria))
            round_rows.append(row)
        verdicts = [row["admitted"] for row in round_rows]
        # Which criteria caused the instability, if any.
        failing = sorted(
            {
                failure.split()[0]
                for row in round_rows
                for failure in row["failures"]
            }
        )
        tasks.append(
            {
                "task_id": task_id,
                "headroom_factor": headroom,
                "rounds": round_rows,
                "admitted_rounds": sum(verdicts),
                "total_rounds": rounds,
                "classification": classify(verdicts),
                "criteria_ever_failed": failing,
            }
        )

    by_id = {row["task_id"]: row for row in tasks}
    solid = [t["task_id"] for t in tasks if t["classification"] == "solid"]
    marginal = [t["task_id"] for t in tasks if t["classification"] == "marginal"]
    rejected = [t["task_id"] for t in tasks if t["classification"] == "rejected"]
    ready = len(solid) >= 3

    report = {
        "schema_version": 1,
        "experiment_id": "E68-replicated-admission",
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
        "rounds_per_task": rounds,
        "tasks": tasks,
        "solid_tasks": solid,
        "marginal_tasks": marginal,
        "rejected_tasks": rejected,
        "substrate_ready_for_search": ready,
    }

    def graded(identifier, supported, evidence):
        return {"id": identifier, "supported": supported, "evidence": evidence}

    predictions = [
        graded("H1", bool(marginal), f"marginal tasks: {marginal or 'none'}"),
        graded(
            "H2",
            by_id["power_mod"]["classification"] == "marginal",
            f"power_mod: {by_id['power_mod']['classification']} "
            f"({by_id['power_mod']['admitted_rounds']}/{rounds} rounds)",
        ),
        graded(
            "H3",
            by_id["count_primes_v2"]["classification"] == "rejected",
            f"count_primes_v2: {by_id['count_primes_v2']['classification']} "
            f"({by_id['count_primes_v2']['admitted_rounds']}/{rounds})",
        ),
        graded(
            "H4",
            by_id["optimize_function"]["classification"] == "solid",
            f"optimize_function: {by_id['optimize_function']['classification']} "
            f"({by_id['optimize_function']['admitted_rounds']}/{rounds})",
        ),
        graded("H5", len(solid) < 3, f"solid tasks: {solid or 'none'}"),
    ]
    report["predictions"] = predictions

    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)

    print(f"preregistration {plan['preregistration_digest'][:16]} verified")
    for task in tasks:
        print(
            f"\n=== {task['task_id']} ===  headroom {task['headroom_factor']:.0f}x  "
            f"{task['classification'].upper()} "
            f"({task['admitted_rounds']}/{task['total_rounds']})"
        )
        for row in task["rounds"]:
            ratio = row["signal_to_noise"]
            print(
                f"  r{row['round']}  self={row['anchor_self_score']:+.4f} "
                f"mean={row['null_reward_mean']:+.4f} sd={row['null_reward_sd']:.4f} "
                f"best5={row['best_of_5']:+.4f} "
                f"s/n={'n/a' if ratio is None else format(ratio, '.1f')}  "
                f"{'admit' if row['admitted'] else 'REJECT'}"
            )
        if task["criteria_ever_failed"]:
            print(f"  criteria ever failed: {task['criteria_ever_failed']}")

    print(f"\nsolid    = {solid or 'none'}")
    print(f"marginal = {marginal or 'none'}")
    print(f"rejected = {rejected or 'none'}")
    print(f"substrate ready for a governed search run: {ready}")
    print("\nPREDICTIONS:")
    for item in predictions:
        mark = "supported" if item["supported"] else "NOT supported"
        print(f"  {item['id']}: {mark} — {item['evidence']}")


if __name__ == "__main__":
    main()
