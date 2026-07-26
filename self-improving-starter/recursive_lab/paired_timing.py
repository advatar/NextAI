"""Drift-cancelling timing: measure the anchor next to the candidate.

E65 found that every timing task in the suite is dominated by *drift* rather
than independent jitter.  The evidence was direct: a task's own starting
solution is its anchor and must score exactly 0.0 by definition, yet it scored
``+0.2339`` on ``count_primes_v2`` and ``-0.1902`` on ``power_mod``.  Each
environment captures its anchor once at construction and scores candidates
against it minutes later, so thermal state, cache occupancy and competing load
shift the whole reward scale between the two measurements.

E65 also showed why averaging cannot fix this: taking the median of m
evaluations reduced the spread by only 20% from m=1 to m=9 where independent
noise predicts about 67%.  A median cannot cancel a trend that is common to
every sample in it.

Pairing can.  This module measures the anchor and the candidate **interleaved in
a single process**, alternating between them, and reports the *ratio* rather
than either absolute time:

    ratio = t_candidate / t_anchor

A multiplicative drift ``d`` affecting the whole process scales both timings and
cancels: ``(d * t_candidate) / (d * t_anchor) == ratio``.  The reward is then

    reward = (1 - ratio) / (1 - reference_ratio)

which is 0.0 when the candidate matches the anchor, 1.0 when it matches the
reference, above 1.0 when it beats the reference, and negative when it is
slower -- the ``base.py`` contract, expressed in drift-immune units.

Why the anchor and not the reference is interleaved: the starting solution is
public and is shown to candidates in the task prompt, so co-locating it with
candidate code in one process leaks nothing.  The reference solution is held out
and must never share a process with a candidate.  It is calibrated separately,
once, against the same anchor -- also by paired measurement, so
``reference_ratio`` is itself drift-immune.

Only the standard library is used.  As elsewhere in this substrate the local
fixture runner is a bounded sandbox and not a security boundary; model-written
candidates belong in the reviewed container adapter.
"""

from __future__ import annotations

import ast
import statistics
import textwrap
from dataclasses import dataclass

from sandbox import run_python

#: Alternating measurement rounds.  Each round times the anchor once and the
#: candidate once, so the two see the same machine state.
#:
#: This MUST be even.  The order within a round alternates, so an odd count runs
#: one ordering more often than the other and leaves a residual order bias that
#: warm-up amplifies.  E66 ran with 7 rounds; adding ``count_divisors``
#: afterwards exposed the flaw immediately -- its anchor self-score, which must
#: be 0.0 by definition, came out at +0.1059 because the anchor took the cold
#: first slot in four rounds against the candidate's three.
PAIRED_ROUNDS = 8

#: Calibration target for one timed batch, well above clock granularity.
TIMING_TARGET_SECONDS = 0.02

#: Minimum calls averaged into one timed batch.
#:
#: The elapsed-time target alone is not enough.  A task whose single call already
#: exceeds the target calibrates to one or two repeats, so each "batch" is
#: effectively a single measurement and inherits its full variance.  ``gcd_fixed``
#: hit this immediately: at roughly 7 ms per call it calibrated to 2-3 repeats and
#: two *identical* programs measured ratios from 1.00 to 1.48, giving an anchor
#: self-score of +0.5058 where 0.0 is the definition.  Requiring a floor on the
#: repeat count restores averaging within each batch.
MIN_TIMING_REPEATS = 8

MAX_TIMING_REPEATS = 1 << 20
RUN_TIMEOUT_SECONDS = 30.0


class PairedTimingError(RuntimeError):
    """Raised when a paired measurement cannot be completed."""


def rename_function(source: str, new_name: str) -> str:
    """Rename the module's single function so two programs can coexist.

    The candidate subset forbids calls other than ``range``, so no program can
    refer to its own name; renaming the definition is sufficient.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError) as error:
        raise PairedTimingError(f"cannot parse program: {type(error).__name__}") from error
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    if len(functions) != 1:
        raise PairedTimingError("program must define exactly one function")
    functions[0].name = new_name
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def _paired_script(anchor: str, candidate: str, timing_argument: int) -> str:
    header = "import time as _h_time\nimport statistics as _h_stats\n"
    programs = (
        rename_function(anchor, "_h_anchor")
        + "\n"
        + rename_function(candidate, "_h_candidate")
        + "\n"
    )
    body = textwrap.dedent(
        f"""
        _H_N = {timing_argument}
        _H_TARGET = {TIMING_TARGET_SECONDS!r}
        _H_MAX = {MAX_TIMING_REPEATS}

        def _h_measure(_h_fn, _h_repeats):
            _h_started = _h_time.perf_counter()
            for _h_unused in range(_h_repeats):
                _h_fn(_H_N)
            return _h_time.perf_counter() - _h_started

        # Calibrate on the anchor, then use the SAME repeat count for both, so
        # per-call overhead enters each side identically and cancels in the ratio.
        _H_MIN_REPEATS = {MIN_TIMING_REPEATS}

        _h_repeats = 1
        while True:
            _h_elapsed = _h_measure(_h_anchor, _h_repeats)
            _h_enough = _h_elapsed >= _H_TARGET and _h_repeats >= _H_MIN_REPEATS
            if _h_enough or _h_repeats >= _H_MAX:
                break
            if _h_repeats < _H_MIN_REPEATS and _h_elapsed >= _H_TARGET:
                # Long enough but too few calls to average: grow to the floor.
                _h_repeats = min(_H_MAX, _H_MIN_REPEATS)
                continue
            if _h_elapsed <= 0.0:
                _h_multiplier = 64
            else:
                _h_multiplier = max(2, min(64, int(_H_TARGET / _h_elapsed)))
            _h_repeats = min(_H_MAX, _h_repeats * _h_multiplier)

        # Warm both programs before measuring, so neither pays the cold-cache
        # and branch-predictor cost of its first execution inside a timed round.
        _h_measure(_h_anchor, _h_repeats)
        _h_measure(_h_candidate, _h_repeats)

        _h_anchor_samples = []
        _h_candidate_samples = []
        for _h_round in range({PAIRED_ROUNDS}):
            # Alternate within the round so neither side systematically owns the
            # warmer or the cooler half of the interval.
            if _h_round % 2 == 0:
                _h_a = _h_measure(_h_anchor, _h_repeats) / _h_repeats
                _h_b = _h_measure(_h_candidate, _h_repeats) / _h_repeats
            else:
                _h_b = _h_measure(_h_candidate, _h_repeats) / _h_repeats
                _h_a = _h_measure(_h_anchor, _h_repeats) / _h_repeats
            _h_anchor_samples.append(_h_a)
            _h_candidate_samples.append(_h_b)

        print("ANCHOR " + format(_h_stats.median(_h_anchor_samples), ".17g"))
        print("CANDIDATE " + format(_h_stats.median(_h_candidate_samples), ".17g"))
        """
    )
    return header + programs + body


@dataclass(frozen=True)
class PairedMeasurement:
    """Anchor and candidate timings taken adjacently, plus their ratio."""

    anchor_seconds: float
    candidate_seconds: float

    @property
    def ratio(self) -> float:
        """``t_candidate / t_anchor``; immune to drift common to both."""
        return self.candidate_seconds / self.anchor_seconds


def paired_measure(
    anchor: str, candidate: str, timing_argument: int
) -> PairedMeasurement:
    """Time ``anchor`` and ``candidate`` interleaved in one process."""
    result = run_python(
        _paired_script(anchor, candidate, timing_argument),
        timeout_s=RUN_TIMEOUT_SECONDS,
    )
    if not result.ok:
        raise PairedTimingError("paired measurement process failed")
    values: dict[str, float] = {}
    for line in result.stdout.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0] in ("ANCHOR", "CANDIDATE"):
            try:
                values[parts[0]] = float(parts[1])
            except ValueError:
                raise PairedTimingError("unparsable timing line") from None
    if "ANCHOR" not in values or "CANDIDATE" not in values:
        raise PairedTimingError("paired measurement produced no timings")
    if values["ANCHOR"] <= 0.0 or values["CANDIDATE"] <= 0.0:
        raise PairedTimingError("paired measurement produced a non-positive timing")
    return PairedMeasurement(values["ANCHOR"], values["CANDIDATE"])


def paired_reward(ratio: float, reference_ratio: float) -> float:
    """Map a drift-immune ratio onto the base.py reward scale.

    ``reference_ratio`` is the reference solution's ratio against the same
    anchor, so it is the 1.0 point.  It must be below 1.0, i.e. the reference
    must actually be faster than the anchor.
    """
    if not 0.0 < reference_ratio < 1.0:
        raise PairedTimingError(
            f"reference_ratio {reference_ratio!r} must lie in (0, 1); the "
            "reference must be faster than the anchor"
        )
    return (1.0 - ratio) / (1.0 - reference_ratio)


def calibrate_reference_ratio(
    anchor: str, reference: str, timing_argument: int, rounds: int = 3
) -> float:
    """Median ratio of the reference against the anchor, measured in pairs.

    Run separately from any candidate so the held-out reference never shares a
    process with candidate code.
    """
    if rounds < 1:
        raise PairedTimingError("rounds must be at least 1")
    ratios = [
        paired_measure(anchor, reference, timing_argument).ratio
        for _ in range(rounds)
    ]
    return statistics.median(ratios)


__all__ = [
    "PairedTimingError",
    "PairedMeasurement",
    "PAIRED_ROUNDS",
    "rename_function",
    "paired_measure",
    "paired_reward",
    "calibrate_reference_ratio",
]
