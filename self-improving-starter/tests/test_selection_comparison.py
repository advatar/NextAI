import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from recursive_lab.quality_diversity import CandidateEvaluation
from recursive_lab.selection_comparison import (
    POLICIES,
    ComparisonBudget,
    budget_curve,
    compare_policies,
    run_archive_recombination,
    run_policy,
)


def evaluate(value):
    score = value / 10
    return CandidateEvaluation(score, (score, 1 - score), {"score": score})


class SelectionComparisonTests(unittest.TestCase):
    def test_all_policies_use_exactly_matched_budgets(self):
        report = compare_policies(
            initial=0,
            mutate=lambda value, rng: min(10, value + rng.randrange(1, 3)),
            evaluate=evaluate,
            budget=ComparisonBudget(7, 3),
            seeds=(1, 2),
            bins=(2, 2),
        )
        self.assertTrue(report["matched_budget"])
        self.assertEqual({run["policy"] for run in report["runs"]}, set(POLICIES))
        self.assertTrue(
            all(run["candidate_evaluations"] == 7 for run in report["runs"])
        )
        self.assertTrue(all(run["task_evaluations"] == 21 for run in report["runs"]))

    def test_seeded_runs_are_reproducible(self):
        kwargs = dict(
            policy="quality_diversity",
            initial=0,
            mutate=lambda value, rng: min(10, value + rng.randrange(1, 4)),
            evaluate=evaluate,
            budget=ComparisonBudget(5),
            seed=9,
            bins=(2, 2),
        )
        self.assertEqual(run_policy(**kwargs), run_policy(**kwargs))

    def test_rejects_invalid_budget_and_evaluation(self):
        with self.assertRaises(ValueError):
            ComparisonBudget(0)
        with self.assertRaises(ValueError):
            run_policy(
                policy="greedy",
                initial=0,
                mutate=lambda value, rng: value,
                evaluate=lambda value: CandidateEvaluation(float("nan"), (0.5,), {}),
                budget=ComparisonBudget(1),
                seed=0,
                bins=(2,),
            )

    def test_budget_curve_uses_matched_trajectory_prefixes(self):
        report = compare_policies(
            initial=0,
            mutate=lambda value, rng: min(10, value + 1),
            evaluate=evaluate,
            budget=ComparisonBudget(4, 3),
            seeds=(1, 2),
            bins=(2, 2),
        )
        curve = budget_curve(report, (1, 2, 4), target_objective=0.4)
        last = curve["points"][-1]["policies"]["greedy"]
        self.assertEqual(curve["checkpoints"], [1, 2, 4])
        self.assertEqual(last["mean_best_objective"], 0.4)
        self.assertEqual(last["target_hit_rate"], 1.0)
        self.assertEqual(last["task_evaluations_per_run"], 12)

    def test_budget_curve_rejects_bad_checkpoints(self):
        with self.assertRaises(ValueError):
            budget_curve({}, (2, 1))

    def test_archive_recombination_is_seeded_and_matched(self):
        kwargs = dict(
            initial=0,
            crossover=lambda a, b, rng: max(a, b),
            mutate=lambda value, rng: min(10, value + 1),
            evaluate=evaluate,
            budget=ComparisonBudget(4, 3),
            seed=7,
            bins=(2, 2),
        )
        first = run_archive_recombination(**kwargs)
        self.assertEqual(first, run_archive_recombination(**kwargs))
        self.assertEqual((first.candidate_evaluations, first.task_evaluations), (4, 12))


if __name__ == "__main__":
    unittest.main()
