"""Run the matched-budget selection comparison on the three-task benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

from recursive_lab.quality_diversity import CandidateEvaluation
from recursive_lab.selection_comparison import ComparisonBudget, compare_policies
from recursive_lab.task_harness import ExecutableTaskSuite

TASKS = ("optimize_function", "count_primes", "sum_digits")

VARIANTS = {
    "optimize_function": (
        "def solve(n):\n    total = 0\n    for i in range(n):\n        total += i * i\n    return total\n",
        "def solve(n):\n    if n <= 0:\n        return 0\n    return (n - 1) * n * (2 * n - 1) // 6\n",
        "def solve(n):\n    return 0\n",
    ),
    "count_primes": (
        "def solve(n):\n    total = 0\n    for value in range(n):\n        if value > 1:\n            prime = 1\n            for divisor in range(2, value):\n                if value % divisor == 0:\n                    prime = 0\n                    break\n            total += prime\n    return total\n",
        "def solve(n):\n    total = 0\n    for value in range(2, n):\n        prime = 1\n        divisor = 2\n        while divisor * divisor <= value:\n            if value % divisor == 0:\n                prime = 0\n                break\n            divisor += 1\n        total += prime\n    return total\n",
        "def solve(n):\n    return 0\n",
    ),
    "sum_digits": (
        "def solve(n):\n    value = -n if n < 0 else n\n    total = 0\n    while value:\n        total += value % 10\n        value //= 10\n    return total\n",
        "def solve(n):\n    if n < 0:\n        n = -n\n    result = 0\n    while n > 0:\n        result += n % 10\n        n = n // 10\n    return result\n",
        "def solve(n):\n    return n\n",
    ),
}


def _evaluate(
    suite: ExecutableTaskSuite, candidate: tuple[int, ...], cache: dict
) -> CandidateEvaluation:
    results = []
    for task_id, variant in zip(TASKS, candidate):
        key = (task_id, variant)
        if key not in cache:
            cache[key] = suite.evaluate(VARIANTS[task_id][variant], task_id=task_id)[0]
        results.append(cache[key])
    # Fixed tiers avoid treating local timing noise as search-policy evidence:
    # baseline=.5, reviewed improved variant=1, deliberately broken control=0.
    tiers = (0.5, 1.0, 0.0)
    utilities = tuple(
        tiers[variant] if result.correct else 0.0
        for result, variant in zip(results, candidate)
    )
    correct_fraction = sum(result.correct for result in results) / len(results)
    objective = sum(utilities) / len(utilities)
    return CandidateEvaluation(
        objective=objective,
        features=(utilities[0], utilities[1], utilities[2], correct_fraction),
        metrics={
            "optimize_function": utilities[0],
            "count_primes": utilities[1],
            "sum_digits": utilities[2],
            "correct_fraction": correct_fraction,
        },
    )


def _mutate(candidate: tuple[int, ...], rng) -> tuple[int, ...]:
    values = list(candidate)
    task = rng.randrange(len(values))
    choices = [
        index for index in range(len(VARIANTS[TASKS[task]])) if index != values[task]
    ]
    values[task] = rng.choice(choices)
    return tuple(values)


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, allow_nan=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposals", type=int, default=12)
    parser.add_argument(
        "--seeds", type=int, default=5, help="number of independent seeds"
    )
    parser.add_argument("--out", default="runs/selection-comparison.json")
    args = parser.parse_args()
    if args.seeds < 1:
        parser.error("--seeds must be positive")
    suite = ExecutableTaskSuite(TASKS, correctness_only=True)
    evaluation_cache = {}
    report = compare_policies(
        initial=(0, 0, 0),
        mutate=_mutate,
        evaluate=lambda candidate: _evaluate(suite, candidate, evaluation_cache),
        budget=ComparisonBudget(args.proposals, len(TASKS)),
        seeds=tuple(range(args.seeds)),
        bins=(3, 3, 2, 2),
    )
    report["benchmark_manifest_digest"] = suite.manifest_digest
    report["tasks"] = list(TASKS)
    report["scoring"] = {
        "correctness_gate": "executable task harness",
        "variant_quality_tiers": {
            "baseline": 0.5,
            "reviewed_improvement": 1.0,
            "broken_control": 0.0,
        },
        "identical_evaluation_cache_entries": len(evaluation_cache),
    }
    report.pop("report_digest", None)
    canonical = json.dumps(
        report, allow_nan=False, sort_keys=True, separators=(",", ":")
    )
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    output = Path(args.out)
    _atomic_json(output, report)
    print(f"Matched budgets: {report['matched_budget']}")
    for policy, summary in report["summaries"].items():
        print(f"{policy:18} mean best={summary['mean_best_objective']:.4f}")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
