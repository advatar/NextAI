"""The two-block replication rule must refuse single-block effects.

E60 reported a ``rugged`` regression from one held-out block; E61 showed on
fresh seeds that it was noise.  E62 makes replication structural, and this rule
is the piece that decides what counts.  It is worth testing directly, because a
rule that quietly accepts a one-block effect would reintroduce exactly the
failure it exists to prevent.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compare_e62_promotion_objective import (  # noqa: E402
    excludes_zero,
    replication_verdict,
    score_objective,
)

FLOOR = 0.005


def block(delta, low, high):
    return {
        "regret_delta": delta,
        "regret_delta_95pct_bootstrap_ci": [low, high],
    }


class IntervalHelper(unittest.TestCase):
    def test_negative_interval_excludes_zero(self):
        self.assertTrue(excludes_zero([-0.02, -0.01]))

    def test_positive_interval_excludes_zero(self):
        self.assertTrue(excludes_zero([0.01, 0.02]))

    def test_spanning_interval_does_not(self):
        self.assertFalse(excludes_zero([-0.01, 0.02]))

    def test_touching_zero_does_not(self):
        self.assertFalse(excludes_zero([0.0, 0.02]))


class ReplicationRule(unittest.TestCase):
    def test_both_blocks_agree_and_clear_the_floor(self):
        verdict = replication_verdict(
            block(-0.02, -0.03, -0.01), block(-0.019, -0.028, -0.009), FLOOR
        )
        self.assertEqual(verdict, "replicated: reduces regret")

    def test_replicated_harm_is_named_as_harm(self):
        verdict = replication_verdict(
            block(0.02, 0.01, 0.03), block(0.018, 0.008, 0.028), FLOOR
        )
        self.assertEqual(verdict, "replicated: increases regret")

    def test_the_e60_rugged_pattern_is_refused(self):
        """The exact shape that fooled E60: significant in one block, gone in
        the next."""
        e60_like = block(0.00836, 0.00167, 0.01533)
        e61_like = block(-0.00165, -0.00843, 0.00503)
        verdict = replication_verdict(e60_like, e61_like, FLOOR)
        self.assertEqual(verdict, "UNREPLICATED: clears in one block only")
        self.assertTrue(verdict.startswith("UNREPLICATED"))

    def test_one_block_only_is_refused_in_either_order(self):
        strong = block(-0.02, -0.03, -0.01)
        weak = block(-0.002, -0.01, 0.006)
        self.assertTrue(
            replication_verdict(strong, weak, FLOOR).startswith("UNREPLICATED")
        )
        self.assertTrue(
            replication_verdict(weak, strong, FLOOR).startswith("UNREPLICATED")
        )

    def test_sign_disagreement_is_refused(self):
        verdict = replication_verdict(
            block(-0.02, -0.03, -0.01), block(0.02, 0.01, 0.03), FLOOR
        )
        self.assertEqual(verdict, "UNREPLICATED: blocks disagree in sign")

    def test_significant_but_below_the_floor_is_negligible(self):
        """The E60 curved case: real interval, meaningless magnitude."""
        verdict = replication_verdict(
            block(-0.00003, -0.00006, -0.00001),
            block(-0.00004, -0.00007, -0.00002),
            FLOOR,
        )
        self.assertEqual(verdict, "replicated but negligible")

    def test_one_block_below_the_floor_is_not_a_result(self):
        verdict = replication_verdict(
            block(-0.02, -0.03, -0.01), block(-0.001, -0.002, -0.0005), FLOOR
        )
        self.assertEqual(verdict, "replicated but negligible")

    def test_inconclusive_in_both_blocks(self):
        verdict = replication_verdict(
            block(-0.001, -0.01, 0.008), block(0.002, -0.009, 0.012), FLOOR
        )
        self.assertEqual(verdict, "inconclusive in both blocks")

    def test_no_verdict_calls_a_single_block_a_result(self):
        """Exhaustive guard: every outcome where the blocks disagree on
        significance must be labelled UNREPLICATED, never as a result."""
        strong = block(-0.02, -0.03, -0.01)
        for other in (
            block(-0.002, -0.01, 0.006),
            block(0.002, -0.006, 0.01),
            block(0.0, -0.01, 0.01),
        ):
            verdict = replication_verdict(strong, other, FLOOR)
            self.assertNotIn("replicated:", verdict)
            self.assertTrue(verdict.startswith("UNREPLICATED"))


class ObjectiveScoring(unittest.TestCase):
    def setUp(self):
        self.per_family = {"a": 0.10, "b": 0.30, "c": 0.20}
        self.weights = {"a": 0.9, "b": 0.1, "c": 0.5}

    def test_worst_family_takes_the_maximum(self):
        self.assertAlmostEqual(
            score_objective("worst_family", self.per_family, self.weights), 0.30
        )

    def test_macro_mean_is_unweighted(self):
        self.assertAlmostEqual(
            score_objective("macro_mean", self.per_family, self.weights), 0.20
        )

    def test_signal_weighting_downweights_low_disagreement_families(self):
        score = score_objective("signal_weighted", self.per_family, self.weights)
        # b carries the worst regret but the least signal, so the weighted score
        # must sit below the unweighted mean.
        self.assertLess(score, 0.20)
        expected = (0.10 * 0.9 + 0.30 * 0.1 + 0.20 * 0.5) / 1.5
        self.assertAlmostEqual(score, expected)

    def test_zero_weights_fail_closed(self):
        with self.assertRaises(ValueError):
            score_objective("signal_weighted", {"a": 0.1}, {"a": 0.0})

    def test_objectives_can_disagree(self):
        """If they always agreed, comparing them would be pointless."""
        worst = score_objective("worst_family", self.per_family, self.weights)
        macro = score_objective("macro_mean", self.per_family, self.weights)
        signal = score_objective("signal_weighted", self.per_family, self.weights)
        self.assertEqual(len({round(worst, 9), round(macro, 9), round(signal, 9)}), 3)


if __name__ == "__main__":
    unittest.main()
