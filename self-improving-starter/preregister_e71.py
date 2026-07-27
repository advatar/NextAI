"""Freeze the E71 plan: the governed search with a model in the proposer slot.

E70 established that the instrument works end to end -- a null control at exactly
0.0, an unselected control at -1.30, and one genuine held-out improvement -- but
its proposer was a generic AST mutator with no model anywhere.  E71 replaces it
with the local Gemma 4 E2B server.

Design constraints learned the hard way
---------------------------------------

**A completable budget.**  E70's first attempt was launched without computing its
cost and ran 2h11m before being killed.  At roughly 15 seconds per model call,
the budget here is set so the whole run finishes inside an hour: 15 proposals x 3
seeds x 4 tasks for the governed arm plus one call per seed per task for the
single-shot arm is about 190 calls.

**Progress logging.**  E70 printed nothing until completion, so a long run was
indistinguishable from a hung one.  Every arm reports as it finishes.

**Loop guarding, not timeouts.**  A model can emit non-terminating programs just
as a mutator can.  ``recursive_lab.loop_guard`` bounds iterations, so this cannot
repeat E70's timeout failures in either direction.

**A hard diversity gate.**  At temperature 1.0 this model returns ONE identical
program on every call -- measured 1/5 unique, and unchanged by prompt variation
alone.  That is the E58 defect reproduced: six calls, one candidate digest, an
adoption gate passing on a search that never searched.  Both levers together
(temperature 1.3 and a per-call prompt nonce) gave 5/10 unique with 10/10
validator-clean.  A governed run whose unique-candidate count falls below the
floor is recorded VOID rather than scored.

The arms answer a question E70 could not
-----------------------------------------

A capable model may simply solve these tasks in one shot, in which case the
iterate-and-select loop is decoration.  ``single_shot`` makes that explicit
rather than leaving it as an unexamined assumption: one proposal from the
starting solution, no iteration, no selection.  If ``governed`` does not beat it,
the governed machinery is not earning its cost on this suite.

Trust boundary: the model sees the public task prompt, the current program, and a
count of development cases passed.  It never sees the hidden cases, the oracle,
the reference solution, or the held-out split -- ``build_prompt`` has no
parameter through which they could reach it.  Results are reported on held-out
cases only.

Disclosure: not blind.  Feasibility was measured on digit_sum_graded before
freezing this plan: 10/10 parsed and validator-clean at temperature 1.3, 5/10
unique.  No task was scored and no search was run.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from compare_selection import _atomic_json
from preregister_e60 import digest_of

PREREGISTRATION = {
    "schema_version": 1,
    "experiment_id": "E71-model-governed-search",
    "follows": "E70d-governed-search",
    "question": (
        "With a live model in the proposer slot, does the governed search "
        "produce held-out correctness improvements, and does iterating and "
        "selecting beat a single proposal?"
    ),
    "makes_capability_claim": True,
    "capability_claim_boundary": (
        "A local Gemma 4 E2B model repairing four small Python functions under a "
        "governed loop. This is a claim about a model fixing bugs on a four-task "
        "suite. It is NOT evidence of self-improvement: the model does not "
        "modify its own scaffold, weights, or proposer, and nothing here is "
        "recursive."
    ),
    "tasks": [
        "digit_sum_graded",
        "count_one_bits",
        "collatz_steps",
        "integer_sqrt",
    ],
    "proposer": {
        "module": "recursive_lab.model_proposer",
        "model": "gemma-4-e2b-it-4bit-mlx via local OptiQ MLX server",
        "endpoint": "http://127.0.0.1:12345/v1",
        "temperature": 1.3,
        "prompt_nonce": (
            "an attempt index is included per call. Temperature alone does not "
            "produce diversity on this model, and neither does prompt variation "
            "alone; both are required."
        ),
    },
    "arms": {
        "governed": (
            "iterate: propose from the incumbent, promote only on strict "
            "development improvement"
        ),
        "single_shot": (
            "one proposal from the starting solution, no iteration, no "
            "selection. The baseline that asks whether the loop earns its cost."
        ),
        "null_only": (
            "semantic no-op variants, no model call. Must score exactly 0.0; "
            "verifies the evaluation path end to end."
        ),
    },
    "trust_boundary": (
        "The model receives the public task prompt, the current program, and a "
        "count of development cases passed. It never receives hidden cases, the "
        "oracle, the reference solution, or the held-out split."
    ),
    "instrument": {
        "proposals_per_governed_run": 15,
        "seeds_per_arm": 3,
        "iteration_limit": 20000,
        "candidate_timeout_seconds": 30.0,
        "minimum_unique_candidates": 4,
        "estimated_model_calls": 192,
        "primary_metric": "held-out normalised delta against the starting solution",
    },
    "void_rule": (
        "A governed run with fewer than minimum_unique_candidates distinct "
        "candidate digests is VOID, not scored. A run that never searched has no "
        "result either way, which is the distinction E58 collapsed."
    ),
    "analysis_plan": {
        "primary": (
            "Per task per arm: mean held-out delta across seeds, with the "
            "development delta alongside so overfitting is visible."
        ),
        "loop_value": (
            "governed versus single_shot on held-out delta. If the loop does not "
            "beat one proposal, that is reported plainly."
        ),
        "null_handling": (
            "Recorded as measured. A void run is reported as void and is not "
            "retried with different settings to obtain a score."
        ),
    },
    "predictions": [
        {
            "id": "H1",
            "statement": "null_only scores exactly 0.0 on every task and seed.",
            "basis": (
                "Deterministic reward, semantically identical programs. Held "
                "since E69 and re-checked here because it is the canary that "
                "caught E70b's contamination."
            ),
        },
        {
            "id": "H2",
            "statement": (
                "governed achieves a strictly positive mean held-out delta on at "
                "least two tasks."
            ),
            "basis": (
                "These are small, well-specified edge-case bugs and the model "
                "produced valid programs 10/10 in feasibility testing. A "
                "language model should reach fixes the generic mutator could "
                "not, which managed only one task."
            ),
        },
        {
            "id": "H3",
            "statement": (
                "single_shot achieves a strictly positive mean held-out delta on "
                "at least one task."
            ),
            "basis": (
                "The tasks are simple enough that one proposal may suffice. "
                "Stated in advance so a one-shot success is not later "
                "reinterpreted as evidence for the loop."
            ),
        },
        {
            "id": "H4",
            "statement": (
                "governed's pooled held-out delta is greater than or equal to "
                "single_shot's."
            ),
            "basis": (
                "Iteration and selection should not actively hurt. If governed "
                "loses, the loop is costing more than it returns on this suite "
                "and should be reported as such."
            ),
        },
        {
            "id": "H5",
            "statement": (
                "No governed run is void: every one produces at least 4 distinct "
                "candidates from 15 proposals."
            ),
            "basis": (
                "Feasibility measured 5/10 unique at temperature 1.3 with a "
                "prompt nonce. At temperature 1.0 the same model gave 1/5, so "
                "this checks the mitigation holds across all four tasks rather "
                "than just the one it was tuned on."
            ),
        },
        {
            "id": "H6",
            "statement": (
                "At least 80% of model proposals pass the candidate validator."
            ),
            "basis": (
                "10/10 on digit_sum_graded in feasibility testing. A lower rate "
                "on other tasks would mean the subset restriction, not the bug, "
                "is what the model is failing."
            ),
        },
    ],
    "claim_boundary": (
        "A local model repairing four small deterministic Python tasks under a "
        "governed loop, scored on held-out cases. Not evidence of model "
        "self-improvement and not evidence of a recursive effect."
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E71-preregistration.json")
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
