"""E71: governed search with a live model in the proposer slot.

See ``preregister_e71.py`` for the frozen plan; this module reloads it,
recomputes its digest, and refuses to run on drift.

The model sees the public task prompt, the current program and a count of
development cases passed.  It never sees the hidden cases, the oracle, the
reference solution or the held-out split.  Results are reported on held-out
cases only.

Progress is logged per arm, because E70 printed nothing until completion and a
long run was indistinguishable from a hung one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path

from compare_selection import _atomic_json
from compare_e60_corrected_admission import load_preregistration
from environments import REGISTRY
from environments.optimize_function import _validate_candidate
from recursive_lab.candidate_diversity import assess_candidate_diversity
from recursive_lab.model_proposer import (
    LocalOpenAICompatibleClient,
    ModelProgramProposer,
)
from recursive_lab.reward_probes import semantic_noop_variant
from run_e70_governed_search import split_score, stratified_split


def public_feedback(passed: int, total: int, attempt: int) -> str:
    """Coarse, public, and carrying a nonce.

    The count is a legitimate public signal -- the search's own feedback, of the
    kind any test runner reports. The attempt index is what makes the prompt
    differ between calls: this model returns one identical program on every call
    without it, even at raised temperature.
    """
    return f"passes {passed} of {total} development cases; attempt {attempt}"


def evaluate(env, source, development, heldout, start_dev, start_held, plan):
    limit = plan["instrument"]["iteration_limit"]
    timeout = plan["instrument"]["candidate_timeout_seconds"]
    outcomes = env.case_results(source, timeout_s=timeout, iteration_limit=limit)
    return (
        split_score(outcomes, development, start_dev),
        split_score(outcomes, heldout, start_held),
        sum(1 for i in development if outcomes[i]),
    )


def run_governed(env, plan, proposer, seed, dev, held, start_dev, start_held):
    proposals = plan["instrument"]["proposals_per_governed_run"]
    starting = env.starting_solution
    incumbent, incumbent_dev = starting, 0.0
    incumbent_passed = start_dev
    digests, receipts = [], []
    valid = 0
    promotions = 0

    for attempt in range(proposals):
        result = proposer.propose(
            env.task_prompt,
            incumbent,
            public_feedback(incumbent_passed, len(dev), attempt * 7 + seed),
        )
        receipts.append(result.receipt.to_dict())
        if result.candidate is None:
            continue
        digests.append(result.receipt.candidate_digest)
        if _validate_candidate(result.candidate)[1] is not None:
            continue
        valid += 1
        dev_delta, _held_delta, passed = evaluate(
            env, result.candidate, dev, held, start_dev, start_held, plan
        )
        # Strictly greater: a tie never displaces the incumbent.
        if dev_delta > incumbent_dev:
            incumbent, incumbent_dev, incumbent_passed = (
                result.candidate,
                dev_delta,
                passed,
            )
            promotions += 1

    diversity = assess_candidate_diversity(digests) if digests else None
    unique = 0 if diversity is None else diversity.unique_candidates
    void = unique < plan["instrument"]["minimum_unique_candidates"]
    dev_delta, held_delta, _ = evaluate(
        env, incumbent, dev, held, start_dev, start_held, plan
    )
    return {
        "seed": seed,
        "proposals": proposals,
        "valid_candidates": valid,
        "unique_candidates": unique,
        "promotions": promotions,
        "development_delta": dev_delta,
        "heldout_delta": held_delta,
        "void": void,
        "receipts": receipts,
    }


def run_single_shot(env, plan, proposer, seed, dev, held, start_dev, start_held):
    result = proposer.propose(
        env.task_prompt, env.starting_solution, public_feedback(start_dev, len(dev), seed)
    )
    if result.candidate is None or _validate_candidate(result.candidate)[1] is not None:
        return {
            "seed": seed,
            "valid_candidates": 0,
            "development_delta": 0.0,
            "heldout_delta": 0.0,
            "receipts": [result.receipt.to_dict()],
        }
    dev_delta, held_delta, _ = evaluate(
        env, result.candidate, dev, held, start_dev, start_held, plan
    )
    return {
        "seed": seed,
        "valid_candidates": 1,
        "development_delta": dev_delta,
        "heldout_delta": held_delta,
        "receipts": [result.receipt.to_dict()],
    }


def run_null(env, plan, seed, dev, held, start_dev, start_held):
    proposals = plan["instrument"]["proposals_per_governed_run"]
    best_dev, best = 0.0, env.starting_solution
    for attempt in range(proposals):
        variant = semantic_noop_variant(env.starting_solution, seed * 100 + attempt)
        dev_delta, _h, _p = evaluate(
            env, variant, dev, held, start_dev, start_held, plan
        )
        if dev_delta > best_dev:
            best_dev, best = dev_delta, variant
    dev_delta, held_delta, _ = evaluate(
        env, best, dev, held, start_dev, start_held, plan
    )
    return {
        "seed": seed,
        "development_delta": dev_delta,
        "heldout_delta": held_delta,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--preregistration",
        type=Path,
        default=Path("experiments/E71-preregistration.json"),
    )
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E71-model-governed-search.json")
    )
    args = parser.parse_args()

    plan = load_preregistration(args.preregistration)
    instrument = plan["instrument"]
    seeds = instrument["seeds_per_arm"]
    proposer_config = plan["proposer"]
    client = LocalOpenAICompatibleClient(base_url=proposer_config["endpoint"])
    started = time.perf_counter()

    tasks = []
    for task_id in plan["tasks"]:
        env = REGISTRY[task_id]()
        limit = instrument["iteration_limit"]
        start_outcomes = env.case_results(
            env.starting_solution,
            timeout_s=instrument["candidate_timeout_seconds"],
            iteration_limit=limit,
        )
        dev, held = stratified_split(start_outcomes)
        start_dev = sum(1 for i in dev if start_outcomes[i])
        start_held = sum(1 for i in held if start_outcomes[i])
        print(
            f"[{task_id}] dev {len(dev)} (headroom {len(dev) - start_dev}), "
            f"held-out {len(held)} (headroom {len(held) - start_held})",
            flush=True,
        )

        proposer = ModelProgramProposer(
            client,
            model="default_model",
            temperature=proposer_config["temperature"],
        )
        arms: dict = {}
        governed = [
            run_governed(env, plan, proposer, s, dev, held, start_dev, start_held)
            for s in range(seeds)
        ]
        print(
            f"  [{task_id}/governed] held-out "
            f"{statistics.fmean(r['heldout_delta'] for r in governed):+.4f}  "
            f"unique {[r['unique_candidates'] for r in governed]}  "
            f"void {[r['void'] for r in governed]}",
            flush=True,
        )
        single = [
            run_single_shot(env, plan, proposer, s, dev, held, start_dev, start_held)
            for s in range(seeds)
        ]
        print(
            f"  [{task_id}/single_shot] held-out "
            f"{statistics.fmean(r['heldout_delta'] for r in single):+.4f}",
            flush=True,
        )
        null = [
            run_null(env, plan, s, dev, held, start_dev, start_held)
            for s in range(seeds)
        ]
        print(
            f"  [{task_id}/null_only] held-out "
            f"{statistics.fmean(r['heldout_delta'] for r in null):+.4f}",
            flush=True,
        )

        for name, runs in (
            ("governed", governed),
            ("single_shot", single),
            ("null_only", null),
        ):
            arms[name] = {
                "runs": runs,
                "mean_development_delta": statistics.fmean(
                    r["development_delta"] for r in runs
                ),
                "mean_heldout_delta": statistics.fmean(r["heldout_delta"] for r in runs),
                "max_heldout_delta": max(r["heldout_delta"] for r in runs),
            }
        tasks.append(
            {
                "task_id": task_id,
                "development_cases": len(dev),
                "heldout_cases": len(held),
                "development_headroom": len(dev) - start_dev,
                "heldout_headroom": len(held) - start_held,
                "arms": arms,
                "model_calls_so_far": proposer.calls,
                "tokens_so_far": proposer.total_tokens,
            }
        )

    by_id = {t["task_id"]: t for t in tasks}
    arm_names = ("governed", "single_shot", "null_only")
    pooled = {
        arm: statistics.fmean(t["arms"][arm]["mean_heldout_delta"] for t in tasks)
        for arm in arm_names
    }
    all_receipts = [
        receipt
        for t in tasks
        for arm in ("governed", "single_shot")
        for run in t["arms"][arm]["runs"]
        for receipt in run.get("receipts", [])
    ]
    parsed = sum(1 for r in all_receipts if r["parse_ok"])
    valid_total = sum(
        run["valid_candidates"]
        for t in tasks
        for arm in ("governed", "single_shot")
        for run in t["arms"][arm]["runs"]
    )

    report = {
        "schema_version": 1,
        "experiment_id": "E71-model-governed-search",
        "claim_boundary": plan["claim_boundary"],
        "capability_claim_boundary": plan["capability_claim_boundary"],
        "preregistration_digest": plan["preregistration_digest"],
        "follows": plan["follows"],
        "question": plan["question"],
        "proposer": plan["proposer"],
        "trust_boundary": plan["trust_boundary"],
        "tasks": tasks,
        "pooled_mean_heldout_delta": pooled,
        "model_calls": len(all_receipts),
        "proposals_parsed": parsed,
        "proposals_validator_clean": valid_total,
        "wall_seconds": time.perf_counter() - started,
    }

    def graded(identifier, supported, evidence):
        return {"id": identifier, "supported": supported, "evidence": evidence}

    null_deltas = [
        r["heldout_delta"] for t in tasks for r in t["arms"]["null_only"]["runs"]
    ]
    gov = {t["task_id"]: t["arms"]["governed"]["mean_heldout_delta"] for t in tasks}
    shot = {t["task_id"]: t["arms"]["single_shot"]["mean_heldout_delta"] for t in tasks}
    voids = [
        (t["task_id"], r["seed"])
        for t in tasks
        for r in t["arms"]["governed"]["runs"]
        if r["void"]
    ]
    validity = valid_total / max(1, len(all_receipts))
    predictions = [
        graded("H1", all(v == 0.0 for v in null_deltas),
               f"null_only held-out: max={max(null_deltas):+.6f} min={min(null_deltas):+.6f}"),
        graded("H2", sum(1 for v in gov.values() if v > 0.0) >= 2,
               f"governed positive on {sum(1 for v in gov.values() if v > 0.0)} tasks: "
               f"{ {k: round(v, 4) for k, v in gov.items()} }"),
        graded("H3", any(v > 0.0 for v in shot.values()),
               f"single_shot: { {k: round(v, 4) for k, v in shot.items()} }"),
        graded("H4", pooled["governed"] >= pooled["single_shot"],
               f"pooled governed={pooled['governed']:+.4f} vs "
               f"single_shot={pooled['single_shot']:+.4f}"),
        graded("H5", not voids, f"void governed runs: {voids or 'none'}"),
        graded("H6", validity >= 0.80,
               f"validator-clean {valid_total}/{len(all_receipts)} = {validity:.0%}"),
    ]
    report["predictions"] = predictions

    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)

    print(f"\npreregistration {plan['preregistration_digest'][:16]} verified")
    for task in tasks:
        print(f"\n=== {task['task_id']} ===")
        for arm in arm_names:
            row = task["arms"][arm]
            print(
                f"  {arm:12} dev={row['mean_development_delta']:+.4f}  "
                f"held-out={row['mean_heldout_delta']:+.4f}  "
                f"max={row['max_heldout_delta']:+.4f}"
            )
    print(f"\npooled held-out: { {k: round(v, 4) for k, v in pooled.items()} }")
    print(
        f"model calls {report['model_calls']}, parsed {parsed}, "
        f"validator-clean {valid_total}, wall {report['wall_seconds']:.0f}s"
    )
    print("\nPREDICTIONS:")
    for item in predictions:
        mark = "supported" if item["supported"] else "NOT supported"
        print(f"  {item['id']}: {mark} — {item['evidence']}")
    _ = by_id


if __name__ == "__main__":
    main()
