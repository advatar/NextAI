"""Freeze the E61 analysis plan before the ablation is run.

E60 found that the promoted router *harms* the ``rugged`` family on held-out
seeds: paired regret delta +0.00836, 95% CI [+0.00167, +0.01533], an interval
excluding zero on the wrong side.  That is the first demonstrably harmful
promotion in the series, and the saturated 5x5 instrument could never have shown
it.

E61 asks why, with a causal ablation.  ``surrogate_choice`` *always* returns one
end of a column's unseen range, so a surrogate router does two separable things
at once:

1. it **narrows** exploitation to the two ends of each column, and
2. it uses the fitted line to **choose** between those two ends.

On ``rugged`` -- a hash-derived surface where a three-point linear fit carries no
signal -- step 2 is worthless, but step 1 still restricts the search to two
horizontal bands.  The ``endpoint_coinflip`` control fires on exactly the same
condition and also always lands on an endpoint, but picks between the two ends
by coin flip, ignoring the fit.  Comparing the two separates "narrowing hurt"
from "following a meaningless fit hurt".

This experiment also introduces the **minimum effect size** criterion recorded as
outstanding in E60, where ``curved`` produced an interval excluding zero around
an effect of -0.00003 -- statistically real, practically meaningless.

Disclosure: the 0.005 floor was chosen with E60's magnitudes already visible, so
it is not blind.  It is stated here, applied prospectively to E61, and the reader
should discount it accordingly.  Seeds are disjoint from E59 and E60.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from compare_selection import _atomic_json
from preregister_e60 import digest_of

PREREGISTRATION = {
    "schema_version": 1,
    "experiment_id": "E61-rugged-ablation",
    "follows": "E60-corrected-admission",
    "question": (
        "Why does the E60-promoted router increase regret on the rugged family, "
        "and is the cause endpoint narrowing or fit-following?"
    ),
    "criteria": {
        "maximum_exploration_target_rate": 0.2,
        "minimum_tasks": 5,
        "minimum_policy_disagreements": 3,
        "minimum_policy_disagreement_rate": 0.2,
    },
    "minimum_effect_size": 0.005,
    "minimum_effect_size_justification": (
        "An interval excluding zero is reported as a result only if the point "
        "estimate also clears 0.005 in regret units, i.e. 0.5% of the metric's "
        "[0, 1] range. E60's curved family cleared significance with an effect "
        "of -0.00003, three orders of magnitude below anything that changes a "
        "best-found score meaningfully. Chosen with E60's magnitudes visible and "
        "therefore not blind; applied prospectively here."
    ),
    "instrument": {
        "module": "recursive_lab.scaled_landscape",
        "grid_size": 128,
        "exploration_per_column": 3,
        "seeds": 240,
        "seed_start": 1000,
        "seed_disjointness": (
            "E59 and E60 used seeds 0-239. E61 uses 1000-1239, so the rugged "
            "replication is on genuinely fresh landscapes."
        ),
        "primary_metric": "regret (1.0 - best_score); lower is better",
    },
    "families": ["rugged", "monotone"],
    "family_roles": {
        "rugged": "the regression under investigation; fit carries no signal",
        "monotone": (
            "positive control; fit carries real signal, so fit-following should "
            "help here if the ablation is measuring what it claims to"
        ),
    },
    "arms": {
        "random": "(1.01, 0.0) surrogate mode; never fires, uniform over unseen",
        "e60_promoted": "(0.0, 0.03) surrogate mode; the harmful router from E60",
        "endpoint_control": (
            "(0.0, 0.03) endpoint_coinflip mode; identical firing rule, lands on "
            "an endpoint, but ignores the fit"
        ),
        "e41_gate": "(0.5, 0.01) surrogate mode; the support-aware gate",
    },
    "analysis_plan": {
        "primary": (
            "Per-family paired regret delta of each arm against the random "
            "baseline, on shared seeds, with 95% bootstrap intervals. An arm is "
            "called a result only if its interval excludes zero AND its point "
            "estimate clears the minimum effect size."
        ),
        "decomposition": (
            "The paired difference (e60_promoted - endpoint_control), with its "
            "own bootstrap interval, isolates the fit-following component. If it "
            "spans zero on rugged, the harm is attributable to endpoint "
            "narrowing rather than to following a meaningless fit."
        ),
        "null_handling": (
            "Null and inconclusive results are recorded as measured and are not "
            "re-run, re-seeded, or re-thresholded, per POC_PLAN.md."
        ),
    },
    "predictions": [
        {
            "id": "H1",
            "statement": (
                "The rugged regression replicates on fresh seeds: e60_promoted "
                "has a positive delta whose interval excludes zero and whose "
                "magnitude clears the minimum effect size."
            ),
            "basis": "E60 measured +0.00836, CI [+0.00167, +0.01533].",
        },
        {
            "id": "H2",
            "statement": (
                "endpoint_control also harms rugged: positive delta, interval "
                "excluding zero."
            ),
            "basis": (
                "If narrowing to two bands is the mechanism, discarding the fit "
                "entirely should not rescue it."
            ),
        },
        {
            "id": "H3",
            "statement": (
                "On rugged the difference (e60_promoted - endpoint_control) has "
                "an interval spanning zero, i.e. the harm is endpoint narrowing "
                "and not fit-following."
            ),
            "basis": (
                "A three-point linear fit on a hash-derived surface should carry "
                "no usable signal, so following it should be no worse than a coin "
                "flip between the same two cells."
            ),
        },
        {
            "id": "H4",
            "statement": (
                "On monotone, e60_promoted has a clearly lower regret than "
                "endpoint_control, with the difference interval excluding zero."
            ),
            "basis": (
                "Positive control. Where the fit carries signal, choosing the "
                "predicted-higher end must beat a coin flip, otherwise the "
                "ablation is not measuring fit-following at all."
            ),
        },
        {
            "id": "H5",
            "statement": (
                "On rugged, e41_gate causes strictly less harm than "
                "e60_promoted (smaller positive delta)."
            ),
            "basis": (
                "e41_gate requires R^2 >= 0.5 before firing, so it should decline "
                "to exploit on a signal-free surface far more often. Speculative: "
                "a spurious fit on three points may clear 0.5 more easily than "
                "expected."
            ),
        },
    ],
    "claim_boundary": (
        "Synthetic landscape ablation of one exploitation rule. Explains a "
        "measured regression in this benchmark; not evidence about model "
        "self-improvement or a recursive effect."
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E61-preregistration.json")
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
