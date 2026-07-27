"""Tasks needing real algorithms, admissible under the widened subset.

E75 showed the suite has zero capability variance: eight of nine tasks score
exactly 1.0 against the 12B proposer, because the narrow subset can only express
single-function integer manipulation.  ``recursive_lab.widened_validator``
removes that ceiling while keeping the properties the grading protocol depends
on, so tasks can finally require data structures and algorithms.

Each task still has the shape the harness needs -- one integer in, one integer
out -- but the work in between needs strings, lists or dictionaries.  Whether any
of them produces the graded partial credit that has eluded every previous design
is measured, not assumed.
"""

from __future__ import annotations

import textwrap

from recursive_lab.widened_validator import validate_widened

from .graded_correctness import GradedCorrectnessEnvironment

_RULES = (
    "Return only a Python module defining solve(n), inside a single ```python "
    "fenced block. You may use lists, tuples, dicts, sets, strings, slicing, "
    "comprehensions and helper functions. No imports, no classes, no lambda, no "
    "try/except, and no names containing double underscores. Available builtins: "
    "abs, all, any, bool, chr, dict, divmod, enumerate, filter, float, "
    "frozenset, int, len, list, map, max, min, ord, pow, range, reversed, round, "
    "set, sorted, str, sum, tuple, zip."
)


class WidenedGradedEnvironment(GradedCorrectnessEnvironment):
    """Graded correctness, validated against the widened subset."""

    def score(self, solution_source: str):
        from .base import ScoreResult

        _, failure = validate_widened(solution_source)
        if failure:
            return ScoreResult(-1.0, False, None, failure)
        passed = self._count_passed(solution_source)
        reward = (passed - self.starting_passed) / self.headroom_cases
        return ScoreResult(
            reward,
            passed == self.total_cases,
            float(passed),
            f"{passed}/{self.total_cases} hidden cases (norm {reward:.3f})",
        )


class LongestPalindromeEnv(WidenedGradedEnvironment):
    """Longest palindromic substring of the decimal digits of |n|."""

    name = "longest_palindrome"

    @property
    def task_prompt(self) -> str:
        return textwrap.dedent(
            f"""\
            solve(n) must return the length of the longest palindromic substring
            of the decimal representation of the absolute value of n. A single
            digit counts as a palindrome of length 1, so the answer is at least
            1 for any n. solve(0) is 1.

            For example solve(12321) = 5, solve(1223) = 2, solve(-9119) = 4.

            {_RULES}
            """
        )

    @property
    def starting_solution(self) -> str:
        # Only detects whole-string palindromes; otherwise returns 1.
        return (
            "def solve(n):\n"
            "    s = str(abs(n))\n"
            "    if s == s[::-1]:\n"
            "        return len(s)\n"
            "    return 1\n"
        )

    @property
    def reference_solution(self) -> str:
        return (
            "def solve(n):\n"
            "    s = str(abs(n))\n"
            "    best = 1\n"
            "    for i in range(len(s)):\n"
            "        for j in range(i + 1, len(s) + 1):\n"
            "            part = s[i:j]\n"
            "            if part == part[::-1] and len(part) > best:\n"
            "                best = len(part)\n"
            "    return best\n"
        )

    @property
    def hidden_cases(self) -> tuple[int, ...]:
        # Weighted toward numbers whose longest palindrome is a PROPER
        # substring. An earlier draft used mostly whole-string palindromes,
        # which the naive solution gets right, and the construction guard
        # rejected the task at 19/20 passing.
        return (
            0, 45, 123456,
            1223, 12234, 51150, 778, 4456, 199299, 123321456,
            9008, 1441000, 22345, 678876123, 30313,
            12321, 9119, -1223, -51150, -4456,
        )

    def oracle(self, n: int) -> int:
        s = str(abs(n))
        best = 1
        for i in range(len(s)):
            for j in range(i + 1, len(s) + 1):
                part = s[i:j]
                if part == part[::-1] and len(part) > best:
                    best = len(part)
        return best


class CoinChangeEnv(WidenedGradedEnvironment):
    """Fewest coins from {1, 3, 4} summing to n. Needs dynamic programming."""

    name = "coin_change"

    @property
    def task_prompt(self) -> str:
        return textwrap.dedent(
            f"""\
            solve(n) must return the FEWEST number of coins, with denominations
            1, 3 and 4, that sum to exactly n. solve(0) is 0. For n < 0 return
            -1.

            Note that a greedy choice is not always optimal: solve(6) is 2
            (3 + 3), not 3 (4 + 1 + 1).

            {_RULES}
            """
        )

    @property
    def starting_solution(self) -> str:
        # Greedy, which is wrong for values like 6.
        return (
            "def solve(n):\n"
            "    if n < 0:\n"
            "        return -1\n"
            "    count = 0\n"
            "    left = n\n"
            "    for coin in [4, 3, 1]:\n"
            "        count += left // coin\n"
            "        left = left % coin\n"
            "    return count\n"
        )

    @property
    def reference_solution(self) -> str:
        return (
            "def solve(n):\n"
            "    if n < 0:\n"
            "        return -1\n"
            "    best = [0] + [n + 1] * n\n"
            "    for amount in range(1, n + 1):\n"
            "        for coin in [1, 3, 4]:\n"
            "            if coin <= amount and best[amount - coin] + 1 < best[amount]:\n"
            "                best[amount] = best[amount - coin] + 1\n"
            "    return best[n]\n"
        )

    @property
    def hidden_cases(self) -> tuple[int, ...]:
        return (
            -3, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 17, 23, 30, 41, 55, 60,
        )

    def oracle(self, n: int) -> int:
        if n < 0:
            return -1
        best = [0] + [n + 1] * n
        for amount in range(1, n + 1):
            for coin in (1, 3, 4):
                if coin <= amount and best[amount - coin] + 1 < best[amount]:
                    best[amount] = best[amount - coin] + 1
        return best[n]


__all__ = ["CoinChangeEnv", "LongestPalindromeEnv", "WidenedGradedEnvironment"]
