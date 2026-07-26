"""Freeze the E63 analysis plan before auditing the executable substrate.

E59-E62 rebuilt the synthetic benchmark until it could measure something. The
recommended next move is the executable task substrate in ``environments/``,
which cannot saturate the way a 5x5 grid did, and where a result would say
something about coding agents rather than about score tables.

The lesson of E51 is to audit an instrument *before* building on it, so this
experiment makes no capability claim at all. It asks one question: can the
executable suite measure an improvement, and would a search loop running on it
be measuring anything real?

Three specific hazards are probed, all of them properties of the reward
function rather than of any candidate:

1. **Ceiling.** A task whose shipped starting solution already scores the
   maximum has no headroom, exactly as the 5x5 grid had none.

2. **Noise floor.** ``count_primes`` and ``optimize_function`` reward a speedup,
   so their reward inherits wall-clock timing noise. If re-scoring a
   *semantically identical* program moves the reward by more than the effects
   worth detecting, single measurements cannot support a claim.

3. **Rectified noise.** Both timing rewards are clamped with
   ``max(0.0, ...)``. Clamping censors the negative half of a symmetric noise
   distribution, so a change that does nothing can still earn a positive
   expected reward. Worse, a search that proposes k null variants and keeps the
   best is taking a maximum over noise, which grows with k. That is a phantom
   improvement available to any optimiser for free, and it is precisely the
   failure mode that would make a self-improvement result spurious.

Null variants are the tool throughout: the starting solution with a trailing
comment appended. They are semantically identical, so every non-zero reward they
earn is measurement artefact by construction.

Disclosure: this plan is not blind. A scouting probe with n=12 on
``count_primes`` observed a null-variant reward spread of 0.188 and a
clamped-versus-unclamped mean difference near 0.18, and those observations
informed both the thresholds and the predictions below. They are stated here so
the reader can discount them, and the run uses fresh measurements at higher n.

Reproducibility: unlike E59-E62 this experiment measures wall-clock time, so its
numbers are not bit-reproducible across machines or runs. The report digest
attests to the recorded report, not to a deterministic computation.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from compare_selection import _atomic_json
from preregister_e60 import digest_of

PREREGISTRATION = {
    "schema_version": 1,
    "experiment_id": "E63-executable-substrate-audit",
    "follows": "E62-promotion-objective",
    "question": (
        "Does the executable task substrate have measurement headroom, and is "
        "its reward trustworthy enough to support a search loop?"
    ),
    "makes_capability_claim": False,
    "tasks": ["optimize_function", "count_primes", "sum_digits"],
    "null_variant_definition": (
        "The environment's own starting_solution with a trailing comment "
        "appended. Semantically identical by construction, so any non-zero "
        "reward it earns is measurement artefact. The comment is required "
        "because count_primes special-cases an exact textual match against the "
        "starting solution and returns 0.0 for it."
    ),
    "admission_criteria": {
        "maximum_starting_solution_reward": 0.5,
        "maximum_null_variant_reward_sd": 0.05,
        "maximum_null_best_of_5_reward": 0.05,
        "maximum_absolute_rectification_bias": 0.05,
    },
    "criteria_justification": (
        "A task is admitted only if its shipped starting solution is not "
        "already near the ceiling, if re-scoring an identical program is stable "
        "to within 0.05 of a [0, 1] reward scale, if a five-sample best-of "
        "search over null variants cannot manufacture more than 0.05 of reward, "
        "and if clamping does not shift the expected reward of a null change by "
        "more than 0.05. All four are properties of the reward function alone."
    ),
    "instrument": {
        "null_variants_per_task": 40,
        "best_of_k_values": [1, 2, 3, 5, 8],
        "best_of_k_method": (
            "Bootstrap over the observed null-variant rewards: draw k with "
            "replacement, take the maximum, repeat 20000 times, report the mean. "
            "This estimates what a search keeping the best of k no-op proposals "
            "would score."
        ),
        "bootstrap_samples": 20000,
        "primary_metric": "environment reward, nominally [0, 1]",
    },
    "analysis_plan": {
        "primary": (
            "Per task: starting-solution reward, null-variant reward mean and "
            "standard deviation, the clamped-minus-unclamped rectification bias "
            "where the raw metric is available, and the best-of-k phantom gain "
            "curve. Each task receives an admission verdict against the frozen "
            "criteria."
        ),
        "no_capability_claim": (
            "No statement about scaffold or model improvement will be made from "
            "this experiment under any outcome. A fully admitted suite would "
            "license future work, not constitute a result."
        ),
        "null_handling": (
            "Findings are recorded as measured. A suite that fails admission is "
            "reported as failing, not re-tuned until it passes."
        ),
    },
    "predictions": [
        {
            "id": "H1",
            "statement": (
                "sum_digits is rejected on the ceiling criterion: its starting "
                "solution already scores the maximum reward."
            ),
            "basis": (
                "Its starting_solution is a correct digit-sum implementation and "
                "its score is binary, so it ships already solved."
            ),
        },
        {
            "id": "H2",
            "statement": (
                "count_primes null-variant reward standard deviation exceeds "
                "0.05."
            ),
            "basis": "Scouting probe observed a spread of 0.188 at n=12.",
        },
        {
            "id": "H3",
            "statement": (
                "On count_primes, best-of-5 over null variants yields at least "
                "0.10 of reward — a phantom improvement from doing nothing."
            ),
            "basis": (
                "Taking a maximum over a clamped noise distribution grows with "
                "k; the scouting probe already showed single draws reaching "
                "0.188."
            ),
        },
        {
            "id": "H4",
            "statement": (
                "On count_primes the rectification bias — clamped mean minus "
                "unclamped mean over null variants — is positive and at least "
                "0.05."
            ),
            "basis": (
                "max(0.0, ...) censors the negative half of the noise "
                "distribution; the scouting probe measured roughly +0.18."
            ),
        },
        {
            "id": "H5",
            "statement": "No task in the suite is admitted.",
            "basis": (
                "Bold and falsifiable. sum_digits is expected to fail on "
                "ceiling and both timing tasks on noise; if any task is "
                "admitted this prediction is wrong and the suite is more usable "
                "than expected."
            ),
        },
    ],
    "claim_boundary": (
        "Instrument audit of the executable task substrate. Measures properties "
        "of the reward function only. Makes no claim about scaffold "
        "improvement, model self-improvement, or a recursive effect."
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E63-preregistration.json")
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
