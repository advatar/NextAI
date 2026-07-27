"""Strategies as the mutable artifact, so improver quality can be measured.

Three benchmark designs failed to make search quality visible by making *tasks*
harder, and the consolidated finding was a narrow model competence band: easy
tasks are one-shot solved, harder ones produce nothing valid.  Making the tasks
harder is not the only lever, and it was the wrong one to reach for first.

The project's design has always said the mutable artifact is a **typed
strategy** -- a system instruction plus planning steps -- not the program and not
the evaluator.  That reframes the measurement.  Instead of asking "is this task
hard enough that search shows up", ask "does changing the strategy change the
outcome on a fixed task set".  If two strategies produce different success rates
under an identical budget, improver quality is measurable, and that is the
prerequisite for any claim about one improver producing better successors than
another.

This is also the only formulation in which a *recursive* claim is even
expressible: a program cannot improve its own proposer, but a strategy is an
artifact a proposer can rewrite, and its quality is measured by the outcomes it
produces rather than by inspecting it.

The strategy is composed into the system instruction and nothing else.  The
subset rules and the trust boundary are fixed by the harness, so a strategy
cannot widen what a candidate may do, cannot see hidden cases, and cannot alter
grading.  A strategy that tried to would be changing the evaluator, which is the
one thing this project has kept immutable throughout.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

#: Fixed by the harness. A strategy may not alter these, because they are the
#: candidate subset and the trust boundary rather than a matter of approach.
SUBSET_RULES = (
    "Return ONLY a Python module defining solve(n), inside a single ```python "
    "fenced block, with no explanation. Use only integer arithmetic, "
    "comparisons, loops, conditionals, local variables and range(). range() is "
    "the ONLY function you may call: abs(), str(), int(), len(), sum(), max() "
    "and min() are NOT available, and neither are lists, strings or "
    "comprehensions. To take an absolute value write `v = n` then "
    "`if v < 0: v = -v`. Keep the program short; never emit a long chain of "
    "elif branches enumerating individual inputs."
)


@dataclass(frozen=True)
class Strategy:
    """A named approach the proposer is instructed to follow.

    ``planning_steps`` are rendered into the system instruction verbatim.  They
    are the mutable content: everything else about the call is held fixed, so a
    measured difference between two strategies is attributable to them.
    """

    name: str
    preamble: str
    planning_steps: tuple[str, ...] = ()

    def system_instruction(self) -> str:
        parts = [self.preamble.strip()]
        if self.planning_steps:
            steps = "\n".join(
                f"{index}. {step}" for index, step in enumerate(self.planning_steps, 1)
            )
            parts.append("Before writing code, work through these steps:\n" + steps)
        parts.append(SUBSET_RULES)
        return "\n\n".join(parts)

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(
                {
                    "name": self.name,
                    "preamble": self.preamble,
                    "planning_steps": list(self.planning_steps),
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "preamble": self.preamble,
            "planning_steps": list(self.planning_steps),
            "digest": self.digest,
        }


#: The degenerate baseline: says what to do and nothing about how.
MINIMAL = Strategy(
    name="minimal",
    preamble="You repair small Python functions. Fix the program you are given.",
)

#: Names the failure mode these tasks actually have -- unhandled input classes --
#: without naming any specific fix for any specific task.
EDGE_CASE = Strategy(
    name="edge_case",
    preamble=(
        "You repair small Python functions. The program you are given is "
        "correct on common inputs and wrong on some class of inputs it does not "
        "handle."
    ),
    planning_steps=(
        "List the distinct classes of input the contract covers, including "
        "negatives, zero, and boundary values.",
        "For each class, decide what the contract requires and whether the "
        "current program does that.",
        "Rewrite the whole function so every class is handled.",
    ),
)

#: Adds an explicit self-check pass on top of enumeration.
VERIFY = Strategy(
    name="verify",
    preamble=(
        "You repair small Python functions. The program you are given is "
        "correct on common inputs and wrong on some class of inputs it does not "
        "handle."
    ),
    planning_steps=(
        "List the distinct classes of input the contract covers, including "
        "negatives, zero, and boundary values.",
        "For each class, decide what the contract requires and whether the "
        "current program does that.",
        "Rewrite the whole function so every class is handled.",
        "Trace your rewritten function on one input from each class and check "
        "the result against the contract before answering.",
    ),
)

BASELINE_STRATEGIES = (MINIMAL, EDGE_CASE, VERIFY)


__all__ = [
    "BASELINE_STRATEGIES",
    "EDGE_CASE",
    "MINIMAL",
    "SUBSET_RULES",
    "Strategy",
    "VERIFY",
]
