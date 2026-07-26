"""Modular exponentiation: a task whose optimum is an algorithm, not a formula.

E63 admitted exactly one task, ``optimize_function``, and noted that one sound
task is not a benchmark.  It has a further weakness for search work: its optimum
is a closed form, ``(n-1)n(2n-1)/6``, so a loop run on it is rediscovering an
algebraic identity.  A suite consisting only of that measures a narrow thing.

This task's optimum is *algorithmic*.  ``solve(n)`` returns ``BASE ** n mod
MODULUS``; the starting solution multiplies ``n`` times, and the reference uses
binary exponentiation, which is O(log n).  There is no closed form to recall --
the improvement is a change in control flow -- and the headroom grows with the
timing argument rather than being fixed.

Both solutions stay inside the validator's subset: binary exponentiation needs
only ``while``, ``if``, ``&``, ``>>``, ``*`` and ``%``, all of which are
permitted, and neither solution calls anything except ``range``.
"""

from __future__ import annotations

import textwrap

from .timed_task import TimedTaskEnvironment

BASE = 7
MODULUS = 1_000_000_007


class PowerModEnv(TimedTaskEnvironment):
    name = "power_mod"
    timing_argument = 20000

    @property
    def task_prompt(self) -> str:
        return textwrap.dedent(
            f"""\
            Make solve(n) as fast as possible.

            Contract (must not change): solve(n) returns
            ({BASE} ** n) % {MODULUS} for every integer n >= 0, and returns 1
            for n <= 0.

            Return only a Python module defining solve(n). No imports and no
            I/O. Use only integer arithmetic, comparisons, loops, conditionals,
            local variables and range().
            """
        )

    @property
    def starting_solution(self) -> str:
        return (
            "def solve(n):\n"
            "    result = 1\n"
            "    for _step in range(n):\n"
            f"        result = result * {BASE} % {MODULUS}\n"
            "    return result\n"
        )

    @property
    def reference_solution(self) -> str:
        return (
            "def solve(n):\n"
            "    if n <= 0:\n"
            "        return 1\n"
            "    result = 1\n"
            f"    base = {BASE} % {MODULUS}\n"
            "    exponent = n\n"
            "    while exponent > 0:\n"
            "        if exponent & 1:\n"
            f"            result = result * base % {MODULUS}\n"
            f"        base = base * base % {MODULUS}\n"
            "        exponent = exponent >> 1\n"
            "    return result\n"
        )

    @property
    def correctness_cases(self) -> tuple[int, ...]:
        return (-5, 0, 1, 2, 3, 7, 16, 17, 100, 1023, 4096, 20000)

    def oracle(self, n: int) -> int:
        if n <= 0:
            return 1
        return pow(BASE, n, MODULUS)


__all__ = ["PowerModEnv", "BASE", "MODULUS"]
