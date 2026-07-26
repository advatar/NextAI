"""Freeze the E60 analysis plan before the cohort is run.

E51 audited a cohort after it had already produced results.  E59 then found a
defect in its own admission gate -- ``plateau`` cleared an absolute count of 3
with 8 disagreements over 120 tasks and measured an effect of exactly zero --
and deliberately did not patch it, because changing a criterion after seeing
results is the failure mode under review.

This script writes that pre-registration down and content-hashes it.  The runner
``compare_e60_corrected_admission.py`` reloads the document, recomputes the
digest, and refuses to run if the criteria, instrument, or analysis plan differ
from what was frozen here.  The intent mirrors ``recursive_lab/manifest.py``:
run identity is fixed up front and drift fails closed, so the plan cannot be
quietly edited into agreement with whatever the data turned out to say.

Predictions are recorded as falsifiable statements.  They are graded verbatim by
the runner, including the ones that turn out wrong.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from compare_selection import _atomic_json

PREREGISTRATION = {
    "schema_version": 1,
    "experiment_id": "E60-corrected-admission",
    "supersedes": "E59-scaled-router",
    "rationale": (
        "E59 admitted the plateau family on an absolute disagreement count of 8 "
        "over 120 tasks (a rate of 6.7%) and then measured a paired regret delta "
        "of exactly 0.0 with a degenerate [0, 0] interval. An absolute count is a "
        "real bar at 5 tasks and no bar at all at 120, so admission now also "
        "requires a scale-free disagreement rate."
    ),
    "change_from_e59": (
        "Adds minimum_policy_disagreement_rate = 0.2, checked conjunctively with "
        "the existing count. The instrument, seeds, budget, candidate grid and "
        "protocol are otherwise identical to E59, so the two runs differ only in "
        "the admission gate."
    ),
    "criteria": {
        "maximum_exploration_target_rate": 0.2,
        "minimum_tasks": 5,
        "minimum_policy_disagreements": 3,
        "minimum_policy_disagreement_rate": 0.2,
    },
    "rate_threshold_justification": (
        "Chosen to mirror the existing maximum_exploration_target_rate of 0.2 "
        "rather than tuned against observed per-family rates: the reference "
        "policies must differ on at least as large a fraction of the cohort as "
        "the fraction random search is permitted to solve outright."
    ),
    "instrument": {
        "module": "recursive_lab.scaled_landscape",
        "grid_size": 128,
        "exploration_per_column": 3,
        "train_seeds": 120,
        "validation_seeds": 120,
        "primary_metric": "regret (1.0 - best_score); lower is better",
    },
    "analysis_plan": {
        "primary": (
            "Per-family paired promoted-minus-random regret delta with a 95% "
            "bootstrap interval, on admitted families only. Each family is its "
            "own claim."
        ),
        "secondary": (
            "The pooled delta across admitted families, reported but explicitly "
            "not the headline: pooling across families with no possible effect "
            "dilutes any real one. This was E59's main reporting weakness."
        ),
        "multiplicity": (
            "No multiplicity correction is applied and none is claimed. Per-family "
            "intervals are descriptive, and any family reaching an interval that "
            "excludes zero is reported as a single-family result requiring "
            "replication, not as a confirmed effect."
        ),
        "null_handling": (
            "A null or inconclusive result is recorded as measured and is not "
            "re-run, re-seeded, or re-thresholded, per POC_PLAN.md."
        ),
    },
    "predictions": [
        {
            "id": "H1",
            "statement": (
                "plateau is rejected by the corrected gate, on the disagreement "
                "rate criterion."
            ),
            "basis": "E59 measured a plateau disagreement rate of 8/120 = 0.067.",
        },
        {
            "id": "H2",
            "statement": (
                "monotone is admitted and its paired regret delta is negative "
                "with a 95% interval excluding zero."
            ),
            "basis": (
                "E59 measured monotone at -0.02372, CI [-0.02635, -0.02116]; the "
                "instrument and seeds are unchanged, so this should replicate."
            ),
        },
        {
            "id": "H3",
            "statement": "Fewer than nine families are admitted.",
            "basis": (
                "E59 admitted all nine under the count-only gate, including "
                "families whose measured effect was indistinguishable from zero."
            ),
        },
        {
            "id": "H4",
            "statement": (
                "At least one family other than plateau is rejected by the rate "
                "criterion."
            ),
            "basis": (
                "Speculative. E59 reported near-zero deltas with intervals "
                "spanning zero for curved, spike, ridge and decoy, which is "
                "consistent with -- but does not establish -- low disagreement "
                "rates. Recorded so a wrong prediction is visible."
            ),
        },
    ],
    "claim_boundary": (
        "Synthetic landscape study of one exploitation rule under a corrected "
        "admission gate. Not evidence of scaffold self-improvement or of a "
        "recursive effect."
    ),
}


def digest_of(document: dict) -> str:
    payload = {key: value for key, value in document.items() if key != "preregistration_digest"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("experiments/E60-preregistration.json"),
    )
    args = parser.parse_args()

    if args.out.exists():
        raise SystemExit(
            f"{args.out} already exists; a frozen pre-registration is not "
            "rewritten. Delete it deliberately if you intend to re-plan, and "
            "record why."
        )

    document = dict(PREREGISTRATION)
    document["preregistration_digest"] = digest_of(document)
    _atomic_json(args.out, document)
    print(f"froze {args.out}")
    print(f"digest {document['preregistration_digest']}")
    for prediction in document["predictions"]:
        print(f"  {prediction['id']}: {prediction['statement']}")


if __name__ == "__main__":
    main()
