"""E72: is improver quality measurable at all?

Three attempts to make search visible by making *tasks* harder all failed, and
the consolidated finding was a narrow model competence band: easy tasks are
one-shot solved, harder ones yield nothing valid.  Making tasks harder was the
wrong lever to reach for first.

This asks the prior question directly.  The mutable artifact in this project's
design is a **typed strategy**, not a program.  So: holding the task set, the
budget, the seeds and the subset rules fixed, does changing the strategy change
the outcome?

    If two strategies produce different success rates, improver quality is
    measurable, and a recursive claim becomes expressible.
    If they do not, no amount of strategy evolution can be evidence of anything
    on this substrate, and that needs saying plainly.

Budget is ONE proposal per (strategy, task, seed).  A single proposal measures
the strategy's success probability directly, with no selection or iteration
mixed in, so any difference is attributable to the instruction alone.

No capability claim is made either way.  A positive result licenses measuring
improver quality; it is not itself evidence of self-improvement, and certainly
not of a recursive effect.
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

TASKS = (
    "digit_sum_graded",
    "count_one_bits",
    "collatz_steps",
    "integer_sqrt",
    "signed_transform",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--temperature", type=float, default=1.3)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("experiments/E72-strategy-discrimination.json"),
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
            solved = valid = 0
            scores = []
            for seed in range(args.seeds):
                result = proposer.propose(
                    env.task_prompt,
                    env.starting_solution,
                    f"passes {env.starting_passed} of {env.total_cases} hidden "
                    f"tests; attempt {seed}",
                )
                if result.candidate is None:
                    continue
                if _validate_candidate(result.candidate)[1] is not None:
                    continue
                valid += 1
                score = env.score(result.candidate).reward
                scores.append(score)
                if score >= 1.0:
                    solved += 1
            rows.append(
                {
                    "task": task_id,
                    "strategy": strategy.name,
                    "strategy_digest": strategy.digest,
                    "seeds": args.seeds,
                    "valid": valid,
                    "solved": solved,
                    "success_rate": solved / args.seeds,
                    "mean_score": statistics.fmean(scores) if scores else 0.0,
                    "tokens": proposer.total_tokens,
                }
            )
            print(
                f"[{task_id}/{strategy.name}] valid {valid}/{args.seeds} "
                f"solved {solved}/{args.seeds} "
                f"mean {rows[-1]['mean_score']:+.3f}",
                flush=True,
            )

    by_strategy = {
        strategy.name: [r for r in rows if r["strategy"] == strategy.name]
        for strategy in BASELINE_STRATEGIES
    }
    pooled = {
        name: statistics.fmean(r["success_rate"] for r in group)
        for name, group in by_strategy.items()
    }
    pooled_valid = {
        name: statistics.fmean(r["valid"] / r["seeds"] for r in group)
        for name, group in by_strategy.items()
    }
    spread = max(pooled.values()) - min(pooled.values())

    report = {
        "schema_version": 1,
        "experiment_id": "E72-strategy-discrimination",
        "question": (
            "Holding tasks, budget, seeds and subset rules fixed, does changing "
            "the strategy change the outcome?"
        ),
        "claim_boundary": (
            "Measures whether improver quality is observable on this substrate. "
            "A positive result licenses measuring improver quality; it is not "
            "evidence of self-improvement or of a recursive effect."
        ),
        "makes_capability_claim": False,
        "budget": "one proposal per (strategy, task, seed); no iteration",
        "tasks": list(TASKS),
        "strategies": [s.to_dict() for s in BASELINE_STRATEGIES],
        "rows": rows,
        "pooled_success_rate": pooled,
        "pooled_valid_rate": pooled_valid,
        "success_rate_spread": spread,
        "improver_quality_measurable": spread > 0.0,
        "wall_seconds": time.perf_counter() - started,
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)

    print("\npooled success rate by strategy:")
    for name, value in sorted(pooled.items(), key=lambda kv: -kv[1]):
        print(f"  {name:10} {value:.0%}  (valid {pooled_valid[name]:.0%})")
    print(f"\nspread {spread:.0%} -> improver quality measurable: {spread > 0.0}")
    print(f"wall {report['wall_seconds']:.0f}s")


if __name__ == "__main__":
    main()
