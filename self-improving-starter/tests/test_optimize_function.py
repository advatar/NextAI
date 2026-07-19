from __future__ import annotations

import unittest
from unittest import mock

from environments.optimize_function import (
    OptimizeFunctionEnv,
    _correctness_cases,
    _reference_value,
    _validate_candidate,
)


class OptimizeFunctionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.env = OptimizeFunctionEnv(trusted_local_fixture=True)

    def test_starting_solution_is_correct_but_not_a_promotion(self) -> None:
        result = self.env.score("\n" + self.env.starting_solution + "\n")

        self.assertTrue(result.correct, result.detail)
        self.assertEqual(result.reward, 0.0)
        self.assertIsNotNone(result.raw)

    def test_live_default_refuses_host_fallback_when_container_is_unavailable(self) -> None:
        with mock.patch(
            "environments.optimize_function.container_runtime_available",
            return_value=False,
        ):
            with self.assertRaisesRegex(RuntimeError, "Refusing to execute"):
                OptimizeFunctionEnv()

    def test_reference_solution_passes_and_scores_near_one(self) -> None:
        result = self.env.score(self.env._REFERENCE_SOLUTION)

        self.assertTrue(result.correct, result.detail)
        self.assertGreater(result.reward, 0.7)
        self.assertLess(result.reward, 1.3)

    def test_wrong_formula_fails_external_correctness_gate(self) -> None:
        result = self.env.score("def solve(n):\n    return n * n\n")

        self.assertFalse(result.correct)
        self.assertEqual(result.reward, -1.0)
        self.assertIsNone(result.raw)
        self.assertIn("protocol", result.detail)

    def test_old_fixed_case_hardcoding_does_not_pass(self) -> None:
        candidate = (
            "def solve(n):\n"
            "    if n == 0 or n == 1 or n == 2 or n == 10 or n == 1000 or n == 50000:\n"
            "        return (n - 1) * n * (2 * n - 1) // 6 if n > 0 else 0\n"
            "    return 0\n"
        )
        result = self.env.score(candidate)

        self.assertFalse(result.correct)
        self.assertEqual(result.reward, -1.0)

    def test_hidden_cases_are_randomized_but_deterministic(self) -> None:
        first = _correctness_cases()
        second = _correctness_cases()

        self.assertEqual(first, second)
        self.assertGreaterEqual(len(first), 30)
        self.assertTrue(any(n not in {0, 1, 2, 10, 1000, 50_000} for n in first))
        self.assertTrue(all(_reference_value(n) == sum(i * i for i in range(n)) for n in first))

    def test_forged_ok_output_is_rejected_before_execution(self) -> None:
        candidate = (
            "print('OK MEDIAN -1000000')\n"
            "def solve(n):\n"
            "    return (n - 1) * n * (2 * n - 1) // 6 if n > 0 else 0\n"
        )
        result = self.env.score(candidate)

        self.assertFalse(result.correct)
        self.assertIn("rejected", result.detail)

    def test_import_introspection_early_exit_and_top_level_effects_fail_closed(self) -> None:
        rejected = {
            "import": "import os\ndef solve(n):\n    return 0\n",
            "introspection": "def solve(n):\n    return n.__class__\n",
            "early exit": "def solve(n):\n    raise SystemExit(0)\n",
            "top-level assignment": "value = 1\ndef solve(n):\n    return value\n",
            "function output": "def solve(n):\n    print('forged')\n    return 0\n",
            "default effect": "def solve(n=range(1)):\n    return 0\n",
        }
        for label, source in rejected.items():
            with self.subTest(label=label):
                result = self.env.score(source)
                self.assertFalse(result.correct)
                self.assertEqual(result.reward, -1.0)
                self.assertIn("rejected", result.detail)

    def test_candidate_cannot_read_harness_state_to_cheat_timing(self) -> None:
        candidate = (
            "def solve(n):\n"
            "    if n == 100000 and _h_index != 21:\n"
            "        return 0\n"
            "    total = 0\n"
            "    for i in range(n):\n"
            "        total += i * i\n"
            "    return total\n"
        )

        result = self.env.score(candidate)

        self.assertFalse(result.correct)
        self.assertEqual(result.reward, -1.0)
        self.assertIn("globals", result.detail)

    def test_safe_ast_accepts_baseline_and_closed_form(self) -> None:
        for source in (self.env.starting_solution, self.env._REFERENCE_SOLUTION):
            with self.subTest(source=source):
                tree, error = _validate_candidate(source)
                self.assertIsNotNone(tree)
                self.assertIsNone(error)

    def test_protocol_rejects_nan_infinity_zero_negative_and_extra_output(self) -> None:
        nonce = "Ptestnonce"
        cases = (-1, 0, 7, 1234)
        prefix = "\n".join(
            f"{nonce} RESULT {index} {_reference_value(n)}"
            for index, n in enumerate(cases)
        )
        for bad_metric in ("nan", "NaN", "inf", "-inf", "0", "-0.0", "-1"):
            with self.subTest(metric=bad_metric):
                stdout = prefix + f"\n{nonce} TIMING {bad_metric}\n"
                self.assertIsNone(self.env._parse_protocol(stdout, cases, nonce))

        valid = prefix + f"\n{nonce} TIMING 0.000001\n"
        self.assertEqual(self.env._parse_protocol(valid, cases, nonce), 0.000001)
        self.assertIsNone(
            self.env._parse_protocol("forged\n" + valid, cases, nonce)
        )


if __name__ == "__main__":
    unittest.main()
