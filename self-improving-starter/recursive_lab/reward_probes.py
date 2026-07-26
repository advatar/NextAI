"""Probes that measure whether a reward function can be trusted.

Three lessons from E63 and E64 are encoded here.

**A null probe must not be detectable.**  E63 and E64 both used "the starting
solution with a comment appended" as the semantically-null variant.
``optimize_function`` compares candidates by ``ast.dump``, so a comment is
invisible to it: the variant parsed identically to the starting solution and the
environment correctly returned exactly ``0.0`` every time.  Both experiments read
that as a perfect noise profile and admitted the task.  It was neither precision
nor censoring -- the probe was simply *evaded*.  Scoring the same task with an
AST-distinct no-op (a renamed local) instead produces rewards spanning -0.29 to
+0.05.  :func:`semantic_noop_variant` renames local bindings, so the program is
byte- and AST-distinct while remaining exactly the same computation, and costs
nothing extra at runtime.

**Zero spread is not self-evidently good.**  A reward clamped with
``max(0.0, ...)`` floors every below-baseline result to exactly zero, which looks
identical to a perfectly precise reward.  E64 admitted ``count_primes`` v1 -- the
task E63 rejected as worst -- for exactly this reason.  :func:`monotonicity_probe`
distinguishes the two by scoring a deliberately *slower* but still correct
program: an honest reward returns a clearly negative number, a censored one
returns zero.

**Best-of-k phantom gain cannot be engineered away.**  Taking a maximum over any
noisy reward grows with k, so a search keeping the best of k no-op proposals
books a gain for doing nothing.  No environment fix removes this; only reducing
the spread does.  :func:`median_score` evaluates a candidate m times and takes
the median, which shrinks the effective spread by roughly ``sqrt(m)``, and
:func:`best_of_k` estimates what a best-of-k search would still manufacture.

Only the standard library is used, and no function here interprets a reward as
evidence of capability -- these measure the instrument, not the candidate.
"""

from __future__ import annotations

import ast
import random
import statistics
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence


class ProbeError(ValueError):
    """Raised when a probe cannot be constructed for a program."""


_PROTECTED_NAMES = frozenset({"solve", "range"})


def _local_binding_names(tree: ast.AST, argument_names: frozenset[str]) -> list[str]:
    """Names assigned inside the function, excluding arguments and builtins."""
    names: list[str] = []
    for node in ast.walk(tree):
        target = None
        if isinstance(node, ast.Assign):
            for item in node.targets:
                if isinstance(item, ast.Name):
                    target = item.id
                    if target not in names:
                        names.append(target)
            continue
        if isinstance(node, (ast.AugAssign, ast.For)):
            item = node.target
            if isinstance(item, ast.Name):
                target = item.id
                if target not in names:
                    names.append(target)
    return [
        name
        for name in names
        if name not in _PROTECTED_NAMES and name not in argument_names
    ]


def semantic_noop_variant(source: str, index: int) -> str:
    """Return a program that computes exactly the same thing, distinctly.

    Local bindings are renamed with an index-specific suffix.  Renaming changes
    the AST -- which is what defeats identity checks like
    ``optimize_function._same_program`` -- while adding no runtime work at all,
    so the timing measured is genuinely the same computation's timing.

    If a program binds nothing renameable, an unused constant assignment is
    inserted instead.  That is still semantically null, though it does cost one
    trivial statement.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError) as error:
        raise ProbeError(f"cannot parse program: {type(error).__name__}") from error

    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    if not functions:
        raise ProbeError("program defines no function to vary")
    function = functions[0]
    argument_names = frozenset(
        argument.arg
        for argument in [*function.args.posonlyargs, *function.args.args]
    )

    renameable = _local_binding_names(function, argument_names)
    suffix = f"_v{index}"
    if renameable:
        mapping = {name: f"{name}{suffix}" for name in renameable}

        class _Renamer(ast.NodeTransformer):
            def visit_Name(self, node: ast.Name) -> ast.Name:  # noqa: N802
                if node.id in mapping:
                    node.id = mapping[node.id]
                return node

        _Renamer().visit(function)
    else:
        function.body.insert(
            0,
            ast.Assign(
                targets=[ast.Name(id=f"_noop{suffix}", ctx=ast.Store())],
                value=ast.Constant(value=0),
            ),
        )

    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def is_semantically_distinct_source(left: str, right: str) -> bool:
    """True when two programs differ by AST, i.e. an identity check sees them apart."""
    try:
        return ast.dump(ast.parse(left), include_attributes=False) != ast.dump(
            ast.parse(right), include_attributes=False
        )
    except (SyntaxError, ValueError, RecursionError) as error:
        raise ProbeError(f"cannot parse program: {type(error).__name__}") from error


def median_score(
    score: Callable[[str], float], source: str, repeats: int
) -> float:
    """Median of ``repeats`` independent evaluations of one program.

    A median over m measurements shrinks the spread by roughly ``sqrt(m)``, which
    is the only lever that reduces best-of-k phantom gain: the environment cannot
    be made noiseless, but the scoring protocol can average over the noise.
    """
    if repeats < 1:
        raise ProbeError("repeats must be at least 1")
    return statistics.median(score(source) for _ in range(repeats))


def median_of_subsample(
    measurements: Sequence[float], repeats: int, rng: random.Random
) -> float:
    """Median of ``repeats`` draws from already-collected measurements.

    Collecting m measurements once and subsampling lets a single expensive sweep
    report the whole median-of-m curve, instead of re-running the environment
    for every m.
    """
    if repeats < 1:
        raise ProbeError("repeats must be at least 1")
    if not measurements:
        raise ProbeError("no measurements to subsample")
    return statistics.median(
        measurements[rng.randrange(len(measurements))] for _ in range(repeats)
    )


def best_of_k(
    rewards: Sequence[float], k: int, samples: int, rng: random.Random
) -> float:
    """Expected reward of keeping the best of ``k`` no-op proposals."""
    if not rewards:
        raise ProbeError("no rewards to bootstrap")
    if k < 1:
        raise ProbeError("k must be at least 1")
    return statistics.fmean(
        max(rewards[rng.randrange(len(rewards))] for _ in range(k))
        for _ in range(samples)
    )


@dataclass(frozen=True)
class MonotonicityResult:
    """Does the reward fall when the program is genuinely made slower?"""

    slower_reward: float
    correct: bool
    responds: bool
    detail: str


def monotonicity_probe(
    score: Callable[[str], tuple[float, bool]],
    slower_source: str,
    *,
    threshold: float,
) -> MonotonicityResult:
    """Score a correct-but-slower program; an honest reward must go negative.

    This is what separates a precise reward from a censored one.  Both look like
    zero variance on null variants, but only a censored reward keeps returning
    ~0.0 when the candidate is actually worse.
    """
    reward, correct = score(slower_source)
    if not correct:
        return MonotonicityResult(
            reward,
            False,
            False,
            "the slower probe was judged incorrect, so monotonicity is unmeasured",
        )
    responds = reward <= threshold
    return MonotonicityResult(
        reward,
        True,
        responds,
        (
            f"slower program scored {reward:+.4f}"
            + (
                ""
                if responds
                else f"; a reward that does not fall below {threshold} when the "
                "program is genuinely slower is censored or insensitive"
            )
        ),
    )


def spread(values: Iterable[float]) -> float:
    collected = list(values)
    if not collected:
        raise ProbeError("no values to summarise")
    return statistics.pstdev(collected)


__all__ = [
    "ProbeError",
    "MonotonicityResult",
    "semantic_noop_variant",
    "is_semantically_distinct_source",
    "median_score",
    "median_of_subsample",
    "best_of_k",
    "monotonicity_probe",
    "spread",
]
