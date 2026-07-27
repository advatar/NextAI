"""Tasks with several independent bugs. The premise failed: see MEASURED OUTCOME.

E71 measured a local model solving all four E69 tasks on held-out cases, three
of them in a single proposal, with every governed run making exactly ONE
promotion.  That makes those tasks useless for the question the project actually
cares about: they measure whether a model can fix a bug, not whether one search
procedure is better than another.  Nothing about *how* you search can show up
when one shot suffices.

These tasks are built to discriminate.  Each contract has several independent
clauses, and each starting solution violates several of them in ways that affect
**disjoint** sets of inputs.  Three consequences follow:

* **Partial credit is meaningful.**  Fixing one clause moves the score by a known
  amount, so "passes 7 of 18" is a real gradient rather than a pass/fail bit.
* **One proposal is unlikely to fix everything.**  The model must coordinate
  several edits that do not interact, which is where iteration and feedback have
  something to contribute.
* **Regressions are visible.**  A candidate that fixes one clause while breaking
  another scores worse, so the reward can distinguish progress from churn.

MEASURED OUTCOME: THE DESIGN DOES NOT WORK.

Whether they are hard enough was treated as an empirical question, and the answer
is no.  With eight proposals per task from the local Gemma 4 E2B model at
temperature 1.3:

    signed_transform   valid 8/8   one-shot solved 8/8
    bounded_counter    valid 8/8   one-shot solved 8/8
    digit_ladder       valid 2/8   one-shot solved 2/2 of the valid ones

**Difficulty is not additive across independent easy bugs.**  The premise behind
these tasks -- that several coordinated edits would defeat a single proposal --
is wrong for a language model.  It does not patch incrementally.  It reads the
contract and writes a correct implementation from scratch, so the number of bugs
in the starting solution is close to irrelevant; only the difficulty of the
contract itself matters.

A first measurement was confounded and is recorded here because the confound is
instructive: asked for an "absolute value", the model called ``abs()`` every
time, the validator rejected it, and signed_transform scored 0/8 valid.  That
looked like difficulty and was actually subset non-compliance.  Naming the
unavailable builtins in ``_RULES`` fixed it and revealed the tasks were easy all
along.  A task that fails for a reason unrelated to its content measures nothing.

These environments are retained as recorded evidence of the negative result, not
as a usable benchmark.  Making search measurable needs contracts that are hard to
implement, or specifications that are underdetermined so that feedback is
genuinely required -- not more bugs.

All solutions stay inside the candidate subset: integer arithmetic, comparisons,
loops, conditionals, local variables and ``range`` only.
"""

from __future__ import annotations

import textwrap

from .graded_correctness import GradedCorrectnessEnvironment

# The subset is stated concretely because a vague "no function calls" rule was
# measured to fail for the wrong reason: asked for an "absolute value", the model
# reached for abs() every time and the validator rejected it, so the task graded
# subset-compliance rather than bug-fixing. Naming the unavailable builtins and
# showing the idiom removes that confound. The constraint itself is unchanged --
# this clarifies the environment, it does not reveal any fix.
_RULES = (
    "Return only a Python module defining solve(n). No imports and no I/O. "
    "Use only integer arithmetic, comparisons, loops, conditionals, local "
    "variables and range(). range() is the ONLY function you may call: abs(), "
    "str(), int(), len(), sum(), max() and min() are NOT available, and neither "
    "are lists, strings or comprehensions. To take an absolute value write "
    "`v = n` then `if v < 0: v = -v`."
)


class SignedTransformEnv(GradedCorrectnessEnvironment):
    """Four clauses; the starting solution satisfies one.

    Bugs, all independent: no zero case, no sign handling, no multiple-of-three
    branch, and the fallback is wrong.
    """

    name = "signed_transform"

    @property
    def task_prompt(self) -> str:
        return textwrap.dedent(
            f"""\
            solve(n) must implement this contract exactly, for every integer n.

            Let v be the absolute value of n, and compute r from v:
              - if v is even,               r = v // 2
              - else if v is divisible by 3, r = v * 2
              - otherwise,                   r = v + 1

            Then:
              - if n is 0, return 0
              - if n is negative, return -r
              - otherwise return r

            {_RULES}
            """
        )

    @property
    def starting_solution(self) -> str:
        # Handles only positive even inputs. No sign handling, no v % 3 branch,
        # fallback returns v unchanged, and no explicit zero case.
        return (
            "def solve(n):\n"
            "    v = n\n"
            "    if v % 2 == 0:\n"
            "        return v // 2\n"
            "    return v\n"
        )

    @property
    def reference_solution(self) -> str:
        return (
            "def solve(n):\n"
            "    if n == 0:\n"
            "        return 0\n"
            "    v = n\n"
            "    if v < 0:\n"
            "        v = -v\n"
            "    if v % 2 == 0:\n"
            "        r = v // 2\n"
            "    elif v % 3 == 0:\n"
            "        r = v * 2\n"
            "    else:\n"
            "        r = v + 1\n"
            "    if n < 0:\n"
            "        return -r\n"
            "    return r\n"
        )

    @property
    def hidden_cases(self) -> tuple[int, ...]:
        return (
            0,
            2, 4, 100, 256,          # positive even
            9, 15, 21, 81,           # positive odd multiples of 3
            5, 7, 11, 25,            # positive other
            -2, -100,                # negative even
            -9, -21,                 # negative odd multiple of 3
            -5, -25,                 # negative other
        )

    def oracle(self, n: int) -> int:
        if n == 0:
            return 0
        v = -n if n < 0 else n
        if v % 2 == 0:
            r = v // 2
        elif v % 3 == 0:
            r = v * 2
        else:
            r = v + 1
        return -r if n < 0 else r


class BoundedCounterEnv(GradedCorrectnessEnvironment):
    """Counting with three independent boundary bugs.

    Counts integers in ``[1, n]`` that are divisible by 3 or 5 but not both.
    The starting solution has an off-by-one range, misses the 5 clause, and
    does not exclude the overlap.
    """

    name = "bounded_counter"

    @property
    def task_prompt(self) -> str:
        return textwrap.dedent(
            f"""\
            solve(n) must return how many integers i with 1 <= i <= n are
            divisible by 3 or by 5, but NOT by both. For n <= 0, return 0.

            {_RULES}
            """
        )

    @property
    def starting_solution(self) -> str:
        # range stops at n (excludes n), only counts multiples of 3, and does
        # not exclude values divisible by both.
        return (
            "def solve(n):\n"
            "    total = 0\n"
            "    for i in range(1, n):\n"
            "        if i % 3 == 0:\n"
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
            "    for i in range(1, n + 1):\n"
            "        by3 = i % 3 == 0\n"
            "        by5 = i % 5 == 0\n"
            "        if by3 != by5:\n"
            "            total += 1\n"
            "    return total\n"
        )

    @property
    def hidden_cases(self) -> tuple[int, ...]:
        return (
            -5, 0, 1, 2, 3, 5, 6, 9, 10, 14, 15, 16, 30, 31, 45, 60, 100, 200,
        )

    def oracle(self, n: int) -> int:
        if n <= 0:
            return 0
        total = 0
        for i in range(1, n + 1):
            if (i % 3 == 0) != (i % 5 == 0):
                total += 1
        return total


class DigitLadderEnv(GradedCorrectnessEnvironment):
    """Digit processing with independent sign, zero and accumulation bugs."""

    name = "digit_ladder"

    @property
    def task_prompt(self) -> str:
        return textwrap.dedent(
            f"""\
            solve(n) must process the decimal digits of the absolute value of n,
            from least significant to most significant, and return their
            alternating sum: the first digit is added, the second subtracted,
            the third added, and so on.

            For n = 0 return 0. For negative n, return the negation of the
            result computed for the absolute value.

            {_RULES}
            """
        )

    @property
    def starting_solution(self) -> str:
        # Adds every digit instead of alternating, ignores the sign, and its
        # loop condition mishandles n = 0 by falling through to return 0
        # correctly but for the wrong reason on negatives.
        return (
            "def solve(n):\n"
            "    v = n\n"
            "    total = 0\n"
            "    while v > 0:\n"
            "        total += v % 10\n"
            "        v = v // 10\n"
            "    return total\n"
        )

    @property
    def reference_solution(self) -> str:
        return (
            "def solve(n):\n"
            "    v = n\n"
            "    if v < 0:\n"
            "        v = -v\n"
            "    total = 0\n"
            "    sign = 1\n"
            "    while v > 0:\n"
            "        total += sign * (v % 10)\n"
            "        sign = -sign\n"
            "        v = v // 10\n"
            "    if n < 0:\n"
            "        return -total\n"
            "    return total\n"
        )

    @property
    def hidden_cases(self) -> tuple[int, ...]:
        return (
            0, 1, 5, 12, 19, 123, 456, 1010, 98765, 100000,
            -1, -12, -123, -456, -1010, -98765, 7, -7,
        )

    def oracle(self, n: int) -> int:
        v = -n if n < 0 else n
        total = 0
        sign = 1
        while v > 0:
            total += sign * (v % 10)
            sign = -sign
            v //= 10
        return -total if n < 0 else total


__all__ = ["BoundedCounterEnv", "DigitLadderEnv", "SignedTransformEnv"]
