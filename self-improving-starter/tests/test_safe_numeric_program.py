from __future__ import annotations

import unittest

from recursive_lab.safe_numeric_program import (
    NumericProgramError,
    evaluate_solve,
    parse_solve_expression,
)


class SafeNumericProgramTests(unittest.TestCase):
    def test_piecewise_integer_expression_evaluates_without_exec(self) -> None:
        sources = (
            "def solve(n):\n"
            "    return n**3 + 2*n + 5 if n >= 0 else n*n - 3*n + 11\n",
            "def solve(n):\n"
            "    if n >= 0:\n"
            "        return n**3 + 2*n + 5\n"
            "    else:\n"
            "        return n*n - 3*n + 11\n",
        )
        for source in sources:
            with self.subTest(source=source):
                expression = parse_solve_expression(source)
                self.assertEqual(evaluate_solve(expression, 2), 17)
                self.assertEqual(evaluate_solve(expression, -2), 21)

    def test_effects_calls_attributes_and_extra_statements_are_rejected(self) -> None:
        rejected = (
            "import os\ndef solve(n):\n return n\n",
            "def solve(n):\n return print(n)\n",
            "def solve(n):\n return n.__class__\n",
            "def solve(n):\n x=n\n return x\n",
            "def solve(n):\n return globals()['x']\n",
        )
        for source in rejected:
            with self.subTest(source=source):
                with self.assertRaises(NumericProgramError):
                    parse_solve_expression(source)

    def test_unbounded_power_and_non_integer_constants_are_rejected(self) -> None:
        for source in (
            "def solve(n):\n return n**100\n",
            "def solve(n):\n return 1.5*n\n",
            "def solve(n):\n return 'x'\n",
        ):
            with self.subTest(source=source):
                with self.assertRaises(NumericProgramError):
                    parse_solve_expression(source)
