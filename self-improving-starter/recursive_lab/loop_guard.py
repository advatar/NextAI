"""Bound every loop in a candidate so non-termination stops being a timeout.

The problem this removes
-----------------------

A mutation search over programs produces non-terminating candidates at a high
rate -- 25-58% for the generic operators in
:mod:`recursive_lab.program_mutation`, because perturbing a ``while`` condition
or a loop counter easily removes the exit.  If the only defence is a wall-clock
timeout, every such candidate costs the full bound, and the bound is caught
between two failures that E70 hit in succession:

* **Too long** and the run never finishes.  E70's first attempt inherited a
  15-second default and spent 2h11m accumulating 39 seconds of CPU.
* **Too short** and *correct* programs are failed spuriously.  E70b used 0.5s
  and the ``null_only`` control -- which proposes semantically identical
  programs and must therefore score exactly 0.0 -- came back at -0.4444, with a
  probe showing 2/12 false timeouts on a correct solution under load.

No timeout resolves that, because the two failure modes move in opposite
directions with machine load.  The bound has to stop being a *time*.

The approach
------------

Rewrite the candidate's AST so the whole function shares one iteration counter,
incremented in every loop body, and every loop breaks once the counter exceeds a
limit.  A non-terminating program then terminates in bounded *work* rather than
bounded time, produces wrong answers, fails its cases and is never promoted --
exactly the outcome wanted, with no dependence on how busy the machine is.

Two details matter.

**One counter per function, not one per loop.**  Per-loop counters bound each
loop separately, so two nested loops still permit ``limit ** 2`` iterations.  A
single counter declared at function entry bounds total work per call regardless
of nesting depth.  It resets on each call, so a program is judged the same way
on every case.

**``break`` rather than an exception.**  The candidate subset forbids exception
machinery, and a truncated loop returning a wrong answer is precisely the signal
the evaluator should act on.  ``break`` leaves only the innermost loop, but an
enclosing loop's own guard fires on its next iteration, so the unwind is
immediate.

Limits are iterations, so they are deterministic and reproducible across
machines -- which a timeout never was.
"""

from __future__ import annotations

import ast

#: Total loop iterations one call may run before loops are cut short.
#:
#: Choose this from a cost model, not by intuition.  A hanging mutant costs
#: ``limit * cases`` iterations *every time it is evaluated*, and a mutation
#: search evaluates thousands.  An earlier draft used 1_000_000, which is
#: 16_000_000 iterations per hanging candidate; a 60-candidate in-process probe
#: with that setting had to be killed after ten minutes -- the same failure as
#: the 15-second timeout, in a different currency.
#:
#: The legitimate requirement is tiny.  Across the correctness suite the largest
#: honest workload is ``collatz_steps`` at n=77_031, needing about 350
#: iterations; ``integer_sqrt`` at n=10_000 needs 100, ``count_one_bits`` 17 and
#: ``digit_sum_graded`` 7.  20_000 is roughly 57x the worst legitimate case and
#: costs 320_000 iterations per hanging mutant, which is milliseconds.
DEFAULT_ITERATION_LIMIT = 20_000

#: Prefixed to avoid colliding with candidate identifiers.
COUNTER_NAME = "_lg_iterations"


class LoopGuardError(ValueError):
    """Raised when a program cannot be guarded."""


def _guard_statements(limit: int) -> list[ast.stmt]:
    """``counter += 1`` then ``if counter > limit: break``."""
    return [
        ast.AugAssign(
            target=ast.Name(id=COUNTER_NAME, ctx=ast.Store()),
            op=ast.Add(),
            value=ast.Constant(value=1),
        ),
        ast.If(
            test=ast.Compare(
                left=ast.Name(id=COUNTER_NAME, ctx=ast.Load()),
                ops=[ast.Gt()],
                comparators=[ast.Constant(value=limit)],
            ),
            body=[ast.Break()],
            orelse=[],
        ),
    ]


class _Guard(ast.NodeTransformer):
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.loops = 0

    def _visit_body(self, body: list[ast.stmt]) -> list[ast.stmt]:
        """Visit each statement, splicing any list a transform returns.

        A transformer that returns a list must have it spliced into the parent
        body; appending it directly would nest a list inside the statement list
        and produce a malformed tree.
        """
        result: list[ast.stmt] = []
        for statement in body:
            visited = self.visit(statement)
            if isinstance(visited, list):
                result.extend(visited)
            elif visited is not None:
                result.append(visited)
        return result

    def _wrap(self, node: ast.For | ast.While) -> ast.stmt:
        self.loops += 1
        node.body = _guard_statements(self.limit) + self._visit_body(node.body)
        node.orelse = self._visit_body(node.orelse)
        return node

    def visit_While(self, node: ast.While) -> ast.stmt:  # noqa: N802
        return self._wrap(node)

    def visit_For(self, node: ast.For) -> ast.stmt:  # noqa: N802
        return self._wrap(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:  # noqa: N802
        node.body = self._visit_body(node.body)
        # Declared at entry so it resets per call and covers every nested loop.
        node.body.insert(
            0,
            ast.Assign(
                targets=[ast.Name(id=COUNTER_NAME, ctx=ast.Store())],
                value=ast.Constant(value=0),
            ),
        )
        return node


def guard_loops(source: str, limit: int = DEFAULT_ITERATION_LIMIT) -> str:
    """Return ``source`` with total loop iterations per call bounded by ``limit``.

    The result is only ever executed, never validated as a candidate or shown to
    a proposer.  It exists so the harness can run untrusted control flow with a
    deterministic bound.
    """
    if limit < 1:
        raise LoopGuardError("limit must be at least 1")
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError) as error:
        raise LoopGuardError(f"cannot parse program: {type(error).__name__}") from error
    guard = _Guard(limit)
    guarded = guard.visit(tree)
    ast.fix_missing_locations(guarded)
    return ast.unparse(guarded) + "\n"


def count_loops(source: str) -> int:
    """How many loops a program contains, for reporting."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError) as error:
        raise LoopGuardError(f"cannot parse program: {type(error).__name__}") from error
    return sum(1 for node in ast.walk(tree) if isinstance(node, (ast.While, ast.For)))


__all__ = [
    "COUNTER_NAME",
    "DEFAULT_ITERATION_LIMIT",
    "LoopGuardError",
    "count_loops",
    "guard_loops",
]
