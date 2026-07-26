"""Paired measurement must cancel drift and must not leak the reference.

E65 showed the executable suite's rewards are drift-dominated: a task's starting
solution is its own anchor and must score 0.0 by definition, yet scored +0.2339
and -0.1902. Averaging could not fix it because a median cannot cancel a trend
common to all its samples. A ratio against an adjacently-measured anchor can.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from recursive_lab.paired_timing import (  # noqa: E402
    PairedMeasurement,
    PairedTimingError,
    calibrate_reference_ratio,
    paired_measure,
    paired_reward,
    rename_function,
)

FAST = "def solve(n):\n    return n + 1\n"
SLOW = (
    "def solve(n):\n"
    "    total = 0\n"
    "    for i in range(n):\n"
    "        total += i\n"
    "    return total\n"
)


class RenameFunction(unittest.TestCase):
    def test_renames_the_definition(self):
        renamed = rename_function(FAST, "_h_anchor")
        tree = ast.parse(renamed)
        self.assertEqual(tree.body[0].name, "_h_anchor")

    def test_two_programs_can_coexist(self):
        source = rename_function(SLOW, "a") + rename_function(FAST, "b")
        namespace: dict = {}
        exec(compile(source, "<t>", "exec"), namespace)  # noqa: S102 - fixture
        self.assertEqual(namespace["a"](5), 10)
        self.assertEqual(namespace["b"](5), 6)

    def test_unparsable_fails_closed(self):
        with self.assertRaises(PairedTimingError):
            rename_function("def solve(:\n", "x")

    def test_multiple_functions_fail_closed(self):
        with self.assertRaises(PairedTimingError):
            rename_function(FAST + "def other(n):\n    return n\n", "x")


class RatioIsDriftImmune(unittest.TestCase):
    def test_ratio_is_the_quotient(self):
        measurement = PairedMeasurement(2.0e-3, 1.0e-3)
        self.assertAlmostEqual(measurement.ratio, 0.5)

    def test_multiplicative_drift_cancels(self):
        """The whole point: a common factor divides out."""
        clean = PairedMeasurement(2.0e-3, 1.0e-3)
        for drift in (0.5, 1.3, 4.0):
            drifted = PairedMeasurement(2.0e-3 * drift, 1.0e-3 * drift)
            self.assertAlmostEqual(drifted.ratio, clean.ratio)


class RewardScale(unittest.TestCase):
    def test_matching_the_anchor_scores_zero(self):
        self.assertAlmostEqual(paired_reward(1.0, 0.25), 0.0)

    def test_matching_the_reference_scores_one(self):
        self.assertAlmostEqual(paired_reward(0.25, 0.25), 1.0)

    def test_beating_the_reference_exceeds_one(self):
        self.assertGreater(paired_reward(0.1, 0.25), 1.0)

    def test_slower_than_the_anchor_goes_negative(self):
        """Not clamped: this is what stops noise rectifying into free reward."""
        self.assertLess(paired_reward(2.0, 0.25), 0.0)

    def test_reference_not_faster_than_anchor_fails_closed(self):
        for bad in (1.0, 1.5, 0.0, -0.2):
            with self.assertRaises(PairedTimingError):
                paired_reward(0.5, bad)


class EndToEnd(unittest.TestCase):
    """A real subprocess measurement, kept small so the suite stays quick."""

    def test_faster_candidate_beats_the_anchor(self):
        measurement = paired_measure(SLOW, FAST, 2000)
        self.assertLess(measurement.ratio, 1.0)

    def test_anchor_against_itself_is_near_one(self):
        """The sharpest diagnostic: no candidate involved, so any deviation is
        pure measurement error."""
        measurement = paired_measure(SLOW, SLOW, 2000)
        self.assertAlmostEqual(measurement.ratio, 1.0, delta=0.25)

    def test_calibration_returns_a_usable_reference_ratio(self):
        ratio = calibrate_reference_ratio(SLOW, FAST, 2000, rounds=1)
        self.assertGreater(ratio, 0.0)
        self.assertLess(ratio, 1.0)

    def test_calibration_rejects_zero_rounds(self):
        with self.assertRaises(PairedTimingError):
            calibrate_reference_ratio(SLOW, FAST, 100, rounds=0)


class ReferenceIsNotCoLocated(unittest.TestCase):
    def test_paired_script_contains_only_anchor_and_candidate(self):
        """The held-out reference must never share a process with a candidate.

        Only the anchor is co-located, and the anchor is public — it is printed
        in the task prompt — so nothing is leaked.
        """
        from recursive_lab.paired_timing import _paired_script

        secret = "def solve(n):\n    return 12345\n"
        script = _paired_script(SLOW, FAST, 100)
        self.assertNotIn("12345", script)
        self.assertIn("_h_anchor", script)
        self.assertIn("_h_candidate", script)
        del secret


class RoundsMustBeEven(unittest.TestCase):
    """An odd round count leaves a residual order bias.

    The order within a round alternates, so with 7 rounds the anchor took the
    cold first slot four times against the candidate's three. count_divisors
    exposed it immediately: its anchor self-score, which must be 0.0 by
    definition because no candidate is involved, came out at +0.1059. With an
    even count and a warm-up it is within a few thousandths of zero.
    """

    def test_paired_rounds_is_even(self):
        from recursive_lab.paired_timing import PAIRED_ROUNDS

        self.assertEqual(PAIRED_ROUNDS % 2, 0)
        self.assertGreaterEqual(PAIRED_ROUNDS, 2)

    def test_script_warms_both_programs_before_timing(self):
        from recursive_lab.paired_timing import _paired_script

        script = _paired_script(SLOW, FAST, 100)
        first_round = script.index("_h_anchor_samples = []")
        warm_up = script[:first_round]
        # Both programs must be exercised before any timed round begins.
        self.assertIn("_h_measure(_h_anchor, _h_repeats)", warm_up)
        self.assertIn("_h_measure(_h_candidate, _h_repeats)", warm_up)


if __name__ == "__main__":
    unittest.main()
