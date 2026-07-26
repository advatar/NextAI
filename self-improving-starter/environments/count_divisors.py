"""Count the divisors of n: an O(n) -> O(sqrt n) task.

E66 left the suite with two admissible tasks, and two is thin.  It also showed
what decides admissibility: headroom.  ``power_mod`` cleared every criterion with
669x between its anchors, while ``count_primes_v2`` failed on phantom gain with
only 22x.  A third task therefore needs a large, honest gap between the naive and
reference solutions.

It also needs a *different* optimisation to the two already admitted.
``optimize_function`` is solved by recalling a closed form and ``power_mod`` by
binary exponentiation; both reward a single algebraic insight.  This task is
solved by observing that divisors come in pairs around the square root, so
trial division can stop at ``sqrt(n)``.  The gain is roughly ``sqrt(n) / 2``,
which at the timing argument is a few hundred times, and it comes from bounding
a loop rather than from replacing one.

Both solutions stay inside the candidate subset: integer arithmetic, ``while``,
``for``, ``if`` and ``range`` only, with no calls but ``range``.  In particular
the reference avoids ``math.isqrt`` by testing ``d * d < n``, which is also why
the perfect-square case needs its own final check.
"""

from __future__ import annotations

import textwrap

from .timed_task import TimedTaskEnvironment


class CountDivisorsEnv(TimedTaskEnvironment):
    name = "count_divisors"
    #: Large enough that the naive scan dominates process overhead, giving the
    #: reference several hundred times of honest headroom.
    timing_argument = 200_000

    @property
    def task_prompt(self) -> str:
        return textwrap.dedent(
            """\
            Make solve(n) as fast as possible.

            Contract (must not change): solve(n) returns the number of positive
            integers that divide n exactly, for every integer n >= 1, and
            returns 0 for n <= 0.

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
            "    total = 0\n"
            "    for d in range(1, n + 1):\n"
            "        if n % d == 0:\n"
            "            total += 1\n"
            "    return total\n"
        )

    @property
    def reference_solution(self) -> str:
        return (
            "def solve(n):\n"
            "    if n <= 0:\n"
            "        return 0\n"
            "    total = 0\n"
            "    d = 1\n"
            "    while d * d < n:\n"
            "        if n % d == 0:\n"
            "            total += 2\n"
            "        d += 1\n"
            "    if d * d == n:\n"
            "        total += 1\n"
            "    return total\n"
        )

    @property
    def correctness_cases(self) -> tuple[int, ...]:
        # Includes perfect squares (1, 4, 36, 10000), a prime (97), a highly
        # composite number (720) and the timing argument itself.
        return (-5, 0, 1, 2, 4, 6, 12, 28, 36, 97, 720, 10_000, 200_000)

    def oracle(self, n: int) -> int:
        if n <= 0:
            return 0
        total = 0
        d = 1
        while d * d < n:
            if n % d == 0:
                total += 2
            d += 1
        if d * d == n:
            total += 1
        return total


__all__ = ["CountDivisorsEnv"]
