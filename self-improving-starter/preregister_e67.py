"""Freeze the E67 plan: is the executable substrate ready for a search run?

E66 established that paired measurement works and admitted two tasks. Three
things changed afterwards, and this experiment is the gate that checks them
together.

1. **Paired scoring is now the default.** ``TimedTaskEnvironment`` calibrates a
   reference ratio at construction and scores candidates from a ratio against an
   adjacently measured anchor. ``anchored`` remains selectable only so
   ``compare_e66_paired_timing.py`` can still reproduce its unpaired arm.

2. **A third task, ``count_divisors``.** Two admitted tasks is thin, and both
   reward a single algebraic insight -- a closed form for ``optimize_function``,
   binary exponentiation for ``power_mod``. ``count_divisors`` is solved by
   bounding a loop at ``sqrt(n)`` instead of replacing it, with roughly 280x of
   headroom.

3. **An order-bias fix in the paired harness.** ``PAIRED_ROUNDS`` was 7. The
   order within a round alternates, so an odd count ran one ordering four times
   against the other's three. ``count_divisors`` exposed it at once: its anchor
   self-score, which must be 0.0 by definition because no candidate is involved,
   came out at +0.1059. The count is now even and both programs are warmed
   before the timed rounds. E66's recorded numbers were measured with the old
   harness; this experiment revalidates every task under the corrected one.

Disclosure: not blind. Scouting after the fix observed anchor self-scores near
zero for all three timed tasks and a reference of ~1.000. As before this measures
wall-clock time, so results are not bit-reproducible and the digest attests to
the recorded report. No capability claim is made under any outcome.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from compare_selection import _atomic_json
from preregister_e60 import digest_of

PREREGISTRATION = {
    "schema_version": 1,
    "experiment_id": "E67-substrate-readiness",
    "follows": "E66-paired-timing",
    "question": (
        "Under paired scoring as the default, with the order-bias fix and a "
        "third task, how many tasks can measure an improvement?"
    ),
    "makes_capability_claim": False,
    "tasks": [
        "optimize_function",
        "count_primes_v2",
        "power_mod",
        "count_divisors",
    ],
    "protocol": (
        "Paired measurement for every task. The three TimedTaskEnvironment "
        "tasks use it through their own score(), now the default; "
        "optimize_function is not a TimedTaskEnvironment and uses "
        "recursive_lab.paired_timing directly, as in E66."
    ),
    "revalidation_note": (
        "E66's numbers were measured with PAIRED_ROUNDS=7 and no warm-up. Every "
        "task is re-measured here under the corrected harness rather than "
        "carrying E66's figures forward."
    ),
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
        "null_variants_per_task": 10,
        "reference_probes_per_task": 5,
        "anchor_self_probes_per_task": 3,
        "best_of_k_values": [1, 2, 3, 5, 8],
        "bootstrap_samples": 20000,
        "primary_metric": "reward; 0.0 is the starting solution, 1.0 the reference",
    },
    "analysis_plan": {
        "primary": (
            "Per task: anchor self-score, null mean/sd, best-of-5, reference "
            "reward, monotonicity and signal-to-noise, judged against the frozen "
            "criteria."
        ),
        "readiness": (
            "The substrate is called ready for a governed search run only if at "
            "least three tasks are admitted. Fewer is reported as not ready."
        ),
        "no_capability_claim": (
            "Readiness licenses a search run; it is not evidence about one. No "
            "statement about scaffold or model improvement is made here."
        ),
        "null_handling": (
            "Findings are recorded as measured; no threshold is relaxed after "
            "seeing results."
        ),
    },
    "predictions": [
        {
            "id": "H1",
            "statement": "count_divisors is admitted.",
            "basis": "About 280x of headroom, comparable to power_mod's 669x.",
        },
        {
            "id": "H2",
            "statement": (
                "Every task's anchor self-score is within 0.05 of zero, "
                "confirming the order-bias fix."
            ),
            "basis": (
                "count_divisors scored +0.1059 with PAIRED_ROUNDS=7 and near "
                "zero after the fix."
            ),
        },
        {
            "id": "H3",
            "statement": "count_primes_v2 remains rejected.",
            "basis": (
                "Its headroom is 22-27x where the admitted tasks have hundreds. "
                "E64's H4 and E66 both found this, and pairing does not create "
                "headroom."
            ),
        },
        {
            "id": "H4",
            "statement": "At least three tasks are admitted.",
            "basis": (
                "E66 admitted optimize_function and power_mod under pairing; "
                "count_divisors should join them."
            ),
        },
        {
            "id": "H5",
            "statement": (
                "Every admitted task has a best-of-5 null reward that is "
                "positive but below 0.05."
            ),
            "basis": (
                "A maximum over noisy rewards is biased upward, so it cannot be "
                "zero; pairing should keep it small. If any admitted task shows "
                "a negative best-of-5 the null distribution is skewed and the "
                "phantom-gain baseline needs rethinking."
            ),
        },
    ],
    "claim_boundary": (
        "Readiness audit of the executable task substrate under paired scoring. "
        "Measures properties of reward functions only. Makes no claim about "
        "scaffold improvement, model self-improvement, or a recursive effect."
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E67-preregistration.json")
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
