"""E61: causal ablation of the rugged regression E60 measured.

Runs four arms on shared seeds and decomposes the harm. See
``preregister_e61.py`` for the frozen plan; this module reloads it, recomputes
its digest, and refuses to run on drift.

The key comparison is ``e60_promoted`` against ``endpoint_control``.  Both fire
on the same condition and both always land on one end of a column's unseen
range; they differ only in whether the fitted line or a coin flip picks which
end.  Their difference is therefore the fit-following component of the effect,
and whatever remains is attributable to endpoint narrowing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from compare_selection import _atomic_json
from compare_e60_corrected_admission import (
    PreregistrationDriftError,
    load_preregistration,
)
from recursive_lab.admission import AdmissionCriteria, CohortObservations, evaluate_admission
from recursive_lab.scaled_landscape import (
    ALWAYS_SURROGATE_POLICY,
    ENDPOINT_COINFLIP_MODE,
    RANDOM_POLICY,
    RouterPolicy,
    SearchBudget,
    bootstrap_ci,
    make_spec,
    mean,
    run_policy,
)

ARMS = {
    "random": RANDOM_POLICY,
    "e60_promoted": RouterPolicy("e60_promoted", 0.0, 0.03),
    "endpoint_control": RouterPolicy(
        "endpoint_control", 0.0, 0.03, ENDPOINT_COINFLIP_MODE
    ),
    "e41_gate": RouterPolicy("e41_gate", 0.5, 0.01),
}


def interval_excludes_zero(interval: list[float]) -> bool:
    return interval[1] < 0 or interval[0] > 0


def verdict(delta: float, interval: list[float], floor: float) -> str:
    if not interval_excludes_zero(interval):
        return "inconclusive: interval spans zero"
    if abs(delta) < floor:
        return f"negligible: |{delta:.5f}| below minimum effect size {floor}"
    return "reduces regret" if delta < 0 else "increases regret"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--preregistration",
        type=Path,
        default=Path("experiments/E61-preregistration.json"),
    )
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E61-rugged-ablation.json")
    )
    args = parser.parse_args()

    plan = load_preregistration(args.preregistration)
    criteria = AdmissionCriteria(**plan["criteria"])
    instrument = plan["instrument"]
    grid_size = instrument["grid_size"]
    seeds = instrument["seeds"]
    seed_start = instrument["seed_start"]
    floor = plan["minimum_effect_size"]
    budget = SearchBudget(grid_size, instrument["exploration_per_column"])
    families = tuple(plan["families"])

    if criteria.to_dict() != plan["criteria"]:
        raise PreregistrationDriftError(
            "AdmissionCriteria does not round-trip the frozen criteria"
        )

    report: dict = {
        "schema_version": 1,
        "experiment_id": "E61-rugged-ablation",
        "claim_boundary": plan["claim_boundary"],
        "preregistration_digest": plan["preregistration_digest"],
        "follows": plan["follows"],
        "question": plan["question"],
        "grid_size": grid_size,
        "seeds": seeds,
        "seed_start": seed_start,
        "minimum_effect_size": floor,
        "budget": {
            "evaluations_per_run": budget.evaluations,
            "search_space": budget.search_space,
            "coverage": budget.coverage,
        },
        "arms": plan["arms"],
        "families": list(families),
    }

    admission_rows = []
    per_family: dict[str, dict] = {}

    for family in families:
        # Per-seed regret for every arm, on shared landscapes.
        regrets: dict[str, list[float]] = {name: [] for name in ARMS}
        endpoint_rates: dict[str, list[float]] = {name: [] for name in ARMS}
        baseline_hits = 0
        disagreements = 0

        for seed in range(seed_start, seed_start + seeds):
            spec = make_spec(family, grid_size, seed=seed)
            runs = {
                name: run_policy(spec, budget, policy, seed=seed)
                for name, policy in ARMS.items()
            }
            for name, run in runs.items():
                regrets[name].append(run.regret)
                endpoint_rates[name].append(run.endpoint_picks / grid_size)
            baseline_hits += int(runs["random"].target_hit)
            reference = run_policy(
                spec, budget, ALWAYS_SURROGATE_POLICY, seed=seed
            )
            if abs(runs["random"].regret - reference.regret) > 1e-12:
                disagreements += 1

        observations = CohortObservations(
            exploration_target_rate=baseline_hits / seeds,
            policy_disagreements=disagreements,
            tasks=seeds,
        )
        admission = evaluate_admission(observations, criteria)
        admission_rows.append(
            {
                "family": family,
                "admitted": admission.admitted,
                "failures": list(admission.failures),
                "observed": {
                    "exploration_target_rate": observations.exploration_target_rate,
                    "policy_disagreements": observations.policy_disagreements,
                    "policy_disagreement_rate": observations.policy_disagreement_rate,
                    "tasks": observations.tasks,
                },
            }
        )
        if not admission.admitted:
            per_family[family] = {"admitted": False}
            continue

        baseline = regrets["random"]
        arm_rows = {}
        for index, name in enumerate(ARMS):
            if name == "random":
                continue
            deltas = [
                arm - control for arm, control in zip(regrets[name], baseline)
            ]
            delta = mean(deltas)
            interval = bootstrap_ci(deltas, 91000 + index)
            arm_rows[name] = {
                "mean_regret": mean(regrets[name]),
                "regret_delta_vs_random": delta,
                "regret_delta_95pct_bootstrap_ci": interval,
                "verdict": verdict(delta, interval, floor),
                "mean_endpoint_pick_rate": mean(endpoint_rates[name]),
            }

        # The decomposition: fit-following isolated from endpoint narrowing.
        fit_component = [
            promoted - control
            for promoted, control in zip(
                regrets["e60_promoted"], regrets["endpoint_control"]
            )
        ]
        fit_delta = mean(fit_component)
        fit_interval = bootstrap_ci(fit_component, 91500)

        per_family[family] = {
            "admitted": True,
            "random_mean_regret": mean(baseline),
            "random_endpoint_pick_rate": mean(endpoint_rates["random"]),
            "arms": arm_rows,
            "fit_following_component": {
                "definition": "e60_promoted minus endpoint_control, paired",
                "delta": fit_delta,
                "delta_95pct_bootstrap_ci": fit_interval,
                "interval_excludes_zero": interval_excludes_zero(fit_interval),
            },
        }

    report["admission"] = admission_rows
    report["results"] = per_family

    # Grade the frozen predictions, including any that fail.
    predictions = []
    rugged = per_family.get("rugged", {})
    monotone = per_family.get("monotone", {})

    def graded(identifier: str, supported: bool, evidence: str) -> dict:
        return {"id": identifier, "supported": supported, "evidence": evidence}

    if rugged.get("admitted"):
        promoted = rugged["arms"]["e60_promoted"]
        control = rugged["arms"]["endpoint_control"]
        gate = rugged["arms"]["e41_gate"]
        component = rugged["fit_following_component"]
        predictions.append(
            graded(
                "H1",
                promoted["regret_delta_vs_random"] > 0
                and interval_excludes_zero(promoted["regret_delta_95pct_bootstrap_ci"])
                and abs(promoted["regret_delta_vs_random"]) >= floor,
                f"e60_promoted delta={promoted['regret_delta_vs_random']:+.5f} "
                f"ci={promoted['regret_delta_95pct_bootstrap_ci']}",
            )
        )
        predictions.append(
            graded(
                "H2",
                control["regret_delta_vs_random"] > 0
                and interval_excludes_zero(control["regret_delta_95pct_bootstrap_ci"]),
                f"endpoint_control delta={control['regret_delta_vs_random']:+.5f} "
                f"ci={control['regret_delta_95pct_bootstrap_ci']}",
            )
        )
        predictions.append(
            graded(
                "H3",
                not component["interval_excludes_zero"],
                f"fit-following component={component['delta']:+.5f} "
                f"ci={component['delta_95pct_bootstrap_ci']}",
            )
        )
        predictions.append(
            graded(
                "H5",
                gate["regret_delta_vs_random"] < promoted["regret_delta_vs_random"],
                f"e41_gate delta={gate['regret_delta_vs_random']:+.5f} vs "
                f"e60_promoted {promoted['regret_delta_vs_random']:+.5f}",
            )
        )
    else:
        for identifier in ("H1", "H2", "H3", "H5"):
            predictions.append(graded(identifier, False, "rugged not admitted"))

    if monotone.get("admitted"):
        component = monotone["fit_following_component"]
        predictions.append(
            graded(
                "H4",
                component["delta"] < 0 and component["interval_excludes_zero"],
                f"fit-following component={component['delta']:+.5f} "
                f"ci={component['delta_95pct_bootstrap_ci']}",
            )
        )
    else:
        predictions.append(graded("H4", False, "monotone not admitted"))

    predictions.sort(key=lambda item: item["id"])
    report["predictions"] = predictions

    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)

    print(f"preregistration {plan['preregistration_digest'][:16]} verified")
    print(f"seeds {seed_start}-{seed_start + seeds - 1} (disjoint from E59/E60)")
    for family in families:
        result = per_family[family]
        print(f"\n=== {family} ===")
        if not result["admitted"]:
            row = next(r for r in admission_rows if r["family"] == family)
            print(f"  NOT ADMITTED: {row['failures']}")
            continue
        print(
            f"  random mean regret {result['random_mean_regret']:.5f} "
            f"(endpoint rate {result['random_endpoint_pick_rate']:.3f})"
        )
        for name, row in result["arms"].items():
            print(
                f"  {name:18} {row['regret_delta_vs_random']:+.5f} "
                f"{row['regret_delta_95pct_bootstrap_ci']} "
                f"endpoint={row['mean_endpoint_pick_rate']:.2f} "
                f"{row['verdict']}"
            )
        component = result["fit_following_component"]
        print(
            f"  fit-following component {component['delta']:+.5f} "
            f"{component['delta_95pct_bootstrap_ci']} "
            f"excludes_zero={component['interval_excludes_zero']}"
        )

    print("\nPREDICTIONS:")
    for item in predictions:
        mark = "supported" if item["supported"] else "NOT supported"
        print(f"  {item['id']}: {mark} — {item['evidence']}")


if __name__ == "__main__":
    main()
