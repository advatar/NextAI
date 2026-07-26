"""The repaired timing reward must not pay for doing nothing.

E63 measured three defects in ``count_primes``: a reference captured from one
noisy sample at import time, a reward clamped to [0, 1] that rectified noise
into free reward, and no held-out reference to anchor the scale. These tests pin
the corrected behaviour, in particular that a slower candidate scores *negative*
rather than being floored at zero -- the floor is what let a best-of-k search
manufacture 0.254 of reward from no-op proposals.
"""

from __future__ import annotations

import statistics
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from environments import REGISTRY  # noqa: E402
from environments.count_primes_v2 import CountPrimesV2Env  # noqa: E402
from environments.power_mod import BASE, MODULUS, PowerModEnv  # noqa: E402
from environments.optimize_function import _validate_candidate  # noqa: E402


class RegistryWiring(unittest.TestCase):
    def test_new_tasks_are_registered(self):
        self.assertIn("count_primes_v2", REGISTRY)
        self.assertIn("power_mod", REGISTRY)

    def test_v1_tasks_are_still_registered(self):
        """Prior records referenced these; removing them would strand evidence."""
        self.assertIn("count_primes", REGISTRY)
        self.assertIn("sum_digits", REGISTRY)


class SolutionsAreInsideTheValidatorSubset(unittest.TestCase):
    """Reference solutions the audit relies on must actually be admissible."""

    def test_every_anchor_solution_validates(self):
        for factory in (CountPrimesV2Env, PowerModEnv):
            for attribute in ("starting_solution", "reference_solution"):
                source = getattr(factory, attribute).fget(factory)  # type: ignore[attr-defined]
                _, failure = _validate_candidate(source)
                self.assertIsNone(
                    failure, msg=f"{factory.__name__}.{attribute}: {failure}"
                )


class OracleAgreement(unittest.TestCase):
    """The parent-side oracle and the reference must agree, or scoring is a lie."""

    def test_count_primes_oracle_matches_a_simple_sieve(self):
        env = CountPrimesV2Env.__new__(CountPrimesV2Env)  # no timing needed
        for n in (-5, 0, 1, 2, 3, 4, 10, 100, 541, 1000):
            expected = sum(
                1
                for value in range(max(0, n))
                if value > 1
                and all(value % d for d in range(2, int(value**0.5) + 1))
            )
            self.assertEqual(env.oracle(n), expected, msg=f"n={n}")

    def test_power_mod_oracle_matches_builtin_pow(self):
        env = PowerModEnv.__new__(PowerModEnv)
        for n in (-3, 0, 1, 2, 17, 1023, 4096):
            expected = 1 if n <= 0 else pow(BASE, n, MODULUS)
            self.assertEqual(env.oracle(n), expected, msg=f"n={n}")


class RewardContract(unittest.TestCase):
    """One environment is enough to pin the shared base-class behaviour."""

    @classmethod
    def setUpClass(cls):
        cls.env = PowerModEnv()

    def test_reference_is_faster_than_starting(self):
        anchors = self.env.baseline_report()
        self.assertLess(anchors["reference_seconds"], anchors["starting_seconds"])
        self.assertGreater(anchors["speedup_factor"], 1.0)

    def test_reference_scores_near_one(self):
        result = self.env.score(self.env.reference_solution)
        self.assertTrue(result.correct)
        self.assertGreater(result.reward, 0.5)

    def test_reward_is_not_clamped_below_zero(self):
        """The defect that let no-op search manufacture reward.

        A deliberately slower-but-correct solution must score negative; under
        v1's ``max(0.0, ...)`` it would have been floored at zero.
        """
        slower = (
            "def solve(n):\n"
            "    if n <= 0:\n"
            "        return 1\n"
            "    result = 1\n"
            "    for _step in range(n):\n"
            f"        result = result * {BASE} % {MODULUS}\n"
            "    for _pad in range(n):\n"
            "        result = result + 0\n"
            "    return result\n"
        )
        result = self.env.score(slower)
        self.assertTrue(result.correct, msg=result.detail)
        self.assertLess(result.reward, 0.0)

    def test_incorrect_solution_is_rejected_before_timing(self):
        wrong = "def solve(n):\n    return 0\n"
        result = self.env.score(wrong)
        self.assertFalse(result.correct)
        self.assertEqual(result.reward, -1.0)

    def test_imports_are_refused(self):
        result = self.env.score("import os\ndef solve(n):\n    return 1\n")
        self.assertFalse(result.correct)
        self.assertEqual(result.reward, -1.0)

    def test_correctness_only_scoring_ignores_timing(self):
        result = self.env.score_correctness(self.env.reference_solution)
        self.assertTrue(result.correct)
        self.assertEqual(result.reward, 1.0)
        self.assertIsNone(result.raw)


class HeadroomIsRequired(unittest.TestCase):
    def test_construction_fails_without_headroom(self):
        """A task whose reference is no faster than its start cannot be scored."""

        class Degenerate(PowerModEnv):
            name = "degenerate_power_mod"

            @property
            def reference_solution(self) -> str:
                return self.starting_solution + "\n# identical\n"

        with self.assertRaises(RuntimeError):
            Degenerate()


class CensoringLooksLikePrecision(unittest.TestCase):
    """A reward that floors everything to zero passes naive noise criteria.

    This is the E64 finding: ``count_primes`` v1, the task E63 rejected as the
    worst in the suite, was *admitted* in E64 with a null standard deviation of
    exactly zero -- because the run's import-time baseline landed on the fast
    side, every null variant came out slower, and ``max(0.0, ...)`` floored all
    of them to 0.0. Zero variance from censoring is indistinguishable from zero
    variance from precision unless signal is measured too, and a signal ratio is
    undefined precisely when the null spread is zero.
    """

    def test_zero_spread_makes_signal_to_noise_undefined(self):
        null_rewards = [0.0] * 30
        spread = statistics.pstdev(null_rewards)
        self.assertEqual(spread, 0.0)
        # This is the division the audit cannot perform, which is why an
        # undefined ratio must be treated as a failure rather than a pass.
        with self.assertRaises(ZeroDivisionError):
            (1.0 - statistics.fmean(null_rewards)) / spread

    def test_undefined_ratio_must_not_count_as_supported(self):
        """Pins the corrected H5 rule against the bug that shipped in E64."""
        threshold = 5.0
        ratios = {"a": None, "b": None}
        buggy = all(v is None or v >= threshold for v in ratios.values())
        corrected = bool(ratios) and all(
            v is not None and v >= threshold for v in ratios.values()
        )
        self.assertTrue(buggy, "the original rule passed undefined ratios")
        self.assertFalse(corrected, "the corrected rule must fail them")

    def test_corrected_rule_still_accepts_real_ratios(self):
        threshold = 5.0
        ratios = {"a": 19.9, "b": 7.2}
        self.assertTrue(
            bool(ratios)
            and all(v is not None and v >= threshold for v in ratios.values())
        )


if __name__ == "__main__":
    unittest.main()
