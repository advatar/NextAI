"""Freeze the E65 plan: a censoring-proof audit with a median-of-m protocol.

E63 and E64 both admitted ``optimize_function`` on a null-variant probe of "the
starting solution with a comment appended".  That environment compares programs
by ``ast.dump``, so a comment is invisible to it and the variant was recognised
as the *same program*, returning exactly 0.0 every time by design.  Both audits
read a string of exact zeros as a perfect noise profile.  It was neither
precision nor censoring: **the probe was evaded**.  A scouting check with an
AST-distinct no-op (a renamed local) produced rewards from -0.29 to +0.05 on the
same task.

So the two experiments that were supposed to establish whether the substrate can
measure anything were themselves mismeasured, and the single task they admitted
is the one that defeated the instrument.  E65 re-runs the audit with three
corrections.

1. **Undetectable null probes.**  ``semantic_noop_variant`` renames local
   bindings.  The program is AST-distinct, so identity checks cannot recognise
   it, and it performs exactly the same computation with no added runtime work.

2. **A monotonicity probe.**  Zero spread from a clamp looks identical to zero
   spread from precision, which is why E64 admitted ``count_primes`` v1 -- the
   task E63 rejected as worst.  Scoring a correct-but-deliberately-slower program
   separates them: an honest reward goes clearly negative, a censored one stays
   at zero.  An undefined signal-to-noise ratio now fails rather than being
   skipped, which is the bug that shipped in E64's H5 grading.

3. **A median-of-m scoring protocol.**  Best-of-k phantom gain is intrinsic to
   taking a maximum over any noisy reward and cannot be engineered out of an
   environment.  Scoring a candidate as the median of m evaluations shrinks the
   spread by roughly sqrt(m).  E65 measures the whole curve rather than asserting
   it: each null variant is evaluated m_max times once, and median-of-m is
   computed by subsampling those measurements.

Disclosure: not blind.  A scouting check observed optimize_function scoring
-0.2110, +0.0000, +0.0516, +0.0308, -0.2901 on AST-distinct no-ops, and E64's
recorded numbers are known.  Both informed the predictions.  As before this
measures wall-clock time, so results are not bit-reproducible and the digest
attests to the recorded report.

No capability claim is made under any outcome.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from compare_selection import _atomic_json
from preregister_e60 import digest_of

PREREGISTRATION = {
    "schema_version": 1,
    "experiment_id": "E65-censoring-proof-audit",
    "follows": "E64-repaired-substrate-audit",
    "question": (
        "With an undetectable null probe, a censoring check, and a median-of-m "
        "protocol, which tasks can actually measure an improvement?"
    ),
    "makes_capability_claim": False,
    "corrects": (
        "E63 and E64 admitted optimize_function on a comment-appended null "
        "variant that the environment recognised as the same program by AST "
        "identity, returning exact zeros by design. Those admissions rest on a "
        "probe artefact and are superseded here."
    ),
    "tasks": ["optimize_function", "count_primes", "count_primes_v2", "power_mod"],
    "null_variant_definition": (
        "semantic_noop_variant: local bindings renamed with an index suffix. "
        "AST-distinct so identity checks cannot recognise it, semantically "
        "identical, and free at runtime."
    ),
    "monotonicity_probe_definition": (
        "A correct program that performs the same computation twice and returns "
        "the second result, so it is roughly 2x slower. An honest reward must "
        "score it at or below the monotonicity threshold."
    ),
    "admission_criteria": {
        "maximum_starting_solution_reward": 0.5,
        "monotonicity_threshold": -0.05,
        "maximum_absolute_null_reward_mean": 0.05,
        "maximum_null_variant_reward_sd": 0.05,
        "maximum_null_best_of_5_reward": 0.05,
        "minimum_reference_reward": 0.5,
        "minimum_signal_to_noise": 5.0,
    },
    "criteria_notes": (
        "Signal-to-noise must be DEFINED to pass; an undefined ratio is a "
        "failure, not a skip. E64's grader treated undefined as passing and so "
        "performed the silent skip its own prediction existed to detect. The "
        "noise criteria are evaluated at the reported protocol_repeats, since "
        "median-of-m is part of the scoring protocol rather than a post-hoc "
        "adjustment."
    ),
    "instrument": {
        "null_variants_per_task": 10,
        "measurements_per_variant": 9,
        "median_of_m_values": [1, 3, 5, 9],
        "protocol_repeats": 9,
        "reference_probes_per_task": 5,
        "best_of_k_values": [1, 2, 3, 5, 8],
        "bootstrap_samples": 20000,
        "primary_metric": "environment reward; 0.0 is the starting solution, 1.0 the reference",
    },
    "analysis_plan": {
        "primary": (
            "Per task: the monotonicity verdict, the null mean/sd and best-of-5 "
            "at each median-of-m level, the reference reward, and signal-to-"
            "noise. Admission is judged at protocol_repeats."
        ),
        "m_curve": (
            "Null sd is reported at m = 1, 3, 5, 9 to show whether averaging "
            "actually buys precision, rather than assuming the sqrt(m) rule."
        ),
        "no_capability_claim": (
            "No statement about scaffold or model improvement is made under any "
            "outcome."
        ),
        "null_handling": (
            "Findings are recorded as measured. A task that fails is reported as "
            "failing, not re-tuned until it passes, and no threshold is relaxed "
            "after seeing results."
        ),
    },
    "predictions": [
        {
            "id": "H1",
            "statement": (
                "optimize_function's null sd at m=1 exceeds 0.05, contradicting "
                "the 0.0000 recorded in E64."
            ),
            "basis": (
                "A scouting check with AST-distinct no-ops spanned -0.29 to "
                "+0.05. E64's zeros came from AST-identity detection, not from "
                "precision."
            ),
        },
        {
            "id": "H2",
            "statement": (
                "count_primes v1 fails the monotonicity probe: a roughly 2x "
                "slower program still scores above -0.05."
            ),
            "basis": (
                "Its reward is clamped with max(0.0, ...), so anything slower "
                "than the captured baseline floors to exactly zero."
            ),
        },
        {
            "id": "H3",
            "statement": (
                "count_primes_v2 and power_mod both pass the monotonicity probe."
            ),
            "basis": "Their shared base class does not clamp.",
        },
        {
            "id": "H4",
            "statement": (
                "For power_mod, null sd at m=9 is at most half its value at m=1."
            ),
            "basis": (
                "Median-of-m should shrink spread by roughly sqrt(9) = 3; half "
                "is a conservative bar."
            ),
        },
        {
            "id": "H5",
            "statement": (
                "At the protocol repeats, power_mod is admitted and "
                "count_primes v1 is not — reversing E64's verdicts for both."
            ),
            "basis": (
                "power_mod had the best signal-to-noise in E64 and failed only "
                "on best-of-5, which averaging should fix; count_primes v1 was "
                "admitted only because censoring hid its noise."
            ),
        },
    ],
    "claim_boundary": (
        "Instrument audit of the executable task substrate under corrected "
        "probes. Measures properties of reward functions only. Makes no claim "
        "about scaffold improvement, model self-improvement, or a recursive "
        "effect."
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E65-preregistration.json")
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
