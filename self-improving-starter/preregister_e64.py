"""Freeze the E64 plan before re-auditing the repaired executable substrate.

E63 admitted one task of three and left four concrete repairs. E64 tests whether
they worked, and closes the hole E63 found in its own criteria.

What was repaired
-----------------

``environments/timed_task.py`` provides a timing-scored base that fixes the
three defects E63 measured in ``count_primes``: anchors are medians of
calibrated repeat batches rather than one sample captured at import time; the
reward is unclamped per ``base.py``'s documented ``[<0, ~1+]`` contract, so noise
cancels instead of rectifying; and a held-out reference solution defines the 1.0
point.  ``count_primes_v2`` is that task rebuilt, and ``power_mod`` is a new
task whose optimum is an algorithm (binary exponentiation) rather than a closed
form.  The v1 environments are untouched so prior records stay interpretable.

The hole E63 left
-----------------

E63's four criteria all tested for the *absence of noise* and none for the
*presence of signal*, so a task whose reward function returned a constant would
have passed every one.  What actually established that ``optimize_function``
works was a separate unplanned check.  E64 adds two signal criteria: a known-good
reference solution must score at least ``minimum_reference_reward``, and the
separation between reference and null rewards must exceed
``minimum_signal_to_noise`` standard deviations of the null distribution.  A
constant reward function now fails on signal-to-noise, as it should.

Disclosure
----------

Not blind.  A smoke test of the two new environments observed anchors of 24x
speedup for ``count_primes_v2`` and 793x for ``power_mod``, and single null
variants scoring -0.233 and +0.080 respectively.  Those observations informed
the predictions below, in particular the negative prediction H4.  Stated so the
reader can discount them; the run uses fresh measurements at higher n.

As in E63 this measures wall-clock time, so the numbers are not bit-reproducible
and the report digest attests to the recorded report rather than to a
deterministic computation.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from compare_selection import _atomic_json
from preregister_e60 import digest_of

PREREGISTRATION = {
    "schema_version": 1,
    "experiment_id": "E64-repaired-substrate-audit",
    "follows": "E63-executable-substrate-audit",
    "question": (
        "Did the E63 repairs produce a reward that cannot be gamed by noise, "
        "and does the suite now contain more than one usable task?"
    ),
    "makes_capability_claim": False,
    "tasks": [
        "optimize_function",
        "count_primes",
        "count_primes_v2",
        "power_mod",
    ],
    "task_roles": {
        "optimize_function": "incumbent; the only task E63 admitted",
        "count_primes": (
            "control; the unrepaired v1, included so the before/after of the "
            "same task is measured in one run rather than across experiments"
        ),
        "count_primes_v2": "repaired rebuild of the control",
        "power_mod": "new task whose optimum is an algorithm, not a closed form",
    },
    "null_variant_definition": (
        "The environment's own starting_solution with a trailing comment "
        "appended. Semantically identical by construction, so any non-zero "
        "reward it earns is measurement artefact."
    ),
    "reference_probe_definition": (
        "Each repaired task's held-out reference solution, scored repeatedly. "
        "For optimize_function and count_primes, which expose no reference, the "
        "signal criteria are evaluated against a strong operator-written "
        "solution recorded in the runner."
    ),
    "admission_criteria": {
        "maximum_starting_solution_reward": 0.5,
        "maximum_null_variant_reward_sd": 0.05,
        "maximum_null_best_of_5_reward": 0.05,
        "maximum_absolute_null_reward_mean": 0.05,
        "minimum_reference_reward": 0.5,
        "minimum_signal_to_noise": 5.0,
    },
    "criteria_justification": (
        "The first three are E63's noise criteria. maximum_absolute_null_reward_"
        "mean replaces E63's rectification-bias probe with a direct statement of "
        "the property that matters: a semantically null change must score about "
        "zero, whatever the mechanism. The last two are the signal criteria E63 "
        "lacked; without them a constant reward function passes trivially. "
        "Signal-to-noise is (mean reference reward - mean null reward) divided "
        "by the null standard deviation, so it asks whether a real improvement "
        "is distinguishable from doing nothing."
    ),
    "instrument": {
        "null_variants_per_task": 30,
        "reference_probes_per_task": 10,
        "best_of_k_values": [1, 2, 3, 5, 8],
        "best_of_k_method": (
            "Bootstrap over the observed null-variant rewards: draw k with "
            "replacement, take the maximum, repeat 20000 times, report the mean."
        ),
        "bootstrap_samples": 20000,
        "primary_metric": "environment reward; 0.0 is the starting solution, 1.0 the reference",
    },
    "analysis_plan": {
        "primary": (
            "Per task: starting-solution reward, null-variant mean/sd, the "
            "best-of-k phantom gain curve, reference-probe mean, and "
            "signal-to-noise. Each task receives an admission verdict against "
            "the frozen criteria."
        ),
        "before_after": (
            "count_primes and count_primes_v2 are scored in the same run, so the "
            "effect of the repair is a within-run comparison rather than a "
            "cross-experiment one."
        ),
        "no_capability_claim": (
            "No statement about scaffold or model improvement will be made under "
            "any outcome. An admitted suite licenses future work; it is not a "
            "result."
        ),
        "null_handling": (
            "Findings are recorded as measured. A task that fails admission is "
            "reported as failing, not re-tuned until it passes."
        ),
    },
    "predictions": [
        {
            "id": "H1",
            "statement": (
                "count_primes_v2's best-of-5 null reward is lower than "
                "count_primes v1's, measured in the same run."
            ),
            "basis": (
                "v1 scored 0.254 in E63. Median anchors and an unclamped reward "
                "should both reduce what a best-of search can manufacture."
            ),
        },
        {
            "id": "H2",
            "statement": (
                "count_primes_v2's null reward mean is closer to zero than "
                "count_primes v1's."
            ),
            "basis": (
                "v1 measured +0.174, driven by a single stale reference and a "
                "floor at zero. Removing both should centre the null "
                "distribution."
            ),
        },
        {
            "id": "H3",
            "statement": "power_mod is admitted.",
            "basis": (
                "Its anchors differ by roughly 793x, so one reward unit is a "
                "large multiple of host timing jitter."
            ),
        },
        {
            "id": "H4",
            "statement": (
                "count_primes_v2 is NOT admitted: it fails the null noise floor "
                "despite the repair."
            ),
            "basis": (
                "Its anchors differ by only about 24x, so one reward unit is a "
                "small multiple of timing jitter. A smoke test saw a single null "
                "at -0.233. This predicts the repair is necessary but not "
                "sufficient, and that headroom magnitude is what decides "
                "usability."
            ),
        },
        {
            "id": "H5",
            "statement": (
                "Every admitted task has a signal-to-noise ratio of at least 5."
            ),
            "basis": (
                "Tautological for tasks admitted under the criteria, and "
                "therefore a check that the criterion is actually being applied "
                "rather than silently skipped when a task exposes no reference."
            ),
        },
    ],
    "claim_boundary": (
        "Instrument audit of the repaired executable task substrate. Measures "
        "properties of reward functions only. Makes no claim about scaffold "
        "improvement, model self-improvement, or a recursive effect."
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E64-preregistration.json")
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
