"""Probes must not be evadable, and zero spread must not read as precision.

E63 and E64 both admitted ``optimize_function`` on a comment-appended null
variant. That environment compares programs by ``ast.dump``, so the comment was
invisible and it correctly returned exact zeros for what it recognised as the
same program. Both audits read those zeros as a perfect noise profile. E65's
AST-distinct probe measured a null sd of 0.1097 on the same task.
"""

from __future__ import annotations

import ast
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from recursive_lab.reward_probes import (  # noqa: E402
    ProbeError,
    best_of_k,
    is_semantically_distinct_source,
    median_of_subsample,
    median_score,
    monotonicity_probe,
    semantic_noop_variant,
    spread,
)

LOOP_PROGRAM = (
    "def solve(n):\n"
    "    total = 0\n"
    "    for i in range(n):\n"
    "        total += i * i\n"
    "    return total\n"
)
CONSTANT_PROGRAM = "def solve(n):\n    return 0\n"


def evaluate(source: str, argument: int) -> int:
    namespace: dict = {}
    exec(compile(source, "<probe>", "exec"), namespace)  # noqa: S102 - trusted fixture
    return namespace["solve"](argument)


class NoopVariantsAreUndetectable(unittest.TestCase):
    def test_variant_is_ast_distinct(self):
        """The property E63/E64's probe lacked."""
        variant = semantic_noop_variant(LOOP_PROGRAM, 0)
        self.assertTrue(is_semantically_distinct_source(LOOP_PROGRAM, variant))

    def test_comment_appended_variant_is_NOT_ast_distinct(self):
        """Pins why the old probe was evaded."""
        old_style = LOOP_PROGRAM + "\n# null variant 0\n"
        self.assertFalse(is_semantically_distinct_source(LOOP_PROGRAM, old_style))

    def test_variant_computes_the_same_answers(self):
        variant = semantic_noop_variant(LOOP_PROGRAM, 7)
        for argument in (-3, 0, 1, 5, 50):
            self.assertEqual(
                evaluate(variant, argument), evaluate(LOOP_PROGRAM, argument)
            )

    def test_distinct_indices_give_distinct_programs(self):
        first = semantic_noop_variant(LOOP_PROGRAM, 1)
        second = semantic_noop_variant(LOOP_PROGRAM, 2)
        self.assertTrue(is_semantically_distinct_source(first, second))

    def test_variant_adds_no_statements_when_renaming(self):
        """A rename must not add runtime work, or it is not a null change."""
        original = ast.parse(LOOP_PROGRAM).body[0]
        varied = ast.parse(semantic_noop_variant(LOOP_PROGRAM, 4)).body[0]
        self.assertEqual(len(original.body), len(varied.body))

    def test_program_without_bindings_still_varies(self):
        variant = semantic_noop_variant(CONSTANT_PROGRAM, 5)
        self.assertTrue(is_semantically_distinct_source(CONSTANT_PROGRAM, variant))
        self.assertEqual(evaluate(variant, 9), 0)

    def test_unparsable_source_fails_closed(self):
        with self.assertRaises(ProbeError):
            semantic_noop_variant("def solve(:\n", 0)

    def test_source_without_a_function_fails_closed(self):
        with self.assertRaises(ProbeError):
            semantic_noop_variant("x = 1\n", 0)


class MonotonicitySeparatesCensoringFromPrecision(unittest.TestCase):
    def test_censored_reward_is_caught(self):
        """A reward floored at zero returns 0.0 for a genuinely slower program."""
        result = monotonicity_probe(
            lambda source: (0.0, True), "slower", threshold=-0.05
        )
        self.assertFalse(result.responds)
        self.assertIn("censored or insensitive", result.detail)

    def test_honest_reward_passes(self):
        result = monotonicity_probe(
            lambda source: (-1.10, True), "slower", threshold=-0.05
        )
        self.assertTrue(result.responds)

    def test_reward_just_above_threshold_fails(self):
        result = monotonicity_probe(
            lambda source: (-0.04, True), "slower", threshold=-0.05
        )
        self.assertFalse(result.responds)

    def test_incorrect_slower_probe_is_not_counted_as_responding(self):
        result = monotonicity_probe(
            lambda source: (-5.0, False), "slower", threshold=-0.05
        )
        self.assertFalse(result.responds)
        self.assertIn("unmeasured", result.detail)


class MedianProtocol(unittest.TestCase):
    def test_median_score_averages_repeated_evaluations(self):
        values = iter([1.0, 5.0, 3.0])
        self.assertEqual(median_score(lambda source: next(values), "x", 3), 3.0)

    def test_median_score_rejects_zero_repeats(self):
        with self.assertRaises(ProbeError):
            median_score(lambda source: 0.0, "x", 0)

    def test_median_of_subsample_is_bounded_by_the_sample(self):
        rng = random.Random(1)
        measurements = [0.1, 0.2, 0.3, 0.4]
        for _ in range(50):
            value = median_of_subsample(measurements, 3, rng)
            self.assertGreaterEqual(value, min(measurements))
            self.assertLessEqual(value, max(measurements))

    def test_median_of_subsample_needs_measurements(self):
        with self.assertRaises(ProbeError):
            median_of_subsample([], 3, random.Random(0))


class BestOfK(unittest.TestCase):
    def test_best_of_k_grows_with_k(self):
        """The phantom gain a search manufactures from no-op proposals."""
        rng = random.Random(2)
        rewards = [-0.2, -0.1, 0.0, 0.1, 0.2]
        one = best_of_k(rewards, 1, 4000, rng)
        eight = best_of_k(rewards, 8, 4000, rng)
        self.assertGreater(eight, one)

    def test_best_of_k_on_a_constant_reward_is_that_constant(self):
        rng = random.Random(3)
        self.assertAlmostEqual(best_of_k([0.0] * 10, 5, 1000, rng), 0.0)

    def test_empty_rewards_fail_closed(self):
        with self.assertRaises(ProbeError):
            best_of_k([], 5, 10, random.Random(0))


class Spread(unittest.TestCase):
    def test_zero_spread_for_a_constant(self):
        self.assertEqual(spread([0.0] * 8), 0.0)

    def test_empty_fails_closed(self):
        with self.assertRaises(ProbeError):
            spread([])


if __name__ == "__main__":
    unittest.main()
