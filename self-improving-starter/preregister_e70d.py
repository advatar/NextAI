"""Freeze the E70d plan: the governed search, with non-termination bounded.

THIRD AMENDMENT, and the last on measurement. E70 failed on a 15s timeout, E70b
on a 0.5s one. Both are the same error: using *time* to detect non-termination,
when the two failure modes move in opposite directions with machine load. E70c
calibrates the timeout, which mitigates but does not remove the dependence.

``recursive_lab.loop_guard`` removes it. Every loop in a candidate shares one
iteration counter and breaks past a limit, so a non-terminating program returns
wrong answers in milliseconds and is simply never promoted. Validated on 240
real mutants across the four tasks: every one ran to completion, 1.9-178.8ms
each, zero timeouts, against 25-78% previously consuming a full timeout.

The limit comes from a cost model rather than intuition, which is what the
earlier timeouts lacked. A hanging mutant costs ``limit x cases`` iterations on
every evaluation; the largest legitimate workload in the suite is collatz_steps
at n=77_031 needing ~350 iterations. 20_000 is ~57x that and costs ~320_000
iterations, i.e. milliseconds. An earlier draft used 1_000_000 and had to be
killed after ten minutes -- the same failure in a different currency.

E70c is allowed to finish independently; if the two disagree, the guarded run is
the trustworthy one, because its result does not depend on machine load at all.

SECOND AMENDMENT. E70b ran to completion but its measurement was contaminated,
and the null control is what caught it. ``null_only`` proposes semantically
identical programs and must therefore score exactly 0.0; it returned -0.4444 on
digit_sum_graded with 3-12% of evaluations recorded as non-terminating. Those
were FALSE timeouts: the fixed 0.5s bound is below the noise floor for a
*correct* program on a loaded machine. A follow-up probe measured 2/12 false
timeouts on integer_sqrt with wall times per evaluation reaching 0.76s, against
Xcode at 92% CPU and WindowServer at 76%.

E70b's numbers are therefore not reported as results, including its apparent
+0.3333 on count_one_bits. Two fixes, both measurement-side:

* the timeout is now **calibrated** from the starting solution's actual runtime
  (max of five samples x 20, floor 2s), so it tracks current machine load;
* the champion is measured **best-of-three**. A false timeout fails every case,
  so it can only understate a score; taking the best across retries recovers a
  correct program's true value while leaving a genuinely hanging one unchanged.

H6's band is widened and restated, because E70b showed the original metric
conflated non-termination with false timeouts.

AMENDMENT NOTICE. E70's frozen plan (digest 3fda04c9...) could not be executed.
Its 15-second candidate timeout was inherited from the environment default, and
the generic mutation operators produce non-terminating programs at a measured
25-58% rate, because perturbing a ``while`` condition or a loop counter easily
removes the exit. The run spent 2h11m accumulating 39 seconds of CPU -- blocked,
not computing -- and was killed.

**No results were observed before this amendment.** The run produced zero bytes
of output and no report file; the failure was detected from process state
(elapsed versus CPU time), not from any measurement. Budget, timeout and seed
count are changed here for feasibility alone, and the hypotheses are carried
over unchanged apart from one addition (H6) covering the non-termination rate,
which is now a first-class measurement rather than an unmodelled cost.

E69 produced the first instrument this line of work has been able to trust: four
deterministic graded-correctness tasks, all solid across five rounds, with a
best-of-k phantom gain of exactly zero.  E70 finally runs a search on it.

This is the first experiment in the series that measures a **capability** rather
than an instrument, and it is scoped accordingly.  The proposer is a generic AST
mutator, not a model.  A positive result would say "a governed mutation search
can fix some of these bugs", not anything about model self-improvement, and
certainly nothing about a recursive effect.

Two design commitments matter more than the outcome.

**A development/held-out split.**  The search is scored only on development
cases; the reported result is the held-out delta.  Without this, "improvement"
is indistinguishable from fitting the graded set.  Cases are split by stratified
alternation over the starting solution's failures, so both halves are guaranteed
to contain fixable cases.

**A generic proposer.**  The mutation operators perturb constants, comparisons,
arithmetic operators, signs and branch order.  None of them encodes a fix.  E9
recorded why this matters: a deterministic exploiter that "encodes useful
compositional bias" is rediscovering an answer its author planted.  A template
such as "insert a negative-number guard" would solve three of these four tasks
by construction and would be worthless as evidence.  Some tasks are therefore
expected to be unreachable, and that is the honest expectation, not a failure of
the setup.

Arms share a budget of candidate evaluations exactly:

* ``governed`` -- mutate from the incumbent, promote on development improvement;
* ``random_walk`` -- mutate the same way, but never select; report the final
  candidate.  This is the control that separates *search* from *mutation*;
* ``null_only`` -- propose semantically identical no-ops and keep the best by
  development score.  This is the end-to-end phantom-gain check: on a
  deterministic reward it must return exactly zero.

Disclosure: not blind.  ``collatz_steps`` is known to be reachable by a single
constant mutation, since its starting solution returns 0 where the contract says
-1, and the mutator perturbs integer constants.  ``digit_sum_graded`` and
``count_one_bits`` need a structural insertion that the operators cannot
produce.  Those expectations are recorded as H3 and H4 rather than discovered
afterwards.  No capability claim beyond the stated boundary is made under any
outcome.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from compare_selection import _atomic_json
from preregister_e60 import digest_of

PREREGISTRATION = {
    "schema_version": 1,
    "experiment_id": "E70d-governed-search",
    "follows": "E69-deterministic-substrate",
    "amends": "E70c-governed-search",
    "amendment_reason": (
        "Non-termination is now bounded by iterations rather than detected by "
        "timeout, so the measurement no longer depends on machine load. Prior: "
        "E70b was contaminated by false timeouts, detected by the null_only "
        "control scoring -0.4444 where exactly 0.0 is required by construction. "
        "Timeout is now calibrated from measured runtime and the champion is "
        "measured best-of-three. Prior context: E70's plan was not executable: a 15s candidate timeout against a 25-58% "
        "non-termination rate made the run take >20h. Killed after 2h11m with "
        "zero output and no report file, so no result informed this amendment. "
        "Timeout 15s -> 0.5s, budget 200 -> 150, seeds 5 -> 3."
    ),
    "question": (
        "On an admissible deterministic substrate, does a governed mutation "
        "search produce held-out correctness improvements that a matched-budget "
        "unselected control does not?"
    ),
    "makes_capability_claim": True,
    "capability_claim_boundary": (
        "Any positive result is a claim about a generic mutation search on four "
        "small Python tasks. It is NOT evidence of model self-improvement, of a "
        "recursive effect, or of anything about the scaffold improving itself. "
        "The proposer is an AST mutator with no model in the loop."
    ),
    "tasks": [
        "digit_sum_graded",
        "count_one_bits",
        "collatz_steps",
        "integer_sqrt",
    ],
    "split": {
        "method": (
            "Stratified alternation: cases the starting solution fails are dealt "
            "alternately to development and held-out, and likewise the cases it "
            "passes. Both halves are therefore guaranteed to contain fixable "
            "cases and regression-detecting cases."
        ),
        "search_sees": "development cases only",
        "reported_on": "held-out cases only",
    },
    "arms": {
        "governed": "mutate from the incumbent; promote on development improvement",
        "random_walk": (
            "mutate identically but never select; report the final candidate. "
            "Separates search from mutation."
        ),
        "null_only": (
            "propose semantic no-ops and keep the best by development score. "
            "End-to-end phantom-gain check; must be exactly zero."
        ),
    },
    "proposer": (
        "recursive_lab.program_mutation: generic AST edits to constants, "
        "comparisons, arithmetic operators, signs and branch order. No operator "
        "encodes a task fix."
    ),
    "instrument": {
        "candidate_evaluations_per_arm": 150,
        "seeds_per_arm": 3,
        "iteration_limit": 20000,
        "iteration_limit_justification": (
            "About 57x the largest legitimate workload in the suite "
            "(collatz_steps at n=77_031 needs ~350 iterations), costing ~320_000 "
            "iterations per hanging mutant. Derived from a cost model, not "
            "chosen by intuition."
        ),
        "timeout_floor_seconds": 10.0,
        "timeout_factor": 50.0,
        "champion_retries": 3,
        "timeout_justification": (
            "With loops bounded by iteration count, the timeout is only a "
            "backstop against pathologies the guard cannot reach, so it is set "
            "deliberately loose. Nothing should ever hit it."
        ),
        "mutation_edits_per_candidate": 1,
        "primary_metric": "held-out normalised delta against the starting solution",
    },
    "promotion_rule": (
        "A candidate is promoted only if it strictly improves the incumbent's "
        "development score. Ties are not promoted, so a no-op can never displace "
        "an incumbent."
    ),
    "analysis_plan": {
        "primary": (
            "Per task per arm: mean held-out delta across seeds, and the "
            "development delta alongside it so overfitting is visible."
        ),
        "control_comparison": (
            "governed versus random_walk on held-out delta, at identical budget "
            "and identical mutation operators. Only the selection differs."
        ),
        "overfitting": (
            "A development delta exceeding the held-out delta is reported as "
            "overfitting, not smoothed over."
        ),
        "null_handling": (
            "Recorded as measured. A task the mutator cannot reach is reported "
            "as unreached, and no operator is added afterwards to reach it."
        ),
    },
    "predictions": [
        {
            "id": "H1",
            "statement": (
                "null_only yields exactly 0.0 held-out delta on every task and "
                "every seed."
            ),
            "basis": (
                "E69 measured best-of-k phantom gain at exactly zero. This "
                "checks the property end to end through the search loop rather "
                "than in isolation."
            ),
        },
        {
            "id": "H2",
            "statement": (
                "governed achieves a strictly positive mean held-out delta on at "
                "least one task."
            ),
            "basis": "collatz_steps is reachable by a single constant mutation.",
        },
        {
            "id": "H3",
            "statement": "collatz_steps is the task governed search improves most.",
            "basis": (
                "Its fix is returning -1 instead of 0 for non-positive n, which "
                "the constant operator produces directly."
            ),
        },
        {
            "id": "H4",
            "statement": (
                "At least one task shows a mean held-out delta of 0.0 under "
                "governed search."
            ),
            "basis": (
                "digit_sum_graded and count_one_bits need a structural insertion "
                "the operators cannot generate. Recorded in advance so an "
                "unreached task is not later presented as a surprise."
            ),
        },
        {
            "id": "H6",
            "statement": (
                "Under the loop guard, fewer than 5% of candidates fail every "
                "case on digit_sum_graded and count_one_bits."
            ),
            "basis": (
                "A scouting probe measured 10/40, 6/40, 23/40 and 20/40 across "
                "the four tasks under a timeout. A 240-mutant probe under the "
                "guard measured all-wrong rates of 0/60, 2/60, 5/60 and 26/60, "
                "so the previously-dominant timeout component is gone. "
                "integer_sqrt is excluded from the claim because its 26/60 "
                "reflects genuinely broken programs rather than hangs."
            ),
        },
        {
            "id": "H5",
            "statement": (
                "governed's mean held-out delta exceeds random_walk's, pooled "
                "across tasks."
            ),
            "basis": (
                "The two arms share operators, budget and seeds; only selection "
                "differs. If selection buys nothing, the governed loop is doing "
                "no work."
            ),
        },
    ],
    "claim_boundary": (
        "A governed generic-mutation search on four small deterministic Python "
        "tasks, scored on held-out cases. Not evidence of model "
        "self-improvement or of a recursive effect."
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E70d-preregistration.json")
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
