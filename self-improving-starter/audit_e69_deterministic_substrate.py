"""E69: audit the deterministic graded-correctness substrate under replication.

See ``preregister_e69.py`` for the frozen plan; this module reloads it,
recomputes its digest, and refuses to run on drift.  No capability claim is made
under any outcome.

Classification follows E68: **solid** only if admitted in every round.  The
thresholds are exactly zero rather than 0.05, because a deterministic reward has
no excuse for any spread -- anything above zero is a defect, not jitter.
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
from recursive_lab.reward_probes import best_of_k, semantic_noop_variant, spread

#: A correct-looking program that answers a constant, so it breaks cases the
#: starting solution passed.  An honest reward scores this clearly negative; a
#: censored one returns ~0.0, which is how E65 caught count_primes v1.
REGRESSION_PROBE = "def solve(n):\n    return 0\n"


def measure_round(env, plan, round_index: int) -> dict:
    instrument = plan["instrument"]
    starting = env.starting_solution

    anchors = [
        env.score(starting).reward
        for _ in range(instrument["anchor_self_probes_per_round"])
    ]
    nulls = [
        env.score(semantic_noop_variant(starting, round_index * 100 + index)).reward
        for index in range(instrument["null_variants_per_round"])
    ]
    references = [
        env.score(env.reference_solution).reward
        for _ in range(instrument["reference_probes_per_round"])
    ]
    regression = env.score(REGRESSION_PROBE).reward

    # Determinism: the same program, scored repeatedly, must give one value.
    repeats = [
        env.score(env.reference_solution).reward
        for _ in range(instrument["determinism_probes_per_round"])
    ]
    deterministic = len(set(repeats)) == 1

    rng = random.Random(69000 + round_index * 13 + len(env.name))
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
        "regression_probe_reward": regression,
        "deterministic": deterministic,
    }
    row["best_of_5"] = row["best_of_k"]["5"]
    return row


def judge(row: dict, headroom: int, criteria: dict) -> dict:
    failures = []
    if abs(row["anchor_self_score"]) > criteria["maximum_absolute_anchor_self_score"]:
        failures.append(
            f"anchor_self_score {row['anchor_self_score']:+.6f} is not exactly "
            "zero; the starting solution must score 0.0 against itself"
        )
    if abs(row["null_reward_mean"]) > criteria["maximum_absolute_null_reward_mean"]:
        failures.append(
            f"null_reward_mean {row['null_reward_mean']:+.6f} is not exactly zero"
        )
    if row["null_reward_sd"] > criteria["maximum_null_variant_reward_sd"]:
        failures.append(
            f"null_reward_sd {row['null_reward_sd']:.6f} is not exactly zero; a "
            "deterministic reward should have no spread at all"
        )
    if row["best_of_5"] > criteria["maximum_null_best_of_5_reward"]:
        failures.append(
            f"best_of_5 {row['best_of_5']:+.6f} is not exactly zero; a search "
            "could manufacture this from no-op proposals"
        )
    if row["reference_reward_mean"] < criteria["minimum_reference_reward"]:
        failures.append(
            f"reference_reward_mean {row['reference_reward_mean']:.4f} is below "
            f"{criteria['minimum_reference_reward']}"
        )
    # The discriminator between determinism and censoring.
    if row["regression_probe_reward"] > criteria["monotonicity_threshold"]:
        failures.append(
            f"regression probe scored {row['regression_probe_reward']:+.4f}; a "
            "reward that does not fall when the program is genuinely worse is "
            "censored, and zero spread would then be an artefact"
        )
    if criteria["determinism_required"] and not row["deterministic"]:
        failures.append(
            "rescoring an identical program produced different values; the "
            "environment is not deterministic"
        )
    if headroom < criteria["minimum_headroom_cases"]:
        failures.append(
            f"headroom is {headroom} cases, below the minimum "
            f"{criteria['minimum_headroom_cases']}"
        )
    return {"admitted": not failures, "failures": failures}


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
        default=Path("experiments/E69-preregistration.json"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("experiments/E69-deterministic-substrate.json"),
    )
    args = parser.parse_args()

    plan = load_preregistration(args.preregistration)
    criteria = plan["admission_criteria"]
    rounds = plan["instrument"]["rounds"]

    tasks = []
    for task_id in plan["tasks"]:
        env = REGISTRY[task_id]()
        report = env.baseline_report()
        headroom = report["headroom_cases"]
        round_rows = []
        for index in range(rounds):
            row = measure_round(env, plan, index)
            row.update(judge(row, headroom, criteria))
            round_rows.append(row)
        verdicts = [row["admitted"] for row in round_rows]
        tasks.append(
            {
                "task_id": task_id,
                "baseline": report,
                "rounds": round_rows,
                "admitted_rounds": sum(verdicts),
                "total_rounds": rounds,
                "classification": classify(verdicts),
            }
        )

    solid = [t["task_id"] for t in tasks if t["classification"] == "solid"]
    marginal = [t["task_id"] for t in tasks if t["classification"] == "marginal"]
    rejected = [t["task_id"] for t in tasks if t["classification"] == "rejected"]
    ready = len(solid) >= 3

    report = {
        "schema_version": 1,
        "experiment_id": "E69-deterministic-substrate",
        "claim_boundary": plan["claim_boundary"],
        "makes_capability_claim": False,
        "preregistration_digest": plan["preregistration_digest"],
        "follows": plan["follows"],
        "question": plan["question"],
        "reward_definition": plan["reward_definition"],
        "admission_criteria": criteria,
        "rounds_per_task": rounds,
        "tasks": tasks,
        "solid_tasks": solid,
        "marginal_tasks": marginal,
        "rejected_tasks": rejected,
        "substrate_ready_for_search": ready,
        "e68_timing_best_of_5_range": [0.018, 0.325],
    }

    def graded(identifier, supported, evidence):
        return {"id": identifier, "supported": supported, "evidence": evidence}

    all_sd = [r["null_reward_sd"] for t in tasks for r in t["rounds"]]
    all_best5 = [r["best_of_5"] for t in tasks for r in t["rounds"]]
    all_regression = [
        r["regression_probe_reward"] for t in tasks for r in t["rounds"]
    ]
    predictions = [
        graded("H1", len(solid) == len(tasks), f"solid: {solid}; marginal: {marginal}; rejected: {rejected}"),
        graded(
            "H2",
            all(value == 0.0 for value in all_sd),
            f"null sd across all rounds: max={max(all_sd):.6f}",
        ),
        graded(
            "H3",
            all(value == 0.0 for value in all_best5),
            f"best-of-5 across all rounds: max={max(all_best5):.6f} "
            f"(E68 timing tasks: +0.018 to +0.325)",
        ),
        graded(
            "H4",
            all(value < criteria["monotonicity_threshold"] for value in all_regression),
            f"regression probe range: {min(all_regression):+.4f} to "
            f"{max(all_regression):+.4f}",
        ),
        graded("H5", ready, f"{len(solid)} solid tasks; ready={ready}"),
    ]
    report["predictions"] = predictions

    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)

    print(f"preregistration {plan['preregistration_digest'][:16]} verified")
    for task in tasks:
        base = task["baseline"]
        print(
            f"\n=== {task['task_id']} ===  "
            f"{base['starting_passed']}/{base['total_cases']} at start, "
            f"headroom {base['headroom_cases']} cases  "
            f"{task['classification'].upper()} "
            f"({task['admitted_rounds']}/{task['total_rounds']})"
        )
        for row in task["rounds"]:
            print(
                f"  r{row['round']}  self={row['anchor_self_score']:+.4f} "
                f"nullsd={row['null_reward_sd']:.6f} "
                f"best5={row['best_of_5']:+.6f} "
                f"ref={row['reference_reward_mean']:+.4f} "
                f"regress={row['regression_probe_reward']:+.4f} "
                f"det={row['deterministic']}  "
                f"{'admit' if row['admitted'] else 'REJECT'}"
            )
        for row in task["rounds"]:
            for failure in row["failures"]:
                print(f"    r{row['round']}: {failure}")

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
