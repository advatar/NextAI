"""RE-Bench-style environment interface.

Each environment is a research-engineering task with three pieces (per
arXiv:2411.15114):

  * starting_solution  – a simple, deliberately weak solution shown to the agent.
                         Defines the 0.0 point of the normalized score and shows
                         what a valid solution looks like.
  * reference_score    – the score of a strong reference solution, held out from
                         the agent. Defines the 1.0 point.
  * score(solution)    – run the candidate in the sandbox, gate on correctness,
                         and return a reward normalized to [<0, ~1+]:
                             (raw - starting_raw) / (reference_raw - starting_raw)
                         A correct-but-no-better solution scores ~0.0; matching
                         the reference scores ~1.0; beating it can exceed 1.0.

Reward is execution-grounded: it comes from actually running the code rather
than only asking a learned judge. That signal is trustworthy only when the
candidate cannot forge, inspect, or modify the evaluator and when resource and
safety gates remain external. Execution by itself is not a security boundary.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass
class ScoreResult:
    reward: float          # normalized score (execution-verified)
    correct: bool          # passed the correctness gate
    raw: float | None      # raw metric (e.g. seconds, accuracy) before normalization
    detail: str            # human-readable log line


class Environment(abc.ABC):
    name: str

    @property
    @abc.abstractmethod
    def task_prompt(self) -> str:
        """The natural-language task shown to the model (no reference solution)."""

    @property
    @abc.abstractmethod
    def starting_solution(self) -> str:
        """A weak but valid starting solution (the 0.0 point, shown to the agent)."""

    @abc.abstractmethod
    def score(self, solution_source: str) -> ScoreResult:
        """Execute `solution_source` in the sandbox and return a normalized reward.

        Must be robust to broken candidates: a solution that errors, times out,
        or fails the correctness gate returns reward <= 0.0 with correct=False,
        never raises.
        """
