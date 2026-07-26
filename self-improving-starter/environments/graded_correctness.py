"""Graded-correctness tasks: a deterministic reward with no timing at all.

Ten experiments (E63-E68) went into making a wall-clock speedup signal
trustworthy on a developer machine, and none produced a task admissible under
replication.  E68 is the summary: no task solid, per-round null standard
deviations spanning 0.020 to 0.415 on the same task, and a single round able to
invert the ranking between the best and worst tasks in the suite.  Every defect
found along the way -- saturation, censoring, probe evasion, drift, order bias,
repeat-count floors -- was a *timing* defect.

This module drops timing entirely.  Reward is the fraction of hidden cases a
candidate answers correctly, normalised so the shipped starting solution scores
0.0 and a fully correct solution scores 1.0:

    reward = (passed - starting_passed) / (total - starting_passed)

Every property E63-E68 fought for falls out for free:

* **No noise.**  The same program scores identically every time, so a null
  variant scores exactly 0.0 and a standard deviation is exactly zero -- from
  determinism, not from censoring.  The monotonicity probe still distinguishes
  the two: a worse program must score below zero, and here it does.
* **No best-of-k phantom gain.**  A maximum over identical values is that value.
  A search proposing k no-op candidates gains exactly nothing, rather than the
  0.02-0.32 the timing tasks handed out.
* **No anchors, no drift, no pairing.**  There is no measurement to drift.
* **Unclamped.**  A candidate that breaks cases the starting solution passed
  scores negative, so regressions are visible rather than floored at zero.

The trade is that this measures *correctness improvement* rather than
optimisation, which is a narrower question -- but it is a real one for coding
agents, and it is measurable today.

Headroom comes from starting solutions that are plausible but incomplete: each
handles the common path and fails a documented class of inputs.  That is the
shape of the improvement a coding agent is actually asked to make.

Determinism note: ``score`` runs the candidate in the local fixture runner,
which is a bounded sandbox and not a security boundary.  Model-written
candidates belong in the reviewed container adapter.
"""

from __future__ import annotations

import abc

from sandbox import run_python

from .base import Environment, ScoreResult
from .optimize_function import _validate_candidate

RUN_TIMEOUT_SECONDS = 15.0


class GradedCorrectnessEnvironment(Environment):
    """Reward is the share of hidden cases fixed, relative to the start."""

    @property
    @abc.abstractmethod
    def reference_solution(self) -> str:
        """A fully correct solution.  Held out; never shown to a candidate."""

    @property
    @abc.abstractmethod
    def hidden_cases(self) -> tuple[int, ...]:
        """Inputs the candidate is graded on.  Not exposed in the prompt."""

    @abc.abstractmethod
    def oracle(self, n: int) -> int:
        """Parent-side ground truth."""

    #: The starting solution must fail at least this share of cases, or the task
    #: ships close to solved and has no room to measure an improvement -- the
    #: failure that sank ``sum_digits`` in E63.
    minimum_failing_share: float = 0.15

    def __init__(self) -> None:
        total = len(self.hidden_cases)
        if total < 8:
            raise RuntimeError(
                f"{self.name}: needs at least 8 hidden cases for the reward to "
                "have resolution"
            )
        self._total = total
        self._starting_passed = self._count_passed(self.starting_solution)
        reference_passed = self._count_passed(self.reference_solution)
        if reference_passed != total:
            raise RuntimeError(
                f"{self.name}: the reference solution fails "
                f"{total - reference_passed} of {total} cases, so 1.0 is not "
                "attainable"
            )
        failing = total - self._starting_passed
        if failing / total < self.minimum_failing_share:
            raise RuntimeError(
                f"{self.name}: the starting solution already passes "
                f"{self._starting_passed}/{total} cases, leaving too little "
                "headroom to measure an improvement"
            )

    # -- evaluation ------------------------------------------------------

    def _count_passed(self, solution_source: str) -> int:
        """How many hidden cases the candidate answers exactly."""
        cases = self.hidden_cases
        checks = "\n".join(
            f"print('R', {index}, solve({value}))"
            for index, value in enumerate(cases)
        )
        result = run_python(
            solution_source + "\n" + checks, timeout_s=RUN_TIMEOUT_SECONDS
        )
        if not result.ok:
            return 0
        seen: dict[int, str] = {}
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) == 3 and parts[0] == "R":
                seen[int(parts[1])] = parts[2]
        passed = 0
        for index, value in enumerate(cases):
            answer = seen.get(index)
            if answer is None:
                continue
            try:
                if int(answer) == self.oracle(value):
                    passed += 1
            except ValueError:
                continue
        return passed

    # -- scoring ---------------------------------------------------------

    @property
    def starting_passed(self) -> int:
        return self._starting_passed

    @property
    def total_cases(self) -> int:
        return self._total

    @property
    def headroom_cases(self) -> int:
        """Cases the starting solution gets wrong; one reward unit."""
        return self._total - self._starting_passed

    def score(self, solution_source: str) -> ScoreResult:
        _, failure = _validate_candidate(solution_source)
        if failure:
            return ScoreResult(-1.0, False, None, failure)
        passed = self._count_passed(solution_source)
        # Deliberately unclamped: a candidate that breaks cases the starting
        # solution passed scores negative, so regressions stay visible.
        reward = (passed - self._starting_passed) / self.headroom_cases
        return ScoreResult(
            reward,
            passed == self._total,
            float(passed),
            f"{passed}/{self._total} hidden cases (norm {reward:.3f})",
        )

    def score_correctness(self, solution_source: str) -> ScoreResult:
        result = self.score(solution_source)
        return ScoreResult(
            1.0 if result.correct else -1.0, result.correct, None, result.detail
        )

    def baseline_report(self) -> dict:
        return {
            "scoring": "graded_correctness",
            "total_cases": self._total,
            "starting_passed": self._starting_passed,
            "headroom_cases": self.headroom_cases,
            "deterministic": True,
        }


__all__ = ["GradedCorrectnessEnvironment"]
