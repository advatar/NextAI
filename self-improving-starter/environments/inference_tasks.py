"""Underdetermined specifications. The design failed: see MEASURED OUTCOME.

Two designs have now failed to produce a benchmark that can measure *search*
rather than task-solving ability:

* E69's four tasks were calibrated against a generic mutator; E71's model
  one-shots three of them and every governed run made exactly one promotion.
* ``multibug_tasks`` assumed several independent bugs would defeat a single
  proposal.  Measured 8/8 one-shot solved.  Difficulty is not additive across
  independent easy bugs -- a model rewrites the function from the contract
  rather than patching, so bug count is nearly irrelevant.

Both failures share a cause: **the full specification was in the prompt.**  Given
a complete contract, a capable model simply implements it, and no amount of
starting-solution damage changes that.

These tasks withhold part of the contract.  The prompt states the rule only over
a region of the input space, and the hidden cases extend beyond it along axes the
public examples cannot determine -- behaviour on negatives, at zero, and past a
threshold that the visible examples never reach.  A single proposal must
therefore *guess* the unstated behaviour, and only feedback across iterations can
correct it.

This is not a trick.  It is the ordinary situation of inferring intended
behaviour from tests, and it is the regime in which search quality is the thing
being measured: with the answer absent from the prompt, a better search procedure
finds it in fewer proposals and a worse one does not find it at all.

MEASURED OUTCOME: THE DESIGN DOES NOT WORK, FOR AN UNEXPECTED REASON.

Measured against the local Gemma 4 E2B, five one-shot proposals and ten iterated
proposals per task:

    piecewise_square   valid 0/5   one-shot 0.000   iterated final 0.000
    threshold_parity   valid 0/5   one-shot 0.000   iterated final 0.000

Not a single valid candidate, so there was no gradient for iteration to climb.
The cause is not difficulty.  Told the rule is not fully specified, this model
does not hypothesise a rule -- **it enumerates a lookup table**:

    elif n == 82: return 6724
    elif n == 83: return 6889
    elif n == 84:            <- truncated at the token cap

Every response ran to ``completion_tokens = 1400`` and stopped mid-branch, so
every candidate was syntactically invalid.  Raising the cap would only move the
truncation point; the enumeration has no natural end.

The deeper lesson, taken with ``multibug_tasks``:

**There is a capability cliff and no middle ground was found on this substrate.**
Given a complete specification the model one-shots the task, so search quality
cannot be observed.  Given an incomplete one it emits nothing valid, so search
has nothing to work with.  A benchmark that can measure *how* a search proceeds
needs tasks whose one-shot success rate is intermediate -- roughly 20-70% -- and
neither design produced that band.

One task from E71 did land in it by accident: ``integer_sqrt`` had a single-shot
success rate of 1/3 while the governed loop reached 3/3.  That is the only
observation so far of iteration mattering, and finding or constructing more tasks
in that band is the concrete prerequisite for anything further.

These environments are retained as recorded evidence of the negative result, not
as a usable benchmark.

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

_FEEDBACK_NOTE = (
    "The examples above do NOT determine the rule everywhere. The hidden tests "
    "cover inputs outside the range shown, and the feedback tells you how many "
    "of them your program currently satisfies. Use that count to revise your "
    "hypothesis about the unstated behaviour."
)


class PiecewiseSquareEnv(GradedCorrectnessEnvironment):
    """Public examples fix the rule on 1..5; negatives, zero and >10 are hidden.

    Unstated axes, each independently guessable:
      - behaviour at 0            (0, or 1, or unspecified)
      - behaviour on negatives    (even symmetry n*n, or odd symmetry -(n*n))
      - behaviour above 10        (continues n*n, or switches to n*10)
    """

    name = "piecewise_square"

    @property
    def task_prompt(self) -> str:
        return textwrap.dedent(
            f"""\
            solve(n) implements a single rule over all integers. These examples
            are all you are told about it:

                solve(1) = 1
                solve(2) = 4
                solve(3) = 9
                solve(5) = 25

            {_FEEDBACK_NOTE}

            {_RULES}
            """
        )

    @property
    def starting_solution(self) -> str:
        # The obvious generalisation from the examples, and wrong outside them.
        return (
            "def solve(n):\n"
            "    return n * n\n"
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
            "    if v > 10:\n"
            "        r = v * 10\n"
            "    else:\n"
            "        r = v * v\n"
            "    if n < 0:\n"
            "        return -r\n"
            "    return r\n"
        )

    @property
    def hidden_cases(self) -> tuple[int, ...]:
        return (
            0,
            1, 2, 3, 4, 5, 9, 10,          # inside the stated region
            11, 12, 20, 50, 100,           # past the unstated threshold
            -1, -3, -5, -10,               # negatives inside the region
            -11, -50,                      # negatives past the threshold
        )

    def oracle(self, n: int) -> int:
        if n == 0:
            return 0
        v = -n if n < 0 else n
        r = v * 10 if v > 10 else v * v
        return -r if n < 0 else r


class ThresholdParityEnv(GradedCorrectnessEnvironment):
    """Public examples show only small positive evens and odds."""

    name = "threshold_parity"

    @property
    def task_prompt(self) -> str:
        return textwrap.dedent(
            f"""\
            solve(n) implements a single rule over all integers. These examples
            are all you are told about it:

                solve(2) = 1
                solve(4) = 2
                solve(3) = 6
                solve(7) = 14

            {_FEEDBACK_NOTE}

            {_RULES}
            """
        )

    @property
    def starting_solution(self) -> str:
        # Matches every stated example, and says nothing correct beyond them.
        return (
            "def solve(n):\n"
            "    if n % 2 == 0:\n"
            "        return n // 2\n"
            "    return n * 2\n"
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
            "    if v >= 20:\n"
            "        r = v\n"
            "    elif v % 2 == 0:\n"
            "        r = v // 2\n"
            "    else:\n"
            "        r = v * 2\n"
            "    if n < 0:\n"
            "        return -r\n"
            "    return r\n"
        )

    @property
    def hidden_cases(self) -> tuple[int, ...]:
        return (
            0,
            2, 3, 4, 7, 8, 15, 19,     # inside the stated region
            20, 21, 40, 99, 100,       # at and past the unstated threshold
            -2, -3, -7, -19,           # negatives inside the region
            -20, -40,                  # negatives past the threshold
        )

    def oracle(self, n: int) -> int:
        if n == 0:
            return 0
        v = -n if n < 0 else n
        if v >= 20:
            r = v
        elif v % 2 == 0:
            r = v // 2
        else:
            r = v * 2
        return -r if n < 0 else r


__all__ = ["PiecewiseSquareEnv", "ThresholdParityEnv"]
