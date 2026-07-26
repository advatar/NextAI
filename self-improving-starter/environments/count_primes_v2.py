"""``count_primes`` rebuilt on a reward that does not pay for noise.

The v1 environment is left untouched: experiments E5, E9 and others were scored
against it, and rewriting it would silently change what that recorded evidence
means.  This is a separate task id so the repair is auditable as a diff and the
old records stay interpretable.

What changed, all inherited from :class:`~environments.timed_task.TimedTaskEnvironment`:

* the anchors are medians of calibrated repeat batches rather than one sample
  taken at import time;
* the reward is unclamped, per ``base.py``'s documented ``[<0, ~1+]`` contract,
  so a slower candidate scores negative instead of being floored at zero;
* a held-out reference solution defines the 1.0 point, so the scale means
  something.

The contract is unchanged: ``solve(n)`` returns the exact count of primes below
``n`` for every integer ``n``.  The starting solution is trial division by every
smaller integer; the reference stops at the square root and skips even divisors,
which is roughly a two-order-of-magnitude speedup at the timing argument.
"""

from __future__ import annotations

import textwrap

from .timed_task import TimedTaskEnvironment


class CountPrimesV2Env(TimedTaskEnvironment):
    name = "count_primes_v2"
    timing_argument = 2000

    @property
    def task_prompt(self) -> str:
        return textwrap.dedent(
            """\
            Make solve(n) count prime integers below n as fast as possible.

            Contract (must not change): solve(n) returns the exact number of
            primes strictly below n, for every integer n, including n <= 0.

            Return only a Python module defining solve(n). No imports and no
            I/O. Use only integer arithmetic, comparisons, loops, conditionals,
            local variables and range().
            """
        )

    @property
    def starting_solution(self) -> str:
        return (
            "def solve(n):\n"
            "    total = 0\n"
            "    for value in range(n):\n"
            "        if value > 1:\n"
            "            prime = 1\n"
            "            for divisor in range(2, value):\n"
            "                if value % divisor == 0:\n"
            "                    prime = 0\n"
            "                    break\n"
            "            total += prime\n"
            "    return total\n"
        )

    @property
    def reference_solution(self) -> str:
        return (
            "def solve(n):\n"
            "    if n <= 2:\n"
            "        return 0\n"
            "    total = 1\n"
            "    for value in range(3, n, 2):\n"
            "        prime = 1\n"
            "        divisor = 3\n"
            "        while divisor * divisor <= value:\n"
            "            if value % divisor == 0:\n"
            "                prime = 0\n"
            "                break\n"
            "            divisor += 2\n"
            "        total += prime\n"
            "    return total\n"
        )

    @property
    def correctness_cases(self) -> tuple[int, ...]:
        return (-10, 0, 1, 2, 3, 4, 10, 100, 541, 999, 1000, 2000)

    def oracle(self, n: int) -> int:
        if n <= 2:
            return 0
        total = 1
        for value in range(3, n, 2):
            prime = True
            divisor = 3
            while divisor * divisor <= value:
                if value % divisor == 0:
                    prime = False
                    break
                divisor += 2
            total += int(prime)
        return total


__all__ = ["CountPrimesV2Env"]
