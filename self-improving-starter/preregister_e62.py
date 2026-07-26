"""Freeze the E62 analysis plan before the promotion-objective comparison.

E59 and E60 both selected a router by **worst-family mean regret**, an objective
adopted without ever being compared against alternatives.  E61 showed what that
costs: on ``monotone``, the only family with a large real effect, E41's older
``R^2 >= 0.5`` gate scored -0.01967 while E60's worst-family-selected router
scored -0.00625.  Worst-family selection picked a router that is mediocre
everywhere over one that is excellent where signal exists.

E62 compares three selection objectives on identical training data and evaluates
each selected router on **two disjoint held-out seed blocks**.

Two disjoint blocks, not one
----------------------------

E60's ``rugged`` regression cleared a 95% interval and then evaporated on fresh
seeds in E61; E59's ``monotone`` magnitude also moved substantially.  Single
cohort intervals in this benchmark are not trustworthy on their own.  This plan
therefore makes replication structural: every effect is measured independently
on block A and block B, and an effect is only called a **result** if both blocks
agree in sign, both intervals exclude zero, and both point estimates clear the
minimum effect size.  Anything else is reported as unreplicated.

The yardstick problem
---------------------

There is no neutral scoreboard here.  Scoring the three objectives by macro-mean
regret would hand the win to the macro-mean objective by construction, and
scoring by worst-family regret would do the same for worst-family.  Both
yardsticks are therefore reported for every selected router, and the
pre-registered question is deliberately not "which objective wins" but:

    Does any objective generalise -- scoring well on a yardstick it was not
    selected for -- and does worst-family selection give up a large, replicated
    advantage on the families that carry signal?

An objective that only wins on its own metric has demonstrated nothing.

Seeds 2000-2119 (train), 3000-3119 (block A) and 4000-4119 (block B) are
disjoint from each other and from E59/E60 (0-239) and E61 (1000-1239).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from compare_selection import _atomic_json
from preregister_e60 import digest_of

PREREGISTRATION = {
    "schema_version": 1,
    "experiment_id": "E62-promotion-objective",
    "follows": "E61-rugged-ablation",
    "question": (
        "Does any promotion objective generalise beyond the yardstick it was "
        "selected for, and does worst-family selection give up a replicated "
        "advantage on the families that carry signal?"
    ),
    "criteria": {
        "maximum_exploration_target_rate": 0.2,
        "minimum_tasks": 5,
        "minimum_policy_disagreements": 3,
        "minimum_policy_disagreement_rate": 0.2,
    },
    "minimum_effect_size": 0.005,
    "replication_rule": (
        "An effect is a result only if block A and block B agree in sign, both "
        "95% bootstrap intervals exclude zero, and both point estimates clear "
        "the minimum effect size. Agreement in one block only is reported as "
        "unreplicated and is not counted as a finding."
    ),
    "instrument": {
        "module": "recursive_lab.scaled_landscape",
        "grid_size": 128,
        "exploration_per_column": 3,
        "train_seeds": 120,
        "train_seed_start": 2000,
        "block_a_seed_start": 3000,
        "block_b_seed_start": 4000,
        "block_seeds": 120,
        "seed_disjointness": (
            "E59/E60 used 0-239 and E61 used 1000-1239. E62 uses 2000-2119 for "
            "selection and 3000-3119 / 4000-4119 for the two held-out blocks, "
            "all mutually disjoint."
        ),
        "primary_metric": "regret (1.0 - best_score); lower is better",
    },
    "objectives": {
        "worst_family": (
            "minimise the worst admitted family's mean regret; the objective "
            "E59 and E60 used without comparison"
        ),
        "macro_mean": "minimise the unweighted mean regret across admitted families",
        "signal_weighted": (
            "minimise mean regret weighted by each family's policy-disagreement "
            "rate, so families where policies can barely differ contribute "
            "little. The weights come from the admission sweep and are a "
            "property of the cohort, never of the candidate under test."
        ),
    },
    "yardsticks": [
        "macro_mean_regret",
        "worst_family_regret",
    ],
    "analysis_plan": {
        "primary": (
            "For each selected router, the paired regret delta against the "
            "random baseline per family, computed independently on block A and "
            "block B, with 95% bootstrap intervals. The replication rule decides "
            "what counts as a result."
        ),
        "generalisation": (
            "Each selected router is scored on BOTH yardsticks on both blocks. "
            "An objective is said to generalise only if it is competitive on the "
            "yardstick it was not selected for."
        ),
        "no_single_winner_claim": (
            "No claim of the form 'objective X is best' will be made from a "
            "single yardstick, since each objective is advantaged on its own."
        ),
        "null_handling": (
            "Null and inconclusive results are recorded as measured and are not "
            "re-run, re-seeded, or re-thresholded, per POC_PLAN.md."
        ),
    },
    "predictions": [
        {
            "id": "H1",
            "statement": "The three objectives do not all select the same router.",
            "basis": (
                "worst-family is maximin and macro-mean is an average; E61 showed "
                "they disagree sharply on monotone."
            ),
        },
        {
            "id": "H2",
            "statement": (
                "The worst-family-selected router is beaten on macro-mean regret "
                "by at least one other objective's router, on both blocks."
            ),
            "basis": (
                "E61 measured a threefold gap on monotone between E41's gate and "
                "E60's worst-family selection."
            ),
        },
        {
            "id": "H3",
            "statement": (
                "At least one objective selects a router with an R^2 threshold "
                "of 0.5 or higher, i.e. a genuinely support-aware gate."
            ),
            "basis": (
                "E41's (0.5, 0.01) gate dominated on monotone in E61, so an "
                "objective that rewards signal should recover something like it."
            ),
        },
        {
            "id": "H4",
            "statement": (
                "The ranking of the three selected routers by macro-mean regret "
                "is identical on block A and block B."
            ),
            "basis": (
                "A stability check on the methodology itself. If two disjoint "
                "blocks disagree on the ranking, single-block selection in this "
                "benchmark is unsound and the replication rule is load-bearing."
            ),
        },
        {
            "id": "H5",
            "statement": (
                "At least one per-family effect clears in one block and fails to "
                "replicate in the other."
            ),
            "basis": (
                "Speculative, and a direct test of whether the replication rule "
                "earns its cost. E60's rugged result behaved exactly this way "
                "across E60 and E61."
            ),
        },
    ],
    "claim_boundary": (
        "Synthetic landscape comparison of three selection objectives for one "
        "exploitation rule. Not evidence about model self-improvement or a "
        "recursive effect."
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E62-preregistration.json")
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
