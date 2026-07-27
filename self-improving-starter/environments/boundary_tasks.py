"""Simple contracts with one subtle boundary. MEASURED: also outside the band.

Two benchmark designs have failed to make search measurable, and the failures
bracket the problem:

* ``multibug_tasks`` -- several independent bugs, complete specification.
  One-shot solved 8/8.  Difficulty is not additive across easy bugs.
* ``inference_tasks`` -- incomplete specification.  Valid 0/5.  The model
  enumerates a lookup table instead of hypothesising a rule, and truncates.

Between "so easy it is solved in one proposal" and "so unusable nothing valid
comes out" there has to be a band where a single proposal *sometimes* works.
That band is the only place search quality can be observed: at 100% one-shot
every search procedure ties, and at 0% valid none of them has a gradient.

Exactly one task has landed there so far, by accident.  E71's ``integer_sqrt``
had a single-shot success rate of 1/3 while the governed loop reached 3/3.  Its
shape is instructive: a short, fully specified contract with **one subtle
boundary** that is easy to state and easy to get wrong -- ``r * r <= n`` versus
``(r + 1) * (r + 1) <= n``.  Not many bugs, not a missing spec; one place where
an off-by-one is natural.

These tasks copy that shape deliberately.  Each is a few lines, fully specified,
with a single boundary that invites the obvious-but-wrong choice: strict versus
non-strict comparison, the sign convention on a negative cube root, ties in
rounding, and the convention at zero.

MEASURED OUTCOME: NEITHER TASK LANDS IN THE BAND.

Eight one-shot proposals each, local Gemma 4 E2B at temperature 1.3:

    integer_cube_root    valid 0/8   one-shot 0%
    round_half_to_even   valid 0/8   one-shot 0%

Zero valid candidates again, and the failure mode is the same class as
``inference_tasks`` though a different shape.  The model degenerates into a
repetitive token loop:

    vi_vi = vi * vi
    vi_vi_vi = vi_vi * vi
    vi_vi_vi_vi = ...        <- runs to the 1400-token cap

``trailing_zero_bits`` never got that far: the construction guard rejected it
because its starting solution already passed 18 of 19 cases.  Python's floor
division handles negative inputs correctly, so the intended ``solve(0) = -1``
trap was the only case that differed.  It is retained unregistered rather than
damaged further to manufacture headroom.

CONSOLIDATED FINDING ACROSS THREE DESIGNS:

**This model's competence band is too narrow to contain a search benchmark.**

    complete spec, easy      -> one-shot solved, search unobservable
    complete spec, subtle    -> degenerates, 0 valid candidates
    incomplete spec          -> enumerates a lookup table, 0 valid candidates

The cliff is sharp: there is no measured regime in which a single proposal
*sometimes* succeeds, which is the only regime where one search procedure can be
shown better than another.  E71's ``integer_sqrt`` at 1/3 remains the sole
accidental observation, and one task is not a benchmark.

This is a property of the proposer, not of the task designs.  Testing whether a
larger model (Longemma ships ``gemma-4-12B-it-OptiQ-4bit``) has a wider band is
the obvious next step, and until something occupies that band, improver quality
cannot be measured here at all.

All solutions stay inside the candidate subset.
"""

from __future__ import annotations

import textwrap

from .graded_correctness import GradedCorrectnessEnvironment

_RULES = (
    "Return only a Python module defining solve(n). No imports and no I/O. "
    "Use only integer arithmetic, comparisons, loops, conditionals, local "
    "variables and range(). range() is the ONLY function you may call: abs(), "
    "str(), int(), len(), sum(), max() and min() are NOT available, and neither "
    "are lists, strings or comprehensions. To take an absolute value write "
    "`v = n` then `if v < 0: v = -v`."
)


class IntegerCubeRootEnv(GradedCorrectnessEnvironment):
    """Cube root truncated toward zero. The sign convention is the trap."""

    name = "integer_cube_root"

    @property
    def task_prompt(self) -> str:
        return textwrap.dedent(
            f"""\
            solve(n) must return the integer cube root of n, truncated toward
            zero: the integer r with the same sign as n and the largest absolute
            value such that |r| * |r| * |r| <= |n|. solve(0) is 0.

            For example solve(8) = 2, solve(9) = 2, solve(-8) = -2 and
            solve(-9) = -2.

            {_RULES}
            """
        )

    @property
    def starting_solution(self) -> str:
        # Positive-only, and off by one: stops at the first r whose cube reaches
        # n rather than the last one that stays below it.
        return (
            "def solve(n):\n"
            "    r = 0\n"
            "    while r * r * r < n:\n"
            "        r += 1\n"
            "    return r\n"
        )

    @property
    def reference_solution(self) -> str:
        return (
            "def solve(n):\n"
            "    v = n\n"
            "    if v < 0:\n"
            "        v = -v\n"
            "    r = 0\n"
            "    while (r + 1) * (r + 1) * (r + 1) <= v:\n"
            "        r += 1\n"
            "    if n < 0:\n"
            "        return -r\n"
            "    return r\n"
        )

    @property
    def hidden_cases(self) -> tuple[int, ...]:
        return (
            0, 1, 2, 7, 8, 9, 26, 27, 28, 63, 64, 65, 1000,
            -1, -7, -8, -9, -27, -28, -64,
        )

    def oracle(self, n: int) -> int:
        v = -n if n < 0 else n
        r = 0
        while (r + 1) ** 3 <= v:
            r += 1
        return -r if n < 0 else r


class RoundHalfToEvenEnv(GradedCorrectnessEnvironment):
    """Divide by 10 and round, with ties going to the even result."""

    name = "round_half_to_even"

    @property
    def task_prompt(self) -> str:
        return textwrap.dedent(
            f"""\
            solve(n) must return n divided by 10, rounded to the nearest
            integer. When n is exactly halfway between two integers (that is,
            when the last digit of n is 5), round to whichever of the two
            results is EVEN.

            For example solve(24) = 2, solve(26) = 3, solve(25) = 2 (2 is even),
            solve(35) = 4 (4 is even), and solve(0) = 0. Negative n follows the
            same rule applied to its magnitude, with the sign restored:
            solve(-25) = -2.

            {_RULES}
            """
        )

    @property
    def starting_solution(self) -> str:
        # Truncating division, no rounding and no tie rule.
        return (
            "def solve(n):\n"
            "    return n // 10\n"
        )

    @property
    def reference_solution(self) -> str:
        return (
            "def solve(n):\n"
            "    v = n\n"
            "    if v < 0:\n"
            "        v = -v\n"
            "    q = v // 10\n"
            "    rem = v - q * 10\n"
            "    if rem > 5:\n"
            "        q = q + 1\n"
            "    elif rem == 5:\n"
            "        if q % 2 == 1:\n"
            "            q = q + 1\n"
            "    if n < 0:\n"
            "        return -q\n"
            "    return q\n"
        )

    @property
    def hidden_cases(self) -> tuple[int, ...]:
        return (
            0, 4, 5, 6, 14, 15, 16, 24, 25, 26, 35, 45, 55, 99, 100,
            -5, -15, -25, -26, -35,
        )

    def oracle(self, n: int) -> int:
        v = -n if n < 0 else n
        q, rem = divmod(v, 10)
        if rem > 5 or (rem == 5 and q % 2 == 1):
            q += 1
        return -q if n < 0 else q


class TrailingZeroBitsEnv(GradedCorrectnessEnvironment):
    """Count trailing zero bits. NOT REGISTERED: too little headroom.

    Rejected by ``GradedCorrectnessEnvironment``'s construction guard, which
    measured the starting solution passing 18 of 19 cases. The intended trap was
    the ``solve(0) = -1`` convention, but Python's floor division already handles
    negative inputs correctly, so ``n = 0`` was the only case that differed.

    Kept as a record. Contriving extra damage to manufacture headroom would make
    the task measure something other than the boundary it was written for, which
    is how the previous two benchmarks became useless.
    """

    name = "trailing_zero_bits"

    @property
    def task_prompt(self) -> str:
        return textwrap.dedent(
            f"""\
            solve(n) must return the number of trailing zero bits in the binary
            representation of the absolute value of n. By convention solve(0)
            returns -1, since zero has no highest set bit.

            For example solve(1) = 0, solve(2) = 1, solve(12) = 2,
            solve(-8) = 3.

            {_RULES}
            """
        )

    @property
    def starting_solution(self) -> str:
        # Loops forever on 0 unless guarded, returns 0 there instead of -1, and
        # ignores the sign.
        return (
            "def solve(n):\n"
            "    if n == 0:\n"
            "        return 0\n"
            "    count = 0\n"
            "    v = n\n"
            "    while v % 2 == 0:\n"
            "        count += 1\n"
            "        v = v // 2\n"
            "    return count\n"
        )

    @property
    def reference_solution(self) -> str:
        return (
            "def solve(n):\n"
            "    if n == 0:\n"
            "        return -1\n"
            "    v = n\n"
            "    if v < 0:\n"
            "        v = -v\n"
            "    count = 0\n"
            "    while v % 2 == 0:\n"
            "        count += 1\n"
            "        v = v // 2\n"
            "    return count\n"
        )

    @property
    def hidden_cases(self) -> tuple[int, ...]:
        return (
            0, 1, 2, 3, 4, 6, 8, 12, 16, 40, 64, 96, 1024,
            -1, -2, -8, -12, -40, -64,
        )

    def oracle(self, n: int) -> int:
        if n == 0:
            return -1
        v = -n if n < 0 else n
        count = 0
        while v % 2 == 0:
            count += 1
            v //= 2
        return count


__all__ = ["IntegerCubeRootEnv", "RoundHalfToEvenEnv", "TrailingZeroBitsEnv"]
