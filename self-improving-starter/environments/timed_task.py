"""A timing-scored task base that does not manufacture reward from noise.

E63 audited the executable suite with **null variants** -- a task's own starting
solution with a comment appended, semantically identical, so any non-zero reward
it earns is measurement artefact.  ``count_primes`` failed badly: re-scoring
identical programs produced rewards from 0.000 to 0.276, and a search keeping
the best of five no-op proposals booked 0.254 of reward for changing nothing.

Three defects produced that, and this base class fixes all three.

1. **The reference was a single measurement.**  ``count_primes.py:16`` captured
   ``_baseline_time`` once at construction and normalised every candidate
   against it forever.  In one E63 run that sample landed 21.8% slow and handed
   every null variant a free +0.174; in an earlier probe it landed fast and
   scored identical programs at -0.171.  The reference was unstable in magnitude
   *and sign* between runs of the same code on the same machine.  Here every
   timing -- including the two anchors -- is a median over
   :data:`TIMING_SAMPLES` samples of an auto-calibrated repeat count, the
   approach ``optimize_function`` already used and the reason it was the one
   task E63 admitted.

2. **The reward was clamped to [0, 1].**  That censors the negative half of a
   symmetric noise distribution, so a no-op change has a positive expected
   reward and ``max`` over k proposals grows with k.  It also contradicted the
   documented interface: ``base.py`` specifies a reward "normalized to
   [<0, ~1+]" where "a correct-but-no-better solution scores ~0.0" and "beating
   it can exceed 1.0".  This class implements that contract literally and does
   not clamp, so a slower candidate scores negative and noise cancels instead of
   rectifying.

3. **There was no held-out reference solution.**  ``count_primes`` normalised
   against the starting solution alone, so the reward scale had no upper anchor
   and its magnitude was arbitrary.  Here a strong reference solution defines
   the 1.0 point, exactly as ``base.py`` describes.  It is held out of the
   prompt and never shown to a candidate.

Reward is therefore ``(t - t_start) / (t_reference - t_start)``, the base.py
formula applied to time as the raw metric.  Because ``t_reference < t_start``,
matching the starting solution scores 0.0, matching the reference scores 1.0,
beating it exceeds 1.0, and being slower goes negative.

Execution note: this base class uses the local fixture runner, matching the
existing ``count_primes`` and ``sum_digits`` environments.  That runner is a
bounded local sandbox and **not** a security boundary.  It is appropriate for
the trusted, operator-authored fixtures used in instrument audits; model-written
candidates must go through the reviewed container adapter.
"""

from __future__ import annotations

import abc
import textwrap

from sandbox import run_python

from .base import Environment, ScoreResult
from .optimize_function import _validate_candidate

#: Samples taken per measurement; the median of these is the reported timing.
TIMING_SAMPLES = 5

#: Repeat counts are calibrated upward until one batch takes at least this long,
#: which keeps a single measurement well above clock granularity.
TIMING_TARGET_SECONDS = 0.04

MAX_TIMING_REPEATS = 1 << 20
RUN_TIMEOUT_SECONDS = 15.0


def _measurement_script(solution_source: str, timing_argument: int) -> str:
    """Build a calibrated, median-of-samples timing harness for ``solve``."""
    preamble = "import time as _h_time\nimport statistics as _h_stats\n"
    body = textwrap.dedent(
        f"""
        _H_N = {timing_argument}
        _H_TARGET = {TIMING_TARGET_SECONDS!r}
        _H_MAX_REPEATS = {MAX_TIMING_REPEATS}

        def _h_measure(_h_repeats):
            _h_started = _h_time.perf_counter()
            for _h_unused in range(_h_repeats):
                solve(_H_N)
            return _h_time.perf_counter() - _h_started

        _h_repeats = 1
        while True:
            _h_elapsed = _h_measure(_h_repeats)
            if _h_elapsed >= _H_TARGET or _h_repeats >= _H_MAX_REPEATS:
                break
            if _h_elapsed <= 0.0:
                _h_multiplier = 64
            else:
                _h_multiplier = max(2, min(64, int(_H_TARGET / _h_elapsed)))
            _h_repeats = min(_H_MAX_REPEATS, _h_repeats * _h_multiplier)

        _h_samples = []
        for _h_unused in range({TIMING_SAMPLES}):
            _h_samples.append(_h_measure(_h_repeats) / _h_repeats)
        print("TIMING " + format(_h_stats.median(_h_samples), ".17g"))
        """
    )
    return preamble + solution_source + "\n" + body


class TimedTaskEnvironment(Environment):
    """A speedup task anchored by a starting solution and a held-out reference."""

    #: The argument passed to ``solve`` when timing.
    timing_argument: int = 1000

    @property
    @abc.abstractmethod
    def reference_solution(self) -> str:
        """A strong solution defining the 1.0 point.  Never shown to candidates."""

    @property
    @abc.abstractmethod
    def correctness_cases(self) -> tuple[int, ...]:
        """Hidden cases the candidate must satisfy exactly."""

    @abc.abstractmethod
    def oracle(self, n: int) -> int:
        """Parent-side ground truth for ``solve(n)``."""

    #: The reference must beat the starting solution by at least this factor.
    #: A bare ``reference < starting`` test is useless as a guard: timing noise
    #: satisfies it about half the time, so a task with no real headroom would
    #: construct successfully and then hand out reward for nothing.
    minimum_speedup_factor: float = 2.0

    def __init__(self) -> None:
        self._starting_time = self._measure_or_raise(self.starting_solution)
        self._reference_time = self._measure_or_raise(self.reference_solution)
        speedup = self._starting_time / self._reference_time
        if speedup < self.minimum_speedup_factor:
            raise RuntimeError(
                f"{self.name}: the reference solution is only {speedup:.2f}x "
                f"faster than the starting solution, below the required "
                f"{self.minimum_speedup_factor}x. One reward unit would be "
                "comparable to timing noise, so the task cannot measure an "
                "improvement."
            )

    # -- measurement -----------------------------------------------------

    def _measure(self, solution_source: str) -> float | None:
        result = run_python(
            _measurement_script(solution_source, self.timing_argument),
            timeout_s=RUN_TIMEOUT_SECONDS,
        )
        if not result.ok:
            return None
        for line in result.stdout.splitlines():
            if line.startswith("TIMING "):
                try:
                    return float(line.split(None, 1)[1])
                except (IndexError, ValueError):
                    return None
        return None

    def _measure_or_raise(self, solution_source: str) -> float:
        timing = self._measure(solution_source)
        if timing is None or timing <= 0.0:
            raise RuntimeError(f"{self.name}: could not time an anchor solution")
        return timing

    def _check_correctness(self, solution_source: str) -> tuple[bool, str]:
        cases = self.correctness_cases
        checks = "\n".join(
            f"print('R', {index}, solve({value}))"
            for index, value in enumerate(cases)
        )
        result = run_python(
            solution_source + "\n" + checks, timeout_s=RUN_TIMEOUT_SECONDS
        )
        if not result.ok:
            return False, "candidate execution failed"
        seen: dict[int, int] = {}
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) == 3 and parts[0] == "R":
                try:
                    seen[int(parts[1])] = int(parts[2])
                except ValueError:
                    return False, "candidate produced an unparsable result"
        if len(seen) != len(cases):
            return False, "candidate did not answer every hidden case"
        for index, value in enumerate(cases):
            if seen[index] != self.oracle(value):
                return False, "hidden correctness mismatch"
        return True, "correctness cases passed"

    # -- scoring ---------------------------------------------------------

    @property
    def reward_span_seconds(self) -> float:
        """Seconds between the two anchors; one reward unit."""
        return self._starting_time - self._reference_time

    def score_correctness(self, solution_source: str) -> ScoreResult:
        _, failure = _validate_candidate(solution_source)
        if failure:
            return ScoreResult(-1.0, False, None, failure)
        correct, detail = self._check_correctness(solution_source)
        return ScoreResult(1.0 if correct else -1.0, correct, None, detail)

    def score(self, solution_source: str) -> ScoreResult:
        _, failure = _validate_candidate(solution_source)
        if failure:
            return ScoreResult(-1.0, False, None, failure)
        correct, detail = self._check_correctness(solution_source)
        if not correct:
            return ScoreResult(-1.0, False, None, detail)
        timing = self._measure(solution_source)
        if timing is None:
            return ScoreResult(-1.0, False, None, "candidate timing failed")
        # base.py's formula with time as the raw metric.  Deliberately unclamped:
        # clamping rectifies noise into free reward, which is what E63 measured.
        reward = (timing - self._starting_time) / (
            self._reference_time - self._starting_time
        )
        return ScoreResult(
            reward,
            True,
            timing,
            f"correct; {timing * 1e6:.2f} us (norm {reward:.3f})",
        )

    def baseline_report(self) -> dict:
        """Anchor timings, so a run can record the scale it was measured on."""
        return {
            "starting_seconds": self._starting_time,
            "reference_seconds": self._reference_time,
            "reward_span_seconds": self.reward_span_seconds,
            "speedup_factor": self._starting_time / self._reference_time,
        }


__all__ = [
    "TimedTaskEnvironment",
    "TIMING_SAMPLES",
    "TIMING_TARGET_SECONDS",
]
