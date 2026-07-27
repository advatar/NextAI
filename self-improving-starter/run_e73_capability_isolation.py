"""E73: with compliance equalised, does any strategy gap survive?

E72 measured a 32% pooled spread between strategies and looked like the
prerequisite for a recursive claim.  Its own data undercut that reading:
``success_rate`` equalled ``valid_rate`` in all fifteen rows, so there was not a
single case where a valid candidate failed to solve its task.  Every difference
between strategies was whether the model emitted a program inside the candidate
subset.  That is compliance, not problem-solving, and evolving strategies
against it would optimise output formatting.

This isolates the two.  Each strategy retries until it produces a VALID
candidate, up to a fixed attempt cap, and only then is the candidate scored.
Two quantities are recorded separately:

* **attempts-to-validity** -- the compliance signal E72 was actually measuring.
* **solve rate among first-valid candidates** -- the capability signal, which is
  the one a recursive claim would need.

Retrying is semantics-preserving: it changes nothing about a candidate, it only
gives each strategy equal opportunity to clear the subset gate.  Nothing repairs
or rewrites model output, so no fix can leak in through the harness.

The task set is deliberately weighted toward tasks that are hard to *solve*
rather than hard to format, including two that E72's sibling calibration found
produced no valid candidates at all.  If capability differences exist anywhere on
this substrate, that is where they should appear.

Expected outcomes, both worth having:

* a surviving gap means strategy quality is capability, and metaproductivity
  becomes meaningful;
* no surviving gap means strategy quality on this substrate IS formatting, and
  that is the honest end of this road for this model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path

from compare_selection import _atomic_json
from environments import REGISTRY
from environments.optimize_function import _validate_candidate
from recursive_lab.model_proposer import (
    LocalOpenAICompatibleClient,
    ModelProgramProposer,
)
from recursive_lab.strategy_proposer import BASELINE_STRATEGIES

#: Weighted toward hard-to-solve rather than hard-to-format. The last two
#: produced 0/8 valid in calibration, so retrying is what gives them any chance
#: to contribute a capability observation.
TASKS = (
    "integer_sqrt",
    "signed_transform",
    "digit_ladder",
    "integer_cube_root",
    "round_half_to_even",
)


def first_valid(proposer, env, seed, max_attempts):
    """Retry until a candidate clears the subset gate, or the cap is reached."""
    for attempt in range(max_attempts):
        result = proposer.propose(
            env.task_prompt,
            env.starting_solution,
            f"passes {env.starting_passed} of {env.total_cases} hidden tests; "
            f"attempt {seed * 17 + attempt}",
        )
        if result.candidate is None:
            continue
        if _validate_candidate(result.candidate)[1] is not None:
            continue
        return result.candidate, attempt + 1
    return None, max_attempts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--max-attempts", type=int, default=4)
    parser.add_argument("--temperature", type=float, default=1.3)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("experiments/E73-capability-isolation.json"),
    )
    args = parser.parse_args()

    client = LocalOpenAICompatibleClient()
    started = time.perf_counter()
    rows = []

    for task_id in TASKS:
        env = REGISTRY[task_id]()
        for strategy in BASELINE_STRATEGIES:
            proposer = ModelProgramProposer(
                client,
                model="default_model",
                temperature=args.temperature,
                system_override=strategy.system_instruction(),
            )
            reached = solved = 0
            attempts_used = []
            scores = []
            for seed in range(args.seeds):
                candidate, attempts = first_valid(
                    proposer, env, seed, args.max_attempts
                )
                attempts_used.append(attempts)
                if candidate is None:
                    continue
                reached += 1
                score = env.score(candidate).reward
                scores.append(score)
                if score >= 1.0:
                    solved += 1
            rows.append(
                {
                    "task": task_id,
                    "strategy": strategy.name,
                    "seeds": args.seeds,
                    "reached_validity": reached,
                    "mean_attempts_to_validity": statistics.fmean(attempts_used),
                    "solved": solved,
                    # The capability signal: of the candidates that cleared the
                    # subset gate, how many actually solved the task.
                    "solve_rate_given_valid": (solved / reached) if reached else None,
                    "mean_score_given_valid": (
                        statistics.fmean(scores) if scores else None
                    ),
                }
            )
            row = rows[-1]
            print(
                f"[{task_id}/{strategy.name}] valid {reached}/{args.seeds} "
                f"(mean {row['mean_attempts_to_validity']:.1f} attempts) "
                f"solved-given-valid "
                f"{row['solve_rate_given_valid'] if row['solve_rate_given_valid'] is not None else 'n/a'}",
                flush=True,
            )

    def pooled(field):
        out = {}
        for strategy in BASELINE_STRATEGIES:
            values = [
                r[field]
                for r in rows
                if r["strategy"] == strategy.name and r[field] is not None
            ]
            out[strategy.name] = statistics.fmean(values) if values else None
        return out

    solve_pooled = pooled("solve_rate_given_valid")
    attempts_pooled = pooled("mean_attempts_to_validity")
    present = [v for v in solve_pooled.values() if v is not None]
    capability_spread = (max(present) - min(present)) if len(present) > 1 else 0.0
    compliance_spread = max(attempts_pooled.values()) - min(attempts_pooled.values())

    report = {
        "schema_version": 1,
        "experiment_id": "E73-capability-isolation",
        "question": (
            "With compliance equalised by retrying until valid, does any "
            "strategy difference in SOLVING survive?"
        ),
        "claim_boundary": (
            "Separates a compliance signal from a capability signal. A "
            "surviving capability gap would license measuring improver quality; "
            "it is not itself evidence of self-improvement or a recursive "
            "effect."
        ),
        "makes_capability_claim": False,
        "method": (
            "Retry until the candidate clears the subset gate, up to the attempt "
            "cap, then score. Retrying is semantics-preserving and nothing "
            "repairs or rewrites model output."
        ),
        "tasks": list(TASKS),
        "strategies": [s.to_dict() for s in BASELINE_STRATEGIES],
        "max_attempts": args.max_attempts,
        "rows": rows,
        "pooled_solve_rate_given_valid": solve_pooled,
        "pooled_attempts_to_validity": attempts_pooled,
        "capability_spread": capability_spread,
        "compliance_spread": compliance_spread,
        "capability_gap_survives": capability_spread > 0.0,
        "wall_seconds": time.perf_counter() - started,
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)

    print("\nCAPABILITY signal - solve rate given a valid candidate:")
    for name, value in solve_pooled.items():
        print(f"  {name:10} {'n/a' if value is None else format(value, '.0%')}")
    print("\nCOMPLIANCE signal - mean attempts to reach validity:")
    for name, value in attempts_pooled.items():
        print(f"  {name:10} {value:.2f}")
    print(f"\ncapability spread {capability_spread:.0%}, "
          f"compliance spread {compliance_spread:.2f} attempts")
    print(f"capability gap survives: {capability_spread > 0.0}")
    print(f"wall {report['wall_seconds']:.0f}s")


if __name__ == "__main__":
    main()
