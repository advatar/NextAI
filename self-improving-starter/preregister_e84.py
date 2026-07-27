"""Freeze the E84 plan: the properly powered test of the recursive effect.

Phase 3 has now been tested three times with inconsistent results, and the
inconsistency is the reason this plan exists:

    E81  null by maximum        best child 13/15 vs 14/15, p=1.000
    E82  null by expectation    mean 75.0% vs 77.5%
    E83  positive, underpowered mean 81.25% vs 68.75%, p=0.387

E82 diagnosed the first two nulls mechanically -- the descendant improver
produced ONE unique child text in five, pairwise similarity 1.00 -- and named
enforcing offspring diversity as the fix before E83 ran. E83 applied it and the
direction flipped as predicted, but with four children per arm the result sat
well inside noise.

Three tests of one question, with a protocol change before the positive, is how
false findings are manufactured. This freezes the design in advance and powers
it from a calculation rather than from what is convenient.

POWER. Detecting the E83 effect (0.6875 vs 0.8125, delta 0.125) at 80% power and
alpha 0.05 requires about 192 solver calls per arm by the standard
two-proportion approximation. The design is therefore 16 children per arm at 12
held-out samples each, which is exactly 192. E83 had 32.

The primary analysis, the statistic, and the threshold are all fixed here, so
there is no room to choose the favourable one afterwards.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from compare_selection import _atomic_json
from preregister_e60 import digest_of

PREREGISTRATION = {
    "schema_version": 1,
    "experiment_id": "E84-powered-recursive-effect",
    "follows": "E83-diverse-improver",
    "question": ("With offspring diversity enforced and the design powered in "
                 "advance, is the descendant a better improver than its "
                 "ancestor?"),
    "makes_capability_claim": True,
    "prior_tests": {
        "E81": "null by maximum, best child 13/15 vs 14/15, p=1.000",
        "E82": "null by expectation, mean 75.0% vs 77.5%",
        "E83": "positive but underpowered, 81.25% vs 68.75%, p=0.387, n=32/arm",
    },
    "multiplicity_disclosure": (
        "This is the FOURTH test of the same question and the second under the "
        "diversity-enforced protocol. E83's positive direction is what motivated "
        "powering the design, so E84 is confirmatory for a hypothesis generated "
        "by E83 and must not be read as independent of it. If E84 is null, the "
        "honest summary of all four is that no recursive effect was "
        "demonstrated."
    ),
    "power_calculation": {
        "target_rates": [0.6875, 0.8125],
        "target_delta": 0.125,
        "alpha": 0.05,
        "power": 0.80,
        "required_solver_calls_per_arm": 192,
        "design": "16 children per arm x 12 held-out samples = 192 per arm",
        "e83_had": 32,
    },
    "protocol": {
        "improver_arms": ["MINIMAL ancestor", "E80 promoted descendant"],
        "offspring_diversity": ("resample until 16 DISTINCT child texts per arm, "
                                "temperature 1.5, attempt cap 48"),
        "selection": ("none; every child is scored, so improvers are compared in "
                      "expectation as POC_PLAN's gain-per-cost criterion asks"),
        "evaluation": ("held-out seeds 101-120 on partition_feasible at "
                       "iteration budget 20000"),
        "matched_budget": "identical child count and sample count in both arms",
    },
    "primary_analysis": (
        "Fisher exact two-sided on pooled solver calls, ancestor versus "
        "descendant. Fixed in advance as the single primary test."
    ),
    "decision_rule": (
        "p < 0.05 with the descendant ahead is required to call a recursive "
        "effect observed. Anything else is reported as not demonstrated, "
        "including a positive direction that misses the threshold."
    ),
    "predictions": [
        {"id": "H1",
         "statement": ("The descendant's pooled solve rate exceeds the "
                       "ancestor's."),
         "basis": "E83 measured 81.25% vs 68.75% under this protocol."},
        {"id": "H2",
         "statement": "The primary test reaches p < 0.05.",
         "basis": ("The design is powered at 80% for the E83 effect size. If "
                   "the true effect is smaller, this fails and the effect is "
                   "not demonstrated.")},
        {"id": "H3",
         "statement": ("Both arms produce 16 distinct children within the "
                       "attempt cap."),
         "basis": ("E83 obtained four distinct children in four attempts per "
                   "arm at temperature 1.5. Sixteen is a stronger demand and "
                   "the descendant collapsed to one unique text at temperature "
                   "1.2 in E82, so this checks the mitigation holds at scale.")},
    ],
    "claim_boundary": (
        "One task family, one generation, one lineage per arm. Even a "
        "significant result is a single-lineage observation, short of "
        "POC_PLAN's three generations and five independent lineages with "
        "sealed transfer."
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path,
                        default=Path("experiments/E84-preregistration.json"))
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit(f"{args.out} exists; a frozen plan is not rewritten.")
    document = dict(PREREGISTRATION)
    document["preregistration_digest"] = digest_of(document)
    _atomic_json(args.out, document)
    print(f"froze {args.out}\ndigest {document['preregistration_digest']}")
    for p in document["predictions"]:
        print(f"  {p['id']}: {p['statement']}")


if __name__ == "__main__":
    main()
