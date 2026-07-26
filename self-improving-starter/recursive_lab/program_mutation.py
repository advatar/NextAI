"""Generic AST mutations for candidate programs.

This is the proposer for the first governed search on the deterministic
substrate.  It is deliberately **generic**: the operators perturb constants,
comparisons, operators and guards without any knowledge of what the tasks need.

That restraint is the point.  E9 already recorded the failure mode -- a
deterministic exploiter that "encodes useful compositional bias" proves nothing,
because the search is then rediscovering an answer the author planted.  A
template like "insert a negative-number guard" would solve three of the four
tasks by construction and would be worthless as evidence.  These operators are
the kind of edit a mutation fuzzer makes, and they are expected to find some
fixes and miss others.

Every mutation stays inside the candidate subset enforced by
``environments.optimize_function._validate_candidate``: no imports, no calls
except ``range``, no attributes, no comprehensions.  Mutations that would leave
the subset are simply not generated, and the search validates anyway.

Only the standard library is used, and nothing here scores or selects -- the
proposer never sees a reward.
"""

from __future__ import annotations

import ast
import random
from dataclasses import dataclass
from typing import Callable, Iterator

#: Comparison operators are swapped within this family, which is where
#: off-by-one and boundary bugs live.
_COMPARISON_SWAPS: dict[type, tuple[type, ...]] = {
    ast.Lt: (ast.LtE, ast.Gt, ast.GtE),
    ast.LtE: (ast.Lt, ast.GtE, ast.Gt),
    ast.Gt: (ast.GtE, ast.Lt, ast.LtE),
    ast.GtE: (ast.Gt, ast.LtE, ast.Lt),
    ast.Eq: (ast.NotEq,),
    ast.NotEq: (ast.Eq,),
}

#: Arithmetic operator swaps, kept to pairs that preserve integer semantics.
_BINOP_SWAPS: dict[type, tuple[type, ...]] = {
    ast.Add: (ast.Sub,),
    ast.Sub: (ast.Add,),
    ast.Mult: (ast.FloorDiv,),
    ast.FloorDiv: (ast.Mult,),
    ast.Mod: (ast.FloorDiv,),
}

#: Perturbations applied to integer constants.
_CONSTANT_DELTAS = (1, -1, 2, -2)


class MutationError(ValueError):
    """Raised when a program cannot be mutated."""


@dataclass(frozen=True)
class Mutation:
    """One applied edit, recorded so a lineage can explain what changed."""

    operator: str
    detail: str


def _integer_constants(tree: ast.AST) -> list[ast.Constant]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
    ]


def _mutate_constant(tree: ast.AST, rng: random.Random) -> Mutation | None:
    nodes = _integer_constants(tree)
    if not nodes:
        return None
    node = rng.choice(nodes)
    before = node.value
    choice = rng.random()
    if choice < 0.35:
        node.value = -before
        how = "negate"
    elif choice < 0.85:
        node.value = before + rng.choice(_CONSTANT_DELTAS)
        how = "offset"
    else:
        node.value = 0 if before != 0 else 1
        how = "zero-toggle"
    return Mutation("constant", f"{how} {before} -> {node.value}")


def _mutate_comparison(tree: ast.AST, rng: random.Random) -> Mutation | None:
    nodes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Compare)
        and len(node.ops) == 1
        and type(node.ops[0]) in _COMPARISON_SWAPS
    ]
    if not nodes:
        return None
    node = rng.choice(nodes)
    before = type(node.ops[0])
    after = rng.choice(_COMPARISON_SWAPS[before])
    node.ops[0] = after()
    return Mutation("comparison", f"{before.__name__} -> {after.__name__}")


def _mutate_binop(tree: ast.AST, rng: random.Random) -> Mutation | None:
    nodes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOP_SWAPS
    ]
    if not nodes:
        return None
    node = rng.choice(nodes)
    before = type(node.op)
    after = rng.choice(_BINOP_SWAPS[before])
    node.op = after()
    return Mutation("binop", f"{before.__name__} -> {after.__name__}")


def _mutate_negate_name(tree: ast.AST, rng: random.Random) -> Mutation | None:
    """Wrap a loaded name in unary minus, or unwrap one already wrapped.

    Generic sign manipulation. It is not a "handle negative inputs" template:
    it fires anywhere a name is read, usually unhelpfully.
    """
    wrapped = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Name)
    ]
    if wrapped and rng.random() < 0.5:
        node = rng.choice(wrapped)
        name = node.operand.id
        _replace_node(tree, node, ast.Name(id=name, ctx=ast.Load()))
        return Mutation("unnegate", f"-{name} -> {name}")

    names = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    ]
    if not names:
        return None
    node = rng.choice(names)
    _replace_node(
        tree, node, ast.UnaryOp(op=ast.USub(), operand=ast.Name(id=node.id, ctx=ast.Load()))
    )
    return Mutation("negate", f"{node.id} -> -{node.id}")


def _mutate_swap_branches(tree: ast.AST, rng: random.Random) -> Mutation | None:
    nodes = [
        node for node in ast.walk(tree) if isinstance(node, ast.If) and node.orelse
    ]
    if not nodes:
        return None
    node = rng.choice(nodes)
    node.body, node.orelse = node.orelse, node.body
    return Mutation("swap-branches", "if/else bodies exchanged")


def _replace_node(tree: ast.AST, target: ast.AST, replacement: ast.AST) -> None:
    for parent in ast.walk(tree):
        for field, value in ast.iter_fields(parent):
            if value is target:
                setattr(parent, field, replacement)
                return
            if isinstance(value, list):
                for index, item in enumerate(value):
                    if item is target:
                        value[index] = replacement
                        return


_OPERATORS: tuple[Callable[[ast.AST, random.Random], Mutation | None], ...] = (
    _mutate_constant,
    _mutate_comparison,
    _mutate_binop,
    _mutate_negate_name,
    _mutate_swap_branches,
)


def mutate(source: str, rng: random.Random, *, edits: int = 1) -> tuple[str, tuple[Mutation, ...]]:
    """Apply ``edits`` random mutations and return the new source and lineage."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError) as error:
        raise MutationError(f"cannot parse program: {type(error).__name__}") from error

    applied: list[Mutation] = []
    for _ in range(max(1, edits)):
        order = list(_OPERATORS)
        rng.shuffle(order)
        for operator in order:
            result = operator(tree, rng)
            if result is not None:
                applied.append(result)
                break
    if not applied:
        raise MutationError("no mutation operator applied")
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n", tuple(applied)


def mutation_stream(
    source: str, rng: random.Random, *, edits: int = 1
) -> Iterator[tuple[str, tuple[Mutation, ...]]]:
    """Endless stream of mutated programs, each derived from ``source``."""
    while True:
        try:
            yield mutate(source, rng, edits=edits)
        except MutationError:
            continue


__all__ = ["Mutation", "MutationError", "mutate", "mutation_stream"]
