"""Freeze the E69 plan: a deterministic substrate, audited under replication.

E63-E68 spent ten experiments making a wall-clock speedup signal trustworthy on
a developer machine.  Every defect found was a timing defect -- saturation,
censoring, probe evasion, drift, order bias, repeat-count floors -- and each was
fixed and validated.  E68 is the verdict: **no task solid**, per-round null
standard deviations spanning 0.020 to 0.415 on the same task, and a single round
able to invert the ranking between the best and worst tasks in the suite.  The
remaining obstacle is not a harness defect but the machine itself.

E69 drops timing.  ``GradedCorrectnessEnvironment`` scores the share of hidden
cases a candidate answers correctly, normalised so the starting solution is 0.0
and a fully correct solution is 1.0.  Four tasks ship a plausible but incomplete
starting solution that fails a documented class of inputs.

A note on one criterion, because it looks like a relaxation and is not.

E64 and E65 established that an **undefined signal-to-noise ratio must fail**:
it is undefined exactly when the null spread is zero, and a reward clamped to a
constant produces exactly that.  ``count_primes`` v1 was admitted in E64 on
precisely this artefact.  A deterministic reward also has zero null spread, for
the opposite reason.

The discriminator is the **monotonicity probe**, and it already exists.  A
censored reward returns ~0.0 for a genuinely worse program -- that is how E65
caught ``count_primes`` v1, which scored +0.0000 for a program doing twice the
work.  An honest deterministic reward returns a clearly negative number.  So E69
admits an undefined ratio **only when** monotonicity is demonstrated and
determinism is separately verified by rescoring identical programs across
rounds.  Zero spread earns a pass by evidence, never by default.

Disclosure: not blind.  Scouting showed all four tasks scoring the anchor at
exactly +0.0000, the reference at exactly +1.0000, and a deliberate regression
between -0.55 and -2.75.  An earlier draft of ``collatz_steps`` had a starting
solution that never terminated on ``solve(0)``, which timed out the run and
scored 0/15; it was rewritten to terminate everywhere, and the episode is
recorded because a task that fails every case also makes negative rewards
impossible.  No capability claim is made under any outcome.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from compare_selection import _atomic_json
from preregister_e60 import digest_of

PREREGISTRATION = {
    "schema_version": 1,
    "experiment_id": "E69-deterministic-substrate",
    "follows": "E68-replicated-admission",
    "question": (
        "Does a deterministic graded-correctness reward produce tasks that are "
        "admissible under replication, where ten experiments of timing work did "
        "not?"
    ),
    "makes_capability_claim": False,
    "tasks": [
        "digit_sum_graded",
        "count_one_bits",
        "collatz_steps",
        "integer_sqrt",
    ],
    "reward_definition": (
        "(passed - starting_passed) / (total - starting_passed), unclamped, so "
        "the starting solution scores 0.0, a fully correct solution 1.0, and a "
        "candidate that breaks previously-passing cases scores negative."
    ),
    "classification": {
        "solid": "admitted in every round",
        "marginal": "admitted in some rounds but not all",
        "rejected": "admitted in no round",
    },
    "readiness_rule": (
        "Ready for a governed search run only if at least three tasks are SOLID. "
        "Marginal does not count."
    ),
    "admission_criteria": {
        "maximum_absolute_anchor_self_score": 0.0,
        "maximum_absolute_null_reward_mean": 0.0,
        "maximum_null_variant_reward_sd": 0.0,
        "maximum_null_best_of_5_reward": 0.0,
        "minimum_reference_reward": 1.0,
        "monotonicity_threshold": -0.05,
        "determinism_required": True,
        "minimum_headroom_cases": 4,
    },
    "criteria_notes": (
        "The noise thresholds are exactly zero rather than 0.05. A deterministic "
        "reward has no excuse for any spread at all, so anything above zero "
        "indicates a defect -- a nondeterministic environment, a timeout, or a "
        "leak -- rather than tolerable jitter. An undefined signal-to-noise "
        "ratio is accepted ONLY when the monotonicity probe scores below the "
        "threshold and determinism is verified; a censored reward fails "
        "monotonicity, which is how E65 caught count_primes v1."
    ),
    "instrument": {
        "rounds": 5,
        "null_variants_per_round": 8,
        "reference_probes_per_round": 2,
        "anchor_self_probes_per_round": 2,
        "determinism_probes_per_round": 3,
        "best_of_k_values": [1, 2, 3, 5, 8],
        "bootstrap_samples": 20000,
        "primary_metric": "share of hidden cases fixed, relative to the start",
    },
    "analysis_plan": {
        "primary": (
            "Per task per round: anchor self-score, null mean/sd, best-of-5, "
            "reference reward, monotonicity, determinism, and headroom. "
            "Classification by consistency across rounds, as in E68."
        ),
        "comparison": (
            "Best-of-5 phantom gain is reported against E68's timing figures "
            "(+0.018 to +0.325) to quantify what dropping the timing signal buys."
        ),
        "no_capability_claim": (
            "Readiness licenses a governed search run; it is not evidence about "
            "one."
        ),
        "null_handling": (
            "Recorded as measured; no threshold relaxed after seeing results."
        ),
    },
    "predictions": [
        {
            "id": "H1",
            "statement": "All four tasks are solid.",
            "basis": (
                "The reward is a deterministic function of the candidate, so "
                "there is no mechanism for a verdict to change between rounds."
            ),
        },
        {
            "id": "H2",
            "statement": (
                "Null standard deviation is exactly 0.0 in every round of every "
                "task."
            ),
            "basis": (
                "Null variants are semantically identical and the reward is "
                "deterministic. Any non-zero value would indicate a "
                "nondeterministic environment or a timeout, not jitter."
            ),
        },
        {
            "id": "H3",
            "statement": (
                "Best-of-5 phantom gain is exactly 0.0 for every task, against "
                "+0.018 to +0.325 for the timing tasks in E68."
            ),
            "basis": (
                "A maximum over identical values is that value, so a search "
                "proposing k no-op candidates gains nothing."
            ),
        },
        {
            "id": "H4",
            "statement": (
                "Every task's monotonicity probe scores below -0.05, "
                "establishing that the zero spread is determinism and not "
                "censoring."
            ),
            "basis": (
                "Scouting saw regressions between -0.55 and -2.75. This is the "
                "criterion that separates E69 from the E64 count_primes v1 "
                "artefact."
            ),
        },
        {
            "id": "H5",
            "statement": (
                "At least three tasks are solid, so the substrate is ready for a "
                "governed search run."
            ),
            "basis": (
                "Follows from H1. Stated separately because readiness is the "
                "decision this whole line of work has been trying to reach."
            ),
        },
    ],
    "claim_boundary": (
        "Readiness audit of a deterministic graded-correctness substrate. "
        "Measures properties of reward functions only. Makes no claim about "
        "scaffold improvement, model self-improvement, or a recursive effect. "
        "Measures correctness improvement, which is narrower than optimisation."
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E69-preregistration.json")
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
