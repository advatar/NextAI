"""Four graded-correctness tasks with plausible but incomplete starting points.

Each starting solution handles the common path and fails a documented class of
inputs — negative numbers, zero, a boundary. That is the shape of the fix a
coding agent is actually asked to make, and unlike a speedup it is measured
exactly rather than timed.

Headroom here is a count of broken cases, not a speed ratio, so it does not
depend on the machine at all.
"""

from __future__ import annotations

import textwrap

from .graded_correctness import GradedCorrectnessEnvironment

_RULES = (
    "Return only a Python module defining solve(n). No imports and no I/O. "
    "Use only integer arithmetic, comparisons, loops, conditionals, local "
    "variables and range()."
)


class DigitSumGradedEnv(GradedCorrectnessEnvironment):
    """Starting solution ignores the sign of n."""

    name = "digit_sum_graded"

    @property
    def task_prompt(self) -> str:
        return textwrap.dedent(
            f"""\
            solve(n) must return the sum of the decimal digits of the absolute
            value of n, for every integer n. solve(0) is 0.

            {_RULES}
            """
        )

    @property
    def starting_solution(self) -> str:
        # Loops while value is truthy, so any negative n returns 0 immediately.
        return (
            "def solve(n):\n"
            "    value = n\n"
            "    total = 0\n"
            "    while value > 0:\n"
            "        total += value % 10\n"
            "        value //= 10\n"
            "    return total\n"
        )

    @property
    def reference_solution(self) -> str:
        return (
            "def solve(n):\n"
            "    value = n\n"
            "    if value < 0:\n"
            "        value = -value\n"
            "    total = 0\n"
            "    while value > 0:\n"
            "        total += value % 10\n"
            "        value //= 10\n"
            "    return total\n"
        )

    @property
    def hidden_cases(self) -> tuple[int, ...]:
        return (
            -987654, -10001, -100, -45, -9, -1, 0, 1, 9, 45, 100, 10001,
            987654, 555, -555, 1000000,
        )

    def oracle(self, n: int) -> int:
        value = -n if n < 0 else n
        total = 0
        while value > 0:
            total += value % 10
            value //= 10
        return total


class CountOneBitsEnv(GradedCorrectnessEnvironment):
    """Starting solution mishandles negative inputs."""

    name = "count_one_bits"

    @property
    def task_prompt(self) -> str:
        return textwrap.dedent(
            f"""\
            solve(n) must return the number of 1 bits in the binary
            representation of the absolute value of n, for every integer n.
            solve(0) is 0.

            {_RULES}
            """
        )

    @property
    def starting_solution(self) -> str:
        # A negative n makes `n >> 1` converge to -1, never 0, so the loop would
        # not terminate; the guard returns 0 instead, which is wrong.
        return (
            "def solve(n):\n"
            "    if n < 0:\n"
            "        return 0\n"
            "    total = 0\n"
            "    value = n\n"
            "    while value > 0:\n"
            "        total += value & 1\n"
            "        value = value >> 1\n"
            "    return total\n"
        )

    @property
    def reference_solution(self) -> str:
        return (
            "def solve(n):\n"
            "    value = n\n"
            "    if value < 0:\n"
            "        value = -value\n"
            "    total = 0\n"
            "    while value > 0:\n"
            "        total += value & 1\n"
            "        value = value >> 1\n"
            "    return total\n"
        )

    @property
    def hidden_cases(self) -> tuple[int, ...]:
        return (
            -255, -128, -7, -3, -1, 0, 1, 3, 7, 8, 15, 16, 255, 256, 1023,
            4096, 65535,
        )

    def oracle(self, n: int) -> int:
        value = -n if n < 0 else n
        total = 0
        while value > 0:
            total += value & 1
            value >>= 1
        return total


class CollatzStepsEnv(GradedCorrectnessEnvironment):
    """Starting solution returns the wrong sentinel for non-positive n.

    Note the starting solution must still *terminate* on every hidden case. An
    earlier draft omitted the ``n <= 0`` guard entirely, and ``solve(0)`` then
    looped forever: 0 is even, so halving leaves it at 0. The subprocess hit its
    timeout, the whole run failed, and the task scored 0/15 — which looks like
    enormous headroom but actually means the task was unusable, and it also made
    negative rewards impossible because nothing passed to begin with.
    """

    name = "collatz_steps"

    @property
    def task_prompt(self) -> str:
        return textwrap.dedent(
            f"""\
            solve(n) must return the number of Collatz steps needed to reach 1
            from n, where an even value is halved and an odd value becomes
            3n + 1. solve(1) is 0. For n <= 0, return -1.

            {_RULES}
            """
        )

    @property
    def starting_solution(self) -> str:
        # Terminates everywhere, but returns 0 rather than -1 for n <= 0.
        return (
            "def solve(n):\n"
            "    if n <= 0:\n"
            "        return 0\n"
            "    value = n\n"
            "    steps = 0\n"
            "    while value != 1:\n"
            "        if value % 2 == 0:\n"
            "            value = value // 2\n"
            "        else:\n"
            "            value = 3 * value + 1\n"
            "        steps += 1\n"
            "    return steps\n"
        )

    @property
    def reference_solution(self) -> str:
        return (
            "def solve(n):\n"
            "    if n <= 0:\n"
            "        return -1\n"
            "    value = n\n"
            "    steps = 0\n"
            "    while value != 1:\n"
            "        if value % 2 == 0:\n"
            "            value = value // 2\n"
            "        else:\n"
            "            value = 3 * value + 1\n"
            "        steps += 1\n"
            "    return steps\n"
        )

    @property
    def hidden_cases(self) -> tuple[int, ...]:
        return (
            -100, -5, -1, 0, 1, 2, 3, 4, 6, 7, 9, 27, 97, 871, 6171, 77031,
        )

    def oracle(self, n: int) -> int:
        if n <= 0:
            return -1
        value = n
        steps = 0
        while value != 1:
            value = value // 2 if value % 2 == 0 else 3 * value + 1
            steps += 1
        return steps


class IntegerSqrtEnv(GradedCorrectnessEnvironment):
    """Starting solution is off by one on perfect squares."""

    name = "integer_sqrt"

    @property
    def task_prompt(self) -> str:
        return textwrap.dedent(
            f"""\
            solve(n) must return the largest integer r with r * r <= n, for
            every integer n >= 0. For n < 0, return -1.

            {_RULES}
            """
        )

    @property
    def starting_solution(self) -> str:
        # Stops at the first r with r * r >= n, overshooting on perfect squares
        # and on most non-squares, and has no negative guard.
        return (
            "def solve(n):\n"
            "    r = 0\n"
            "    while r * r < n:\n"
            "        r += 1\n"
            "    return r\n"
        )

    @property
    def reference_solution(self) -> str:
        return (
            "def solve(n):\n"
            "    if n < 0:\n"
            "        return -1\n"
            "    r = 0\n"
            "    while (r + 1) * (r + 1) <= n:\n"
            "        r += 1\n"
            "    return r\n"
        )

    @property
    def hidden_cases(self) -> tuple[int, ...]:
        return (-4, -1, 0, 1, 2, 3, 4, 5, 8, 9, 10, 15, 16, 17, 99, 100, 101, 10000)

    def oracle(self, n: int) -> int:
        if n < 0:
            return -1
        r = 0
        while (r + 1) * (r + 1) <= n:
            r += 1
        return r


__all__ = [
    "DigitSumGradedEnv",
    "CountOneBitsEnv",
    "CollatzStepsEnv",
    "IntegerSqrtEnv",
]
