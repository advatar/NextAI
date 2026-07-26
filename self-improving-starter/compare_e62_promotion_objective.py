"""E62: compare three promotion objectives across two disjoint held-out blocks.

See ``preregister_e62.py`` for the frozen plan; this module reloads it,
recomputes its digest, and refuses to run on drift.

Two structural commitments distinguish this run from E59-E61:

* **Replication is built in.** Every effect is measured independently on two
  disjoint held-out seed blocks. An effect counts as a result only if both
  blocks agree in sign, both intervals exclude zero, and both point estimates
  clear the minimum effect size. E60's rugged regression would have been caught
  by this rule at the time rather than one experiment later.

* **No single yardstick decides.** Each objective is advantaged on the metric it
  optimises, so every selected router is scored on both yardsticks and the
  question asked is whether any objective generalises beyond its own.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from compare_selection import _atomic_json
from compare_e59_scaled_router import CANDIDATES, policy_for
from compare_e60_corrected_admission import (
    PreregistrationDriftError,
    load_preregistration,
)
from recursive_lab.admission import (
    AdmissionCriteria,
    CohortObservations,
    evaluate_admission,
)
from recursive_lab.scaled_landscape import (
    ALWAYS_SURROGATE_POLICY,
    FAMILIES,
    RANDOM_POLICY,
    SearchBudget,
    bootstrap_ci,
    make_spec,
    mean,
    run_policy,
)

BASELINE = (1.01, 0.0)


def admit_families(grid_size, budget, seeds, seed_start, criteria):
    """Admission and per-family disagreement rates, from the baseline only."""
    rows = []
    for family in FAMILIES:
        hits = 0
        disagreements = 0
        for seed in range(seed_start, seed_start + seeds):
            spec = make_spec(family, grid_size, seed=seed)
            baseline = run_policy(spec, budget, RANDOM_POLICY, seed=seed)
            reference = run_policy(spec, budget, ALWAYS_SURROGATE_POLICY, seed=seed)
            hits += int(baseline.target_hit)
            if abs(baseline.regret - reference.regret) > 1e-12:
                disagreements += 1
        observations = CohortObservations(
            exploration_target_rate=hits / seeds,
            policy_disagreements=disagreements,
            tasks=seeds,
        )
        result = evaluate_admission(observations, criteria)
        rows.append(
            {
                "family": family,
                "admitted": result.admitted,
                "failures": list(result.failures),
                "policy_disagreement_rate": observations.policy_disagreement_rate,
                "exploration_target_rate": observations.exploration_target_rate,
            }
        )
    return rows


def family_regrets(families, grid_size, budget, seeds, seed_start, candidate):
    """Mean regret per family for one candidate router."""
    policy = policy_for(candidate)
    return {
        family: mean(
            run_policy(
                make_spec(family, grid_size, seed=seed), budget, policy, seed=seed
            ).regret
            for seed in range(seed_start, seed_start + seeds)
        )
        for family in families
    }


def score_objective(name, per_family, weights):
    if name == "worst_family":
        return max(per_family.values())
    if name == "macro_mean":
        return mean(per_family.values())
    total = sum(weights[family] for family in per_family)
    if total <= 0:
        raise ValueError("signal weights sum to zero")
    return sum(per_family[f] * weights[f] for f in per_family) / total


def paired_deltas(families, grid_size, budget, seeds, seed_start, candidate, salt):
    """Paired candidate-minus-random regret per family on one block."""
    policy = policy_for(candidate)
    control = policy_for(BASELINE)
    rows = {}
    for index, family in enumerate(families):
        deltas = []
        for seed in range(seed_start, seed_start + seeds):
            spec = make_spec(family, grid_size, seed=seed)
            arm = run_policy(spec, budget, policy, seed=seed).regret
            base = run_policy(spec, budget, control, seed=seed).regret
            deltas.append(arm - base)
        rows[family] = {
            "regret_delta": mean(deltas),
            "regret_delta_95pct_bootstrap_ci": bootstrap_ci(deltas, salt + index),
        }
    return rows


def excludes_zero(interval):
    return interval[1] < 0 or interval[0] > 0


def replication_verdict(block_a, block_b, floor):
    """Both blocks must agree before anything is called a result."""
    a_delta = block_a["regret_delta"]
    b_delta = block_b["regret_delta"]
    a_ok = excludes_zero(block_a["regret_delta_95pct_bootstrap_ci"])
    b_ok = excludes_zero(block_b["regret_delta_95pct_bootstrap_ci"])
    same_sign = (a_delta < 0) == (b_delta < 0)
    clears = abs(a_delta) >= floor and abs(b_delta) >= floor

    if a_ok and b_ok and same_sign and clears:
        return "replicated: reduces regret" if a_delta < 0 else "replicated: increases regret"
    if a_ok and b_ok and same_sign:
        return "replicated but negligible"
    if a_ok != b_ok:
        return "UNREPLICATED: clears in one block only"
    if a_ok and b_ok and not same_sign:
        return "UNREPLICATED: blocks disagree in sign"
    return "inconclusive in both blocks"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--preregistration",
        type=Path,
        default=Path("experiments/E62-preregistration.json"),
    )
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E62-promotion-objective.json")
    )
    args = parser.parse_args()

    plan = load_preregistration(args.preregistration)
    criteria = AdmissionCriteria(**plan["criteria"])
    if criteria.to_dict() != plan["criteria"]:
        raise PreregistrationDriftError(
            "AdmissionCriteria does not round-trip the frozen criteria"
        )

    instrument = plan["instrument"]
    grid_size = instrument["grid_size"]
    budget = SearchBudget(grid_size, instrument["exploration_per_column"])
    train_seeds = instrument["train_seeds"]
    train_start = instrument["train_seed_start"]
    block_seeds = instrument["block_seeds"]
    blocks = {
        "block_a": instrument["block_a_seed_start"],
        "block_b": instrument["block_b_seed_start"],
    }
    floor = plan["minimum_effect_size"]
    objectives = list(plan["objectives"])

    admission_rows = admit_families(
        grid_size, budget, train_seeds, train_start, criteria
    )
    admitted = tuple(row["family"] for row in admission_rows if row["admitted"])
    weights = {
        row["family"]: row["policy_disagreement_rate"] for row in admission_rows
    }

    report: dict = {
        "schema_version": 1,
        "experiment_id": "E62-promotion-objective",
        "claim_boundary": plan["claim_boundary"],
        "preregistration_digest": plan["preregistration_digest"],
        "follows": plan["follows"],
        "question": plan["question"],
        "grid_size": grid_size,
        "minimum_effect_size": floor,
        "replication_rule": plan["replication_rule"],
        "budget": {
            "evaluations_per_run": budget.evaluations,
            "search_space": budget.search_space,
            "coverage": budget.coverage,
        },
        "seeds": {
            "train": [train_start, train_start + train_seeds - 1],
            "block_a": [blocks["block_a"], blocks["block_a"] + block_seeds - 1],
            "block_b": [blocks["block_b"], blocks["block_b"] + block_seeds - 1],
        },
        "admission": admission_rows,
        "admitted_families": list(admitted),
        "signal_weights": {f: weights[f] for f in admitted},
    }

    if not admitted:
        report["decision"] = "no admitted family; cohort produces no claim"
        canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
        report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
        _atomic_json(args.out, report)
        print("no family admitted")
        return

    # Selection: score every candidate once on train, then apply each objective.
    train_scores = {
        candidate: family_regrets(
            admitted, grid_size, budget, train_seeds, train_start, candidate
        )
        for candidate in CANDIDATES
    }
    selections = {}
    for objective in objectives:
        best = min(
            CANDIDATES,
            key=lambda c: (
                score_objective(objective, train_scores[c], weights),
                c[0],
                c[1],
            ),
        )
        selections[objective] = {
            "r_squared_threshold": best[0],
            "variance_threshold": best[1],
            "train_objective_score": score_objective(
                objective, train_scores[best], weights
            ),
        }
    report["selections"] = selections

    # Evaluation: both yardsticks and per-family deltas, on both blocks.
    evaluation: dict = {}
    for objective in objectives:
        chosen = (
            selections[objective]["r_squared_threshold"],
            selections[objective]["variance_threshold"],
        )
        per_block = {}
        for block_name, start in blocks.items():
            regrets = family_regrets(
                admitted, grid_size, budget, block_seeds, start, chosen
            )
            per_block[block_name] = {
                "family_mean_regret": regrets,
                "macro_mean_regret": mean(regrets.values()),
                "worst_family_regret": max(regrets.values()),
                "per_family_delta": paired_deltas(
                    admitted,
                    grid_size,
                    budget,
                    block_seeds,
                    start,
                    chosen,
                    93000 + 100 * objectives.index(objective),
                ),
            }
        verdicts = {
            family: replication_verdict(
                per_block["block_a"]["per_family_delta"][family],
                per_block["block_b"]["per_family_delta"][family],
                floor,
            )
            for family in admitted
        }
        evaluation[objective] = {
            "router": selections[objective],
            "blocks": per_block,
            "replication_verdicts": verdicts,
        }
    report["evaluation"] = evaluation

    # Grade the frozen predictions.
    routers = {
        objective: (
            selections[objective]["r_squared_threshold"],
            selections[objective]["variance_threshold"],
        )
        for objective in objectives
    }

    def graded(identifier, supported, evidence):
        return {"id": identifier, "supported": supported, "evidence": evidence}

    predictions = []
    predictions.append(
        graded(
            "H1",
            len(set(routers.values())) > 1,
            f"selected routers: {routers}",
        )
    )

    worst_macro = {
        block: evaluation["worst_family"]["blocks"][block]["macro_mean_regret"]
        for block in blocks
    }
    beaten_in_both = [
        objective
        for objective in objectives
        if objective != "worst_family"
        and all(
            evaluation[objective]["blocks"][block]["macro_mean_regret"]
            < worst_macro[block]
            for block in blocks
        )
    ]
    predictions.append(
        graded(
            "H2",
            bool(beaten_in_both),
            f"objectives beating worst_family on macro in both blocks: "
            f"{beaten_in_both or 'none'}",
        )
    )
    predictions.append(
        graded(
            "H3",
            any(router[0] >= 0.5 for router in routers.values()),
            f"selected R^2 thresholds: {[r[0] for r in routers.values()]}",
        )
    )

    ranking = {
        block: sorted(
            objectives,
            key=lambda o: evaluation[o]["blocks"][block]["macro_mean_regret"],
        )
        for block in blocks
    }
    predictions.append(
        graded(
            "H4",
            ranking["block_a"] == ranking["block_b"],
            f"block_a={ranking['block_a']} block_b={ranking['block_b']}",
        )
    )

    unreplicated = [
        f"{objective}/{family}"
        for objective in objectives
        for family, verdict in evaluation[objective]["replication_verdicts"].items()
        if verdict.startswith("UNREPLICATED")
    ]
    predictions.append(
        graded(
            "H5",
            bool(unreplicated),
            f"unreplicated effects: {unreplicated or 'none'}",
        )
    )
    report["predictions"] = predictions
    report["macro_ranking"] = ranking

    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)

    print(f"preregistration {plan['preregistration_digest'][:16]} verified")
    print(f"admitted={list(admitted)}")
    print(f"signal weights={ {f: round(weights[f], 3) for f in admitted} }")
    print("\nSELECTED ROUTERS")
    for objective in objectives:
        router = selections[objective]
        print(
            f"  {objective:16} R2>={router['r_squared_threshold']:<5} "
            f"var>={router['variance_threshold']}"
        )
    print("\nHELD-OUT SCORES (both yardsticks, both blocks)")
    for objective in objectives:
        for block in blocks:
            data = evaluation[objective]["blocks"][block]
            print(
                f"  {objective:16} {block:8} macro={data['macro_mean_regret']:.5f} "
                f"worst={data['worst_family_regret']:.5f}"
            )
    print("\nPER-FAMILY REPLICATION")
    for objective in objectives:
        print(f"  {objective}")
        for family, verdict in evaluation[objective]["replication_verdicts"].items():
            a = evaluation[objective]["blocks"]["block_a"]["per_family_delta"][family]
            b = evaluation[objective]["blocks"]["block_b"]["per_family_delta"][family]
            print(
                f"    {family:14} A={a['regret_delta']:+.5f} "
                f"B={b['regret_delta']:+.5f}  {verdict}"
            )
    print("\nPREDICTIONS:")
    for item in predictions:
        mark = "supported" if item["supported"] else "NOT supported"
        print(f"  {item['id']}: {mark} — {item['evidence']}")


if __name__ == "__main__":
    main()
