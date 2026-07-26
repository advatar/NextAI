"""E65: re-audit the substrate with probes the environments cannot evade.

See ``preregister_e65.py`` for the frozen plan; this module reloads it,
recomputes its digest, and refuses to run on drift.  It makes no capability
claim under any outcome.

The corrections over E63/E64 are in :mod:`recursive_lab.reward_probes`: null
variants are AST-distinct so identity checks cannot recognise them, a
monotonicity probe distinguishes a censored reward from a precise one, and
median-of-m is measured as a curve rather than assumed.
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
from recursive_lab.reward_probes import (
    best_of_k,
    is_semantically_distinct_source,
    median_of_subsample,
    monotonicity_probe,
    semantic_noop_variant,
    spread,
)

#: Strong solutions for tasks that do not expose ``reference_solution``.
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

#: Correct programs that do the same work twice and return the second result,
#: so they are about 2x slower.  An honest reward must score these negative.
SLOWER_PROBES = {
    "optimize_function": (
        "def solve(n):\n"
        "    total = 0\n"
        "    for i in range(n):\n"
        "        total += i * i\n"
        "    second = 0\n"
        "    for i in range(n):\n"
        "        second += i * i\n"
        "    return second\n"
    ),
    "count_primes": (
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
    ),
    "power_mod": (
        "def solve(n):\n"
        "    result = 1\n"
        "    for _step in range(n):\n"
        "        result = result * 7 % 1000000007\n"
        "    second = 1\n"
        "    for _step in range(n):\n"
        "        second = second * 7 % 1000000007\n"
        "    return second\n"
    ),
}
SLOWER_PROBES["count_primes_v2"] = SLOWER_PROBES["count_primes"]


def build_environment(task_id: str):
    if task_id == "optimize_function":
        return REGISTRY[task_id](correctness_only=False)
    return REGISTRY[task_id]()


def audit_task(task_id: str, plan: dict) -> dict:
    instrument = plan["instrument"]
    criteria = plan["admission_criteria"]
    env = build_environment(task_id)
    starting = env.starting_solution

    row: dict = {"task_id": task_id}
    row["starting_solution_reward"] = env.score(starting).reward

    # -- monotonicity: does the reward fall when the program is truly slower?
    slower = SLOWER_PROBES[task_id]
    result = monotonicity_probe(
        lambda source: (
            lambda scored: (scored.reward, scored.correct)
        )(env.score(source)),
        slower,
        threshold=criteria["monotonicity_threshold"],
    )
    row["monotonicity"] = {
        "slower_reward": result.slower_reward,
        "correct": result.correct,
        "responds": result.responds,
        "detail": result.detail,
    }

    # -- null variants, each measured several times so median-of-m is a curve
    variants = []
    for index in range(instrument["null_variants_per_task"]):
        variant = semantic_noop_variant(starting, index)
        if not is_semantically_distinct_source(starting, variant):
            raise RuntimeError(
                f"{task_id}: null variant {index} is not AST-distinct; the probe "
                "would be evaded exactly as in E63/E64"
            )
        variants.append(variant)

    measurements = [
        [
            env.score(variant).reward
            for _ in range(instrument["measurements_per_variant"])
        ]
        for variant in variants
    ]
    row["null_variants"] = len(variants)
    row["measurements_per_variant"] = instrument["measurements_per_variant"]
    row["probe_is_ast_distinct"] = True

    rng = random.Random(65000 + len(task_id))
    curve = {}
    for m in instrument["median_of_m_values"]:
        per_variant = [median_of_subsample(values, m, rng) for values in measurements]
        curve[str(m)] = {
            "null_reward_mean": statistics.fmean(per_variant),
            "null_reward_sd": spread(per_variant),
            "best_of_5": best_of_k(
                per_variant, 5, instrument["bootstrap_samples"], rng
            ),
        }
    row["median_of_m"] = curve

    protocol = str(instrument["protocol_repeats"])
    row["protocol_repeats"] = instrument["protocol_repeats"]
    row["null_reward_mean"] = curve[protocol]["null_reward_mean"]
    row["null_reward_sd"] = curve[protocol]["null_reward_sd"]
    row["best_of_5"] = curve[protocol]["best_of_5"]

    # -- signal
    reference = getattr(env, "reference_solution", None)
    if not isinstance(reference, str) or not reference.strip():
        reference = EXTERNAL_REFERENCES.get(task_id)
    if reference is None:
        row["reference_reward_mean"] = None
        row["signal_to_noise"] = None
    else:
        rewards = [
            env.score(reference).reward
            for _ in range(instrument["reference_probes_per_task"])
        ]
        row["reference_reward_mean"] = statistics.fmean(rewards)
        sd = row["null_reward_sd"]
        row["signal_to_noise"] = (
            None
            if sd <= 0.0
            else (row["reference_reward_mean"] - row["null_reward_mean"]) / sd
        )
    return row


def judge(row: dict, criteria: dict) -> dict:
    failures = []
    if row["starting_solution_reward"] > criteria["maximum_starting_solution_reward"]:
        failures.append(
            f"starting_solution_reward {row['starting_solution_reward']:.3f} "
            "exceeds maximum (ships already solved)"
        )
    if not row["monotonicity"]["responds"]:
        failures.append(
            f"monotonicity: {row['monotonicity']['detail']} — the reward is "
            "censored or insensitive"
        )
    if abs(row["null_reward_mean"]) > criteria["maximum_absolute_null_reward_mean"]:
        failures.append(
            f"null_reward_mean {row['null_reward_mean']:+.3f} exceeds maximum "
            f"magnitude {criteria['maximum_absolute_null_reward_mean']}"
        )
    if row["null_reward_sd"] > criteria["maximum_null_variant_reward_sd"]:
        failures.append(
            f"null_reward_sd {row['null_reward_sd']:.3f} exceeds maximum "
            f"{criteria['maximum_null_variant_reward_sd']}"
        )
    if row["best_of_5"] > criteria["maximum_null_best_of_5_reward"]:
        failures.append(
            f"best_of_5 {row['best_of_5']:.3f} exceeds maximum "
            f"{criteria['maximum_null_best_of_5_reward']}"
        )
    reference = row["reference_reward_mean"]
    if reference is None:
        failures.append("no reference solution available; signal is unmeasured")
    elif reference < criteria["minimum_reference_reward"]:
        failures.append(
            f"reference_reward_mean {reference:.3f} is below minimum "
            f"{criteria['minimum_reference_reward']}"
        )
    ratio = row["signal_to_noise"]
    # Undefined must FAIL. E64 treated it as a pass and thereby skipped the very
    # criterion its own prediction existed to verify.
    if ratio is None:
        failures.append(
            "signal_to_noise is undefined (null spread is zero); this is "
            "evidence of censoring, not precision, and cannot count as a pass"
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
        default=Path("experiments/E65-preregistration.json"),
    )
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E65-censoring-proof-audit.json")
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

    report = {
        "schema_version": 1,
        "experiment_id": "E65-censoring-proof-audit",
        "claim_boundary": plan["claim_boundary"],
        "makes_capability_claim": False,
        "preregistration_digest": plan["preregistration_digest"],
        "follows": plan["follows"],
        "corrects": plan["corrects"],
        "question": plan["question"],
        "reproducibility_note": (
            "Measures wall-clock time; not bit-reproducible. The digest attests "
            "to the recorded report."
        ),
        "admission_criteria": criteria,
        "tasks": rows,
        "admitted_tasks": admitted,
        "rejected_tasks": rejected,
    }

    def graded(identifier, supported, evidence):
        return {"id": identifier, "supported": supported, "evidence": evidence}

    opt = by_id["optimize_function"]
    v1 = by_id["count_primes"]
    v2 = by_id["count_primes_v2"]
    pmod = by_id["power_mod"]
    predictions = [
        graded(
            "H1",
            opt["median_of_m"]["1"]["null_reward_sd"] > 0.05,
            f"optimize_function null sd at m=1 = "
            f"{opt['median_of_m']['1']['null_reward_sd']:.4f} (E64 recorded 0.0000)",
        ),
        graded(
            "H2",
            not v1["monotonicity"]["responds"],
            f"count_primes v1 slower probe scored "
            f"{v1['monotonicity']['slower_reward']:+.4f}, responds="
            f"{v1['monotonicity']['responds']}",
        ),
        graded(
            "H3",
            v2["monotonicity"]["responds"] and pmod["monotonicity"]["responds"],
            f"count_primes_v2 responds={v2['monotonicity']['responds']} "
            f"({v2['monotonicity']['slower_reward']:+.4f}); power_mod responds="
            f"{pmod['monotonicity']['responds']} "
            f"({pmod['monotonicity']['slower_reward']:+.4f})",
        ),
        graded(
            "H4",
            pmod["median_of_m"]["9"]["null_reward_sd"]
            <= 0.5 * pmod["median_of_m"]["1"]["null_reward_sd"],
            f"power_mod null sd m=1 {pmod['median_of_m']['1']['null_reward_sd']:.4f} "
            f"-> m=9 {pmod['median_of_m']['9']['null_reward_sd']:.4f}",
        ),
        graded(
            "H5",
            pmod["admitted"] and not v1["admitted"],
            f"power_mod admitted={pmod['admitted']}, count_primes v1 admitted="
            f"{v1['admitted']}",
        ),
    ]
    report["predictions"] = predictions

    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)

    print(f"preregistration {plan['preregistration_digest'][:16]} verified")
    for row in rows:
        print(f"\n=== {row['task_id']} ===")
        print(f"  starting reward {row['starting_solution_reward']:+.4f}")
        mono = row["monotonicity"]
        print(
            f"  monotonicity: slower scored {mono['slower_reward']:+.4f} "
            f"responds={mono['responds']}"
        )
        for m, values in row["median_of_m"].items():
            print(
                f"  m={m:>2}  null mean={values['null_reward_mean']:+.4f} "
                f"sd={values['null_reward_sd']:.4f} "
                f"best-of-5={values['best_of_5']:+.4f}"
            )
        ratio = row["signal_to_noise"]
        shown = "UNDEFINED" if ratio is None else f"{ratio:.1f}"
        print(
            f"  reference mean={row['reference_reward_mean']}  signal/noise={shown}"
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
