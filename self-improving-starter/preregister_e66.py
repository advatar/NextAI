"""Freeze the E66 plan: does interleaved paired measurement fix the drift?

E65 established that the executable suite's timing rewards are dominated by
drift rather than independent jitter.  A task's starting solution is its own
anchor and must score exactly 0.0 by definition, yet it scored ``+0.2339`` on
``count_primes_v2`` and ``-0.1902`` on ``power_mod``.  Every environment captures
its anchor once at construction and scores candidates against it minutes later,
so machine state moves the whole reward scale.  E65 also ruled out the fix
proposed in E64: median-of-m reduced the spread by only 20% from m=1 to m=9,
because a median cannot cancel a trend common to all its samples.

``recursive_lab/paired_timing.py`` measures the anchor and the candidate
interleaved in a single process and reports the *ratio* ``t_candidate /
t_anchor``.  Multiplicative drift affecting the process scales both timings and
cancels.  The reward ``(1 - ratio) / (1 - reference_ratio)`` keeps the base.py
contract in drift-immune units.

Only the anchor is co-located with the candidate.  The starting solution is
public -- it is printed in the task prompt -- so sharing a process with candidate
code leaks nothing.  The held-out reference is calibrated separately against the
same anchor, also by paired measurement.

This experiment measures both protocols on the same tasks in the same run, so
the comparison is within-run rather than across experiments.  No capability
claim is made under any outcome.

Disclosure: not blind.  A scouting check of the paired protocol on ``power_mod``
observed null-variant rewards between -0.0276 and +0.0119, an anchor self-score
of +0.0004 and a reference of +1.0002.  Those informed the predictions.  As
before this measures wall-clock time, so results are not bit-reproducible and the
digest attests to the recorded report.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from compare_selection import _atomic_json
from preregister_e60 import digest_of

PREREGISTRATION = {
    "schema_version": 1,
    "experiment_id": "E66-paired-timing",
    "follows": "E65-censoring-proof-audit",
    "question": (
        "Does interleaved paired measurement remove the drift that made every "
        "task in the executable suite unable to measure an improvement?"
    ),
    "makes_capability_claim": False,
    "tasks": ["optimize_function", "count_primes_v2", "power_mod"],
    "task_note": (
        "count_primes v1 is excluded: the paired protocol replaces an "
        "environment's scoring entirely, so v1 and v2 would run identical "
        "programs. E65 already established v1's reward is censored."
    ),
    "arms": {
        "unpaired": (
            "the environment's own score(), whose anchor was captured once at "
            "construction — the protocol E63 through E65 audited"
        ),
        "paired": (
            "recursive_lab.paired_timing: anchor and candidate interleaved in "
            "one process, reward computed from the ratio"
        ),
    },
    "null_variant_definition": (
        "semantic_noop_variant: local bindings renamed with an index suffix. "
        "AST-distinct so identity checks cannot recognise it, semantically "
        "identical, and free at runtime."
    ),
    "anchor_self_score_note": (
        "Scoring the starting solution against itself is the sharpest single "
        "diagnostic: it must be 0.0 by definition, so any deviation is pure "
        "measurement error with no candidate involved."
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
        "best_of_k_values": [1, 2, 3, 5, 8],
        "bootstrap_samples": 20000,
        "paired_rounds": 7,
        "primary_metric": "reward; 0.0 is the starting solution, 1.0 the reference",
    },
    "analysis_plan": {
        "primary": (
            "For each task and each protocol: anchor self-score, null mean/sd, "
            "best-of-5, reference reward, signal-to-noise and monotonicity. "
            "Admission is judged per protocol against the frozen criteria."
        ),
        "within_run": (
            "Both protocols are measured in the same run on the same machine "
            "state, so the comparison does not inherit drift between "
            "experiments — which would be self-defeating for an experiment "
            "about drift."
        ),
        "no_capability_claim": (
            "No statement about scaffold or model improvement is made under any "
            "outcome. An admitted protocol licenses future work; it is not a "
            "result."
        ),
        "null_handling": (
            "Findings are recorded as measured; no threshold is relaxed after "
            "seeing results."
        ),
    },
    "predictions": [
        {
            "id": "H1",
            "statement": (
                "Under the paired protocol every task's anchor self-score is "
                "within 0.05 of zero."
            ),
            "basis": (
                "Unpaired it was +0.2339 and -0.1902. A ratio against an "
                "adjacently measured anchor should be 1.0 up to residual noise. "
                "Scouting saw +0.0004 on power_mod."
            ),
        },
        {
            "id": "H2",
            "statement": (
                "For every task, paired null sd is lower than unpaired null sd."
            ),
            "basis": "Removing a common-mode term cannot increase the spread.",
        },
        {
            "id": "H3",
            "statement": (
                "Under the paired protocol every task's null reward mean is "
                "within 0.05 of zero."
            ),
            "basis": (
                "Drift is what pushed the unpaired null means to +0.1493 "
                "(optimize_function) and -0.0911 (power_mod)."
            ),
        },
        {
            "id": "H4",
            "statement": "At least one task is admitted under the paired protocol.",
            "basis": (
                "power_mod already had the best signal-to-noise in the suite and "
                "failed only on drift-driven criteria."
            ),
        },
        {
            "id": "H5",
            "statement": (
                "No task is admitted under the unpaired protocol, reproducing "
                "E65 within this run."
            ),
            "basis": (
                "Same protocol, same machine. If this fails, E65's rejections "
                "were themselves unstable and the whole comparison is suspect."
            ),
        },
    ],
    "claim_boundary": (
        "Measurement-protocol comparison on the executable task substrate. "
        "Measures properties of reward functions only. Makes no claim about "
        "scaffold improvement, model self-improvement, or a recursive effect."
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E66-preregistration.json")
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
