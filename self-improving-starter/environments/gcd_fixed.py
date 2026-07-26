"""Greatest common divisor with a fixed constant: an O(n) -> O(log n) task.

E67 admitted two tasks against a readiness bar of three, so the suite needs
another with large headroom. It also needs a *different* insight: the suite so
far rewards recalling a closed form (``optimize_function``), binary
exponentiation (``power_mod``) and bounding a loop at ``sqrt(n)``
(``count_divisors``).

This task is solved by the Euclidean algorithm. The naive solution scans every
integer up to ``n`` looking for the largest common divisor; the reference
replaces the scan entirely with repeated remainders, which terminates in
O(log n) steps. Nothing about it is recoverable by tightening a bound — the loop
has to be thrown away and replaced — so it probes a different kind of
improvement from anything already in the suite.

Both solutions stay inside the candidate subset: integer arithmetic, ``while``,
``if``, boolean operators, comparisons and ``range`` only.
"""

from __future__ import annotations

import textwrap

from .timed_task import TimedTaskEnvironment

#: A fixed second operand, held constant so ``solve`` keeps a one-argument
#: signature. Composite with several distinct prime factors, so the answer is
#: not trivially 1 for most inputs.
CONSTANT = 963_761_198_400  # 2^7 * 3^4 * 5^2 * 7^2 * 11 * 13 * 17 * 19 * 23


class GcdFixedEnv(TimedTaskEnvironment):
    name = "gcd_fixed"
    #: Chosen so a single naive call costs roughly a millisecond.  That matters
    #: as much as headroom: at 120_000 the naive scan took ~7 ms, which exceeds
    #: the calibration target on its own, so batches held only 2-3 calls and two
    #: identical programs measured ratios between 1.00 and 1.48.  Euclid is
    #: O(log n), so shrinking the argument costs almost no headroom.
    timing_argument = 20_000

    @property
    def task_prompt(self) -> str:
        return textwrap.dedent(
            f"""\
            Make solve(n) as fast as possible.

            Contract (must not change): solve(n) returns the greatest common
            divisor of n and {CONSTANT} for every integer n >= 1, and returns 0
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
            "    if n <= 0:\n"
            "        return 0\n"
            "    best = 1\n"
            "    d = 1\n"
            "    while d <= n:\n"
            f"        if n % d == 0 and {CONSTANT} % d == 0:\n"
            "            best = d\n"
            "        d += 1\n"
            "    return best\n"
        )

    @property
    def reference_solution(self) -> str:
        return (
            "def solve(n):\n"
            "    if n <= 0:\n"
            "        return 0\n"
            "    a = n\n"
            f"    b = {CONSTANT}\n"
            "    while b > 0:\n"
            "        t = b\n"
            "        b = a % b\n"
            "        a = t\n"
            "    return a\n"
        )

    @property
    def correctness_cases(self) -> tuple[int, ...]:
        # Coprime (7919 is prime and not a factor), sharing single factors,
        # sharing many factors, and the timing argument itself.
        return (-3, 0, 1, 2, 7, 13, 64, 121, 7919, 5040, 100_000, 120_000)

    def oracle(self, n: int) -> int:
        if n <= 0:
            return 0
        a, b = n, CONSTANT
        while b:
            a, b = b, a % b
        return a


__all__ = ["GcdFixedEnv", "CONSTANT"]
