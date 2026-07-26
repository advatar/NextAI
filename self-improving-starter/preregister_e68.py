"""Freeze the E68 plan: replicate admission verdicts instead of taking one.

E62 made replication structural for *effects* -- two disjoint blocks, agreement
required -- after E60's ``rugged`` regression evaporated in E61.  That rule was
never applied to *admission verdicts*, which are equally threshold-crossing
decisions taken from a single noisy sample.

E67 showed the cost.  ``power_mod`` was admitted in E66 at a best-of-5 null
reward of +0.0261 and rejected in E67 at +0.0533, against a 0.05 bar.  Neither
run is wrong; the task sits on the threshold.  E66's headline "two tasks
admitted" was itself an unreplicated single-run claim, and one of the two did not
hold.

E68 runs the whole admission audit K times and classifies each task by how often
it is admitted:

* **solid** -- admitted in every round;
* **marginal** -- admitted in some rounds and not others;
* **rejected** -- admitted in no round.

Only *solid* tasks count toward readiness.  A marginal task is not a
half-admitted task; it is a task whose verdict is not yet a measurement.

Two other changes are folded in and revalidated here.

``gcd_fixed`` is added: greatest common divisor against a fixed constant, solved
by the Euclidean algorithm.  It probes an insight the suite lacks -- the naive
loop is *replaced* rather than bounded or recalled.

``MIN_TIMING_REPEATS`` is added to the paired harness.  An elapsed-time target
alone is insufficient: a task whose single call exceeds the target calibrates to
one or two repeats, so each batch is effectively a single measurement.
``gcd_fixed`` hit this at once -- roughly 7 ms per call gave 2-3 repeats and two
*identical* programs measured ratios from 1.00 to 1.48, an anchor self-score of
+0.5058 where 0.0 is the definition.  Its timing argument was also reduced from
120_000 to 20_000 so a naive call costs about a millisecond; Euclid is O(log n),
so almost no headroom is lost.  E67's figures predate both changes, so every task
is re-measured here.

Disclosure: not blind, and deliberately pessimistic.  Scouting after the fixes
still saw anchor self-scores of +0.0545/-0.1393/-0.0151/-0.0681 for
``gcd_fixed`` and -0.0723/-0.0170/-0.1225/+0.1000 for ``power_mod`` while the
machine was busy with other probes, which is why several predictions below
expect instability rather than admission.  Wall-clock measurement is not
bit-reproducible; the digest attests to the recorded report.  No capability claim
is made under any outcome.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from compare_selection import _atomic_json
from preregister_e60 import digest_of

PREREGISTRATION = {
    "schema_version": 1,
    "experiment_id": "E68-replicated-admission",
    "follows": "E67-substrate-readiness",
    "question": (
        "When admission is replicated rather than taken from one run, which "
        "tasks hold up?"
    ),
    "makes_capability_claim": False,
    "tasks": [
        "optimize_function",
        "count_primes_v2",
        "power_mod",
        "count_divisors",
        "gcd_fixed",
    ],
    "classification": {
        "solid": "admitted in every round",
        "marginal": "admitted in some rounds but not all",
        "rejected": "admitted in no round",
    },
    "readiness_rule": (
        "The substrate is ready for a governed search run only if at least three "
        "tasks are SOLID. Marginal tasks do not count: a verdict that changes "
        "between runs is not yet a measurement."
    ),
    "corrections_revalidated_here": [
        "MIN_TIMING_REPEATS floor in the paired harness",
        "gcd_fixed timing argument reduced from 120_000 to 20_000",
        "correctness gating added to the optimize_function paired scorer, which "
        "in E67 measured timing without checking the candidate was correct",
    ],
    "admission_criteria": {
        "maximum_absolute_anchor_self_score": 0.05,
        "maximum_absolute_null_reward_mean": 0.05,
        "maximum_null_variant_reward_sd": 0.05,
        "maximum_null_best_of_5_reward": 0.05,
        "minimum_reference_reward": 0.5,
        "minimum_signal_to_noise": 5.0,
        "monotonicity_threshold": -0.05,
    },
    "instrument": {
        "rounds": 5,
        "null_variants_per_round": 8,
        "reference_probes_per_round": 3,
        "anchor_self_probes_per_round": 2,
        "best_of_k_values": [1, 2, 3, 5, 8],
        "bootstrap_samples": 20000,
        "primary_metric": "reward; 0.0 is the starting solution, 1.0 the reference",
    },
    "analysis_plan": {
        "primary": (
            "Per task: the admission verdict in each of K rounds, the resulting "
            "classification, and the per-round criterion values so an instability "
            "can be attributed to a specific criterion."
        ),
        "no_capability_claim": (
            "Readiness licenses a search run; it is not evidence about one."
        ),
        "null_handling": (
            "Findings are recorded as measured; no threshold is relaxed after "
            "seeing results, and a marginal task is never rounded up to admitted."
        ),
    },
    "predictions": [
        {
            "id": "H1",
            "statement": (
                "At least one task is marginal — admitted in some rounds and not "
                "others."
            ),
            "basis": (
                "The central methodological claim. power_mod already disagreed "
                "between E66 and E67. If nothing is marginal, single-run "
                "admission was adequate after all and this experiment is "
                "unnecessary."
            ),
        },
        {
            "id": "H2",
            "statement": "power_mod is marginal.",
            "basis": "Admitted in E66 at +0.0261, rejected in E67 at +0.0533.",
        },
        {
            "id": "H3",
            "statement": "count_primes_v2 is rejected in every round.",
            "basis": (
                "28x headroom against hundreds for the others; rejected in E64, "
                "E65, E66 and E67."
            ),
        },
        {
            "id": "H4",
            "statement": "optimize_function is solid.",
            "basis": (
                "8740x headroom, and the widest margin on every criterion in E67."
            ),
        },
        {
            "id": "H5",
            "statement": (
                "Fewer than three tasks are solid, so the substrate is still not "
                "ready."
            ),
            "basis": (
                "Pessimistic. Scouting saw anchor self-scores beyond 0.05 for "
                "both gcd_fixed and power_mod under load. If this is wrong the "
                "substrate is in better shape than expected."
            ),
        },
    ],
    "claim_boundary": (
        "Replicated readiness audit of the executable task substrate. Measures "
        "properties of reward functions only. Makes no claim about scaffold "
        "improvement, model self-improvement, or a recursive effect."
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E68-preregistration.json")
    )
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit(f"{args.out} already exists; a frozen plan is not rewritten.")
    document = dict(PREREGISTRATION)
    document["preregistration_digest"] = digest_of(document)
    _atomic_json(args.out, document)
    print(f"froze {args.out}")
    print(f"digest {document['preregistration_digest']}")
    for prediction in document["predictions"]:
        print(f"  {prediction['id']}: {prediction['statement']}")


if __name__ == "__main__":
    main()
