"""E60: re-run E59 under the corrected admission gate, against a frozen plan.

E59 recorded a defect in its own gate: ``minimum_policy_disagreements`` is an
absolute count, so ``plateau`` was admitted with 8 disagreements over 120 tasks
and then measured a paired effect of exactly zero.  E59 deliberately left it
unpatched, because changing a criterion after seeing results is precisely the
post-hoc adjustment the review criticised.

This experiment does the honest version.  ``preregister_e60.py`` froze the
criteria, instrument, analysis plan and falsifiable predictions *before* this
run, and this module reloads that document, recomputes its digest, and refuses
to proceed if the plan or the configuration it demands has drifted.  That mirrors
``recursive_lab/manifest.py``: identity is fixed up front and drift fails closed.

Only the admission gate differs from E59.  The instrument, seeds, budget,
candidate grid and protocol are identical, so the two runs are a controlled
comparison of the gate itself.

Per the frozen plan the **per-family** delta is the primary result and the
pooled delta is explicitly secondary, since pooling across families with no
possible effect dilutes any real one -- E59's main reporting weakness.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from compare_selection import _atomic_json
from compare_e59_scaled_router import (
    admission_for_family,
    evaluate_cohort,
    paired_regret_delta,
)
from preregister_e60 import digest_of
from recursive_lab.admission import AdmissionCriteria
from recursive_lab.scaled_landscape import FAMILIES, SearchBudget


class PreregistrationDriftError(RuntimeError):
    """Raised when the frozen plan is missing, altered, or not the one requested."""


def load_preregistration(path: Path) -> dict:
    """Load the frozen plan and fail closed on any tampering."""
    if not path.is_file():
        raise PreregistrationDriftError(
            f"{path} is missing; run preregister_e60.py before this experiment"
        )
    document = json.loads(path.read_text())
    stored = document.get("preregistration_digest")
    if not stored:
        raise PreregistrationDriftError(f"{path} carries no preregistration_digest")
    recomputed = digest_of(document)
    if recomputed != stored:
        raise PreregistrationDriftError(
            f"{path} digest mismatch: stored {stored}, recomputed {recomputed}. "
            "The frozen plan was edited after it was registered."
        )
    return document


def grade(prediction_id: str, outcome: bool, evidence: str) -> dict:
    return {
        "id": prediction_id,
        "supported": outcome,
        "evidence": evidence,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--preregistration",
        type=Path,
        default=Path("experiments/E60-preregistration.json"),
    )
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E60-corrected-admission.json")
    )
    args = parser.parse_args()

    plan = load_preregistration(args.preregistration)
    criteria = AdmissionCriteria(**plan["criteria"])
    instrument = plan["instrument"]
    grid_size = instrument["grid_size"]
    train_seeds = instrument["train_seeds"]
    validation_seeds = instrument["validation_seeds"]
    budget = SearchBudget(grid_size, instrument["exploration_per_column"])

    # The frozen criteria must be exactly what the module defaults now encode;
    # otherwise the plan and the implementation have drifted apart.
    if criteria.to_dict() != plan["criteria"]:
        raise PreregistrationDriftError(
            "AdmissionCriteria does not round-trip the frozen criteria"
        )

    admission_rows = [
        admission_for_family(
            family, grid_size, budget, train_seeds, 0, criteria
        )
        for family in FAMILIES
    ]
    admitted = tuple(row["family"] for row in admission_rows if row["admitted"])
    rejected = tuple(row["family"] for row in admission_rows if not row["admitted"])

    report: dict = {
        "schema_version": 1,
        "experiment_id": "E60-corrected-admission",
        "claim_boundary": plan["claim_boundary"],
        "preregistration_digest": plan["preregistration_digest"],
        "supersedes": plan["supersedes"],
        "change_from_e59": plan["change_from_e59"],
        "grid_size": grid_size,
        "exploration_per_column": instrument["exploration_per_column"],
        "budget": {
            "evaluations_per_run": budget.evaluations,
            "search_space": budget.search_space,
            "coverage": budget.coverage,
        },
        "primary_metric": instrument["primary_metric"],
        "primary_analysis": plan["analysis_plan"]["primary"],
        "train_seeds": train_seeds,
        "validation_seeds": validation_seeds,
        "admission_criteria": plan["criteria"],
        "admission": admission_rows,
        "admitted_families": list(admitted),
        "rejected_families": list(rejected),
    }

    predictions: list[dict] = []
    plateau = next(row for row in admission_rows if row["family"] == "plateau")
    predictions.append(
        grade(
            "H1",
            not plateau["admitted"]
            and any("disagreement_rate" in f for f in plateau["failures"]),
            f"plateau admitted={plateau['admitted']} failures={plateau['failures']}",
        )
    )
    predictions.append(
        grade(
            "H3",
            len(admitted) < len(FAMILIES),
            f"{len(admitted)} of {len(FAMILIES)} families admitted",
        )
    )
    rate_rejected_others = [
        row["family"]
        for row in admission_rows
        if row["family"] != "plateau"
        and not row["admitted"]
        and any("disagreement_rate" in f for f in row["failures"])
    ]
    predictions.append(
        grade(
            "H4",
            bool(rate_rejected_others),
            f"other families rejected on rate: {rate_rejected_others or 'none'}",
        )
    )

    if not admitted:
        report["decision"] = "no admitted family; cohort produces no claim"
        predictions.append(
            grade("H2", False, "monotone not admitted; no delta measurable")
        )
        report["predictions"] = predictions
        canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
        report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
        _atomic_json(args.out, report)
        print("no family admitted; no comparison run")
        return

    train = evaluate_cohort(admitted, grid_size, budget, train_seeds, 0)
    winner = min(
        train.values(),
        key=lambda item: (
            item["worst_family_mean_regret"],
            item["macro_mean_regret"],
            item["r_squared_threshold"],
            item["variance_threshold"],
        ),
    )
    promoted = (winner["r_squared_threshold"], winner["variance_threshold"])
    baseline = (1.01, 0.0)
    validation_start = train_seeds
    validation = evaluate_cohort(
        admitted, grid_size, budget, validation_seeds, validation_start
    )
    paired = paired_regret_delta(
        admitted,
        grid_size,
        budget,
        validation_seeds,
        validation_start,
        promoted,
        baseline,
        87002,
    )

    report["promotion_objective"] = "worst-family mean regret, then macro regret"
    report["promoted"] = {
        "r_squared_threshold": promoted[0],
        "variance_threshold": promoted[1],
    }
    report["validation"] = validation[f"{promoted[0]}:{promoted[1]}"]
    report["random_baseline_validation"] = validation[f"{baseline[0]}:{baseline[1]}"]
    report["paired_promoted_minus_random"] = paired

    per_family = paired["per_family"]
    report["per_family_verdicts"] = {
        family: (
            "reduces regret"
            if row["regret_delta_95pct_bootstrap_ci"][1] < 0
            else "increases regret"
            if row["regret_delta_95pct_bootstrap_ci"][0] > 0
            else "inconclusive: interval spans zero"
        )
        for family, row in per_family.items()
    }

    monotone = per_family.get("monotone")
    if monotone is None:
        predictions.append(grade("H2", False, "monotone was not admitted"))
    else:
        interval = monotone["regret_delta_95pct_bootstrap_ci"]
        predictions.append(
            grade(
                "H2",
                monotone["regret_delta"] < 0 and interval[1] < 0,
                f"monotone delta={monotone['regret_delta']:.5f} ci={interval}",
            )
        )
    predictions.sort(key=lambda item: item["id"])
    report["predictions"] = predictions

    interval = paired["pooled_regret_delta_95pct_bootstrap_ci"]
    report["pooled_verdict_secondary"] = (
        "reduces regret"
        if interval[1] < 0
        else "increases regret"
        if interval[0] > 0
        else "inconclusive: interval spans zero"
    )

    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)

    print(f"preregistration {plan['preregistration_digest'][:16]} verified")
    print(f"admitted={list(admitted)}")
    print(f"rejected={list(rejected)}")
    for row in admission_rows:
        if not row["admitted"]:
            print(f"  reject {row['family']:14} {row['failures']}")
    print(f"promoted={report['promoted']}")
    print("\nPRIMARY (per family):")
    for family, row in per_family.items():
        print(
            f"  {family:14} {row['regret_delta']:+.5f} "
            f"{row['regret_delta_95pct_bootstrap_ci']} "
            f"{report['per_family_verdicts'][family]}"
        )
    print(
        f"\nsecondary pooled={paired['pooled_regret_delta']:+.5f} "
        f"ci={interval} {report['pooled_verdict_secondary']}"
    )
    print("\nPREDICTIONS:")
    for item in predictions:
        mark = "supported" if item["supported"] else "NOT supported"
        print(f"  {item['id']}: {mark} — {item['evidence']}")


if __name__ == "__main__":
    main()
