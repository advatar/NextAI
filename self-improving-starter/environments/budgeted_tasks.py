"""Cheap-to-verify, expensive-to-solve tasks with a deterministic budget.

E76 sharpened the blocker: the binding constraint is not the candidate subset
but the task FORMAT.  Any problem expressible as one function, one integer in,
one integer out, checked by a Python oracle, is within a 12B model's competence,
and that format is exactly what makes the oracle checkable.  The tension is
between checkability and difficulty.

There is a classic escape, and this module uses it.  For problems where
*verifying* an answer is cheap but *finding* it is expensive, difficulty and
checkability are no longer in tension: the oracle stays a short exact
computation while the candidate must supply a genuinely efficient algorithm.

The lever that makes this work deterministically already exists.
``recursive_lab.loop_guard`` bounds total loop iterations per call, so an
algorithmic requirement can be enforced without any wall-clock timing:

* a brute-force solution over 2**24 subsets needs ~16.7 million iterations and
  is cut short by the guard, so it returns wrong answers;
* a dynamic program over the same instance needs ~15 thousand and finishes well
  inside the budget.

Both are *correct* programs; only one is efficient enough.  That is a difficulty
axis the previous designs never had, and unlike a timeout it is exact,
reproducible and independent of machine load -- the property E65 to E68 spent
four experiments establishing.

The budget is also a continuous dial.  If a task lands outside the measurable
band it can be moved by changing the iteration limit or the instance size,
rather than by inventing another task and hoping.  That is the first genuinely
tunable difficulty control in this substrate.

The instance generator is stated in the prompt so the candidate can reproduce it
exactly; it is arithmetic the model must implement, not data it must be given.
"""

from __future__ import annotations

import textwrap

from recursive_lab.widened_validator import validate_widened

from .base import ScoreResult
from .graded_correctness import GradedCorrectnessEnvironment

#: Total loop iterations a candidate may spend per call. Chosen so an O(K * S)
#: dynamic program fits comfortably and an O(2**K) enumeration cannot.
ITERATION_BUDGET = 200_000

ITEMS = 20

#: Value range. Sized with ITEMS so the DP costs about ITEMS * total/2 ~ 100k
#: iterations (inside the budget) while enumeration costs 2**20 ~ 1.05M (outside).
VALUE_RANGE = 1000

_RULES = (
    "Return only a Python module defining solve(n), inside a single ```python "
    "fenced block. You may use lists, tuples, dicts, sets, strings, slicing, "
    "comprehensions and helper functions. No imports, no classes, no lambda, no "
    "try/except, and no names containing double underscores."
)


GENERATOR_EXPR = f"[((n * 31 + i * 7919) % {VALUE_RANGE}) + 1 for i in range({ITEMS})]"


def _instance(n: int) -> list[int]:
    """The multiset for seed n.

    The prompt renders :data:`GENERATOR_EXPR` rather than repeating the formula,
    because an earlier revision changed this function and the anchor solutions
    while leaving the prompt's hardcoded copy stale. The model then implemented
    the formula it was given -- correctly, with an efficient bitset DP -- and
    scored zero against a different oracle, which looked exactly like the task
    being too hard.
    """
    return [((n * 31 + i * 7919) % VALUE_RANGE) + 1 for i in range(ITEMS)]


class BudgetedEnvironment(GradedCorrectnessEnvironment):
    """Graded correctness under the widened subset and an iteration budget."""

    iteration_budget: int = ITERATION_BUDGET

    def case_results(self, solution_source, *, timeout_s=30.0, iteration_limit=None):
        return super().case_results(
            solution_source,
            timeout_s=timeout_s,
            iteration_limit=iteration_limit or self.iteration_budget,
        )

    def score(self, solution_source: str) -> ScoreResult:
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

    def _count_passed(self, solution_source: str) -> int:
        outcomes = self.case_results(solution_source)
        return sum(1 for ok in outcomes if ok)


class PartitionFeasibleEnv(BudgetedEnvironment):
    """Can the generated multiset be split into two equal-sum halves?

    Verification is a short dynamic program.  A candidate that enumerates
    subsets is correct but exceeds the budget and is cut short.
    """

    name = "partition_feasible"

    @property
    def task_prompt(self) -> str:
        return textwrap.dedent(
            f"""\
            Build the list a = [((n * 31 + i * 7919) % {VALUE_RANGE}) + 1 for i in range({ITEMS})].

            solve(n) must return the LARGEST sum achievable by any subset of a
            that does not exceed total // 2, where total is the sum of a.

            IMPORTANT: your program runs under a hard budget of about
            {ITERATION_BUDGET:,} total loop iterations per call. Enumerating all
            2**{ITEMS} subsets is over a million iterations, exceeds the budget,
            and will be cut off mid-computation, producing wrong answers. You
            need an approach whose work grows with the total rather than with
            the number of subsets.

            {_RULES}
            """
        )

    @property
    def starting_solution(self) -> str:
        # Correct in principle, far over budget: 2**20 subsets.
        return (
            "def solve(n):\n"
            f"    a = {GENERATOR_EXPR}\n"
            "    total = sum(a)\n"
            "    half = total // 2\n"
            "    best = 0\n"
            "    for mask in range(1 << len(a)):\n"
            "        s = 0\n"
            "        for i in range(len(a)):\n"
            "            if mask & (1 << i):\n"
            "                s += a[i]\n"
            "        if s <= half and s > best:\n"
            "            best = s\n"
            "    return best\n"
        )

    @property
    def reference_solution(self) -> str:
        """Bitset dynamic program: one big-integer shift per item.

        The reference must be the FASTEST known-correct program, not merely a
        correct one. An earlier version used the O(items * total/2) table DP,
        and tightening the budget made that reference itself unattainable -- the
        construction guard correctly refused to build the environment. Using the
        bitset form means the budget can be tightened to squeeze out the table
        DP while 1.0 stays reachable.
        """
        return (
            "def solve(n):\n"
            f"    a = {GENERATOR_EXPR}\n"
            "    total = sum(a)\n"
            "    half = total // 2\n"
            "    reachable = 1\n"
            "    for value in a:\n"
            "        reachable = reachable | (reachable << value)\n"
            "    for target in range(half, -1, -1):\n"
            "        if (reachable >> target) & 1:\n"
            "            return target\n"
            "    return 0\n"
        )

    @property
    def hidden_cases(self) -> tuple[int, ...]:
        return tuple(range(1, 21))

    def oracle(self, n: int) -> int:
        a = _instance(n)
        total = sum(a)
        half = total // 2
        reachable = [False] * (half + 1)
        reachable[0] = True
        for value in a:
            for target in range(half, value - 1, -1):
                if reachable[target - value]:
                    reachable[target] = True
        for target in range(half, -1, -1):
            if reachable[target]:
                return target
        return 0


__all__ = ["ITERATION_BUDGET", "BudgetedEnvironment", "PartitionFeasibleEnv"]
