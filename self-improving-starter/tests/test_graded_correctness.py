"""A deterministic reward must be deterministic, unclamped, and have headroom.

E63-E68 spent ten experiments on a wall-clock reward and never produced a task
admissible under replication. Every defect was a timing defect. These tests pin
the properties that make the graded-correctness reward different in kind: the
same program always scores the same, a no-op scores exactly zero, and a
regression scores negative rather than being floored.

The last point matters most. Zero spread on null variants looks identical
whether it comes from determinism or from censoring — a reward clamped to a
constant produces exactly that, and E64 admitted ``count_primes`` v1 on the
artefact. The regression probe is the discriminator.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from environments import CORRECTNESS_TASKS, REGISTRY  # noqa: E402
from environments.correctness_tasks import (  # noqa: E402
    CollatzStepsEnv,
    CountOneBitsEnv,
    DigitSumGradedEnv,
    IntegerSqrtEnv,
)
from environments.optimize_function import _validate_candidate  # noqa: E402
from recursive_lab.reward_probes import semantic_noop_variant  # noqa: E402

TASK_CLASSES = (
    DigitSumGradedEnv,
    CountOneBitsEnv,
    CollatzStepsEnv,
    IntegerSqrtEnv,
)
REGRESSION = "def solve(n):\n    return 0\n"


class Registration(unittest.TestCase):
    def test_every_correctness_task_is_registered(self):
        for name in CORRECTNESS_TASKS:
            self.assertIn(name, REGISTRY)

    def test_there_are_at_least_three(self):
        """The readiness bar; fewer would not be a benchmark."""
        self.assertGreaterEqual(len(CORRECTNESS_TASKS), 3)


class SolutionsAreAdmissible(unittest.TestCase):
    def test_anchor_solutions_pass_the_validator(self):
        for factory in TASK_CLASSES:
            for attribute in ("starting_solution", "reference_solution"):
                source = getattr(factory, attribute).fget(factory)  # type: ignore[attr-defined]
                _, failure = _validate_candidate(source)
                self.assertIsNone(
                    failure, msg=f"{factory.__name__}.{attribute}: {failure}"
                )


class OraclesAreIndependentlyCorrect(unittest.TestCase):
    """The oracle must not simply be the reference solution restated."""

    def test_digit_sum(self):
        env = DigitSumGradedEnv.__new__(DigitSumGradedEnv)
        for n in (-987654, -45, -1, 0, 1, 45, 987654, 1000000):
            self.assertEqual(env.oracle(n), sum(int(d) for d in str(abs(n))))

    def test_count_one_bits(self):
        env = CountOneBitsEnv.__new__(CountOneBitsEnv)
        for n in (-255, -7, -1, 0, 1, 7, 255, 65535):
            self.assertEqual(env.oracle(n), bin(abs(n)).count("1"))

    def test_integer_sqrt(self):
        import math

        env = IntegerSqrtEnv.__new__(IntegerSqrtEnv)
        for n in (-4, -1, 0, 1, 2, 8, 9, 10, 99, 100, 101, 10000):
            expected = -1 if n < 0 else math.isqrt(n)
            self.assertEqual(env.oracle(n), expected, msg=f"n={n}")

    def test_collatz_sentinel_for_non_positive(self):
        env = CollatzStepsEnv.__new__(CollatzStepsEnv)
        for n in (-100, -5, -1, 0):
            self.assertEqual(env.oracle(n), -1)
        self.assertEqual(env.oracle(1), 0)
        self.assertEqual(env.oracle(2), 1)
        self.assertEqual(env.oracle(3), 7)


class RewardContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.envs = {name: REGISTRY[name]() for name in CORRECTNESS_TASKS}

    def test_starting_solution_scores_exactly_zero(self):
        for name, env in self.envs.items():
            self.assertEqual(
                env.score(env.starting_solution).reward, 0.0, msg=name
            )

    def test_reference_scores_exactly_one_and_is_correct(self):
        for name, env in self.envs.items():
            result = env.score(env.reference_solution)
            self.assertEqual(result.reward, 1.0, msg=name)
            self.assertTrue(result.correct, msg=name)

    def test_null_variants_score_exactly_zero(self):
        for name, env in self.envs.items():
            for index in range(3):
                variant = semantic_noop_variant(env.starting_solution, index)
                self.assertEqual(env.score(variant).reward, 0.0, msg=f"{name}/{index}")

    def test_regression_scores_negative(self):
        """The discriminator: a censored reward would return ~0.0 here."""
        for name, env in self.envs.items():
            self.assertLess(env.score(REGRESSION).reward, -0.05, msg=name)

    def test_scoring_is_deterministic(self):
        for name, env in self.envs.items():
            values = {env.score(env.reference_solution).reward for _ in range(4)}
            self.assertEqual(len(values), 1, msg=name)

    def test_every_task_has_headroom(self):
        for name, env in self.envs.items():
            report = env.baseline_report()
            self.assertGreaterEqual(report["headroom_cases"], 4, msg=name)
            self.assertLess(
                report["starting_passed"], report["total_cases"], msg=name
            )

    def test_starting_solutions_terminate_on_every_case(self):
        """An earlier collatz draft looped forever on solve(0), timing out the
        run and scoring 0/15 — which reads as huge headroom but means the task
        is unusable, and also makes negative rewards impossible."""
        for name, env in self.envs.items():
            self.assertGreater(env.baseline_report()["starting_passed"], 0, msg=name)

    def test_imports_are_refused(self):
        env = self.envs["digit_sum_graded"]
        result = env.score("import os\ndef solve(n):\n    return 0\n")
        self.assertEqual(result.reward, -1.0)
        self.assertFalse(result.correct)


class ConstructionGuards(unittest.TestCase):
    def test_task_without_headroom_fails_closed(self):
        class AlreadySolved(DigitSumGradedEnv):
            name = "already_solved"

            @property
            def starting_solution(self) -> str:
                return self.reference_solution

        with self.assertRaises(RuntimeError):
            AlreadySolved()

    def test_task_with_a_broken_reference_fails_closed(self):
        class BadReference(DigitSumGradedEnv):
            name = "bad_reference"

            @property
            def reference_solution(self) -> str:
                return "def solve(n):\n    return 0\n"

        with self.assertRaises(RuntimeError):
            BadReference()


if __name__ == "__main__":
    unittest.main()
