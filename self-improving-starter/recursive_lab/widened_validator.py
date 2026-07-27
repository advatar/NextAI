"""A wider candidate subset that keeps the properties the narrow one protected.

E75 established the blocker structurally: eight of nine tasks score exactly 1.0
against the 12B proposer, so the outcome variable is constant and no strategy
comparison is possible.  The cause is not any task design.  It is that the
restricted subset enforced by ``environments.optimize_function._validate_candidate``
-- integer arithmetic, no data structures, no builtin except ``range`` -- caps
task difficulty far below the model, because the only expressible problems are
single-function integer manipulations.

Trustworthy evaluation and measurable difficulty were therefore in direct
tension.  This module resolves the tension rather than accepting it, by asking
what the narrow subset was actually protecting and defending those properties
with narrower prohibitions.

What the narrow subset protected, and how this keeps it
------------------------------------------------------

**Reading the grading data.**  The checker appends ``print('R', i, solve(v))``
lines to the candidate's own source, so the case values sit in the same file.  A
candidate that could open its own source, or reach the interpreter's frames,
could read them.  Both routes require either an import or a dunder attribute, and
both remain banned.

**Forging output.**  A candidate could print fabricated ``R`` lines or exit
before the real checks ran.  Printing is blocked because ``print`` is not in the
builtin allowlist, and exiting requires ``sys`` or ``exit``, neither reachable.

**Escaping the sandbox.**  ``open``, ``eval``, ``exec``, ``compile``,
``__import__``, ``globals``, ``locals``, ``vars`` and ``getattr`` are all absent
from the allowlist, and an allowlist is used rather than a denylist so a builtin
that is not reasoned about is unavailable by default.

**Attribute escapes.**  Attribute access is permitted, because string and list
methods are most of what makes richer tasks expressible, but any attribute or
name containing ``__`` is rejected.  That closes the standard
``().__class__.__bases__`` style traversal.

What is deliberately NOT claimed
--------------------------------

This is defence in depth, not a security boundary, exactly as the narrow
validator was.  The boundary is ``sandbox.run_python`` for trusted fixtures and
the reviewed container adapter for untrusted code, and that is unchanged.  A
wider subset means a wider attack surface for a determined adversary; the claim
here is only that the specific properties the grading protocol depends on are
still defended.

The narrow validator is left untouched, so every prior experiment keeps the
subset it was measured under.
"""

from __future__ import annotations

import ast

#: Builtins a candidate may call.  An allowlist, so anything not reasoned about
#: is unavailable.  Notably absent: print, open, eval, exec, compile, input,
#: __import__, globals, locals, vars, getattr, setattr, delattr, dir, exit.
ALLOWED_BUILTINS = frozenset(
    {
        "abs", "all", "any", "bool", "chr", "dict", "divmod", "enumerate",
        "filter",
        "float", "frozenset", "int", "len", "list", "map", "max", "min", "pow",
        "ord", "range", "reversed", "round", "set", "sorted", "str", "sum",
        "tuple",
        "zip",
    }
)

_MAX_CANDIDATE_BYTES = 32 * 1024

#: Node types the wider subset permits.  Comprehensions, data structures,
#: slicing, f-strings and multiple assignment are all allowed; ``import``,
#: ``with``, ``try``, ``global``, ``nonlocal``, ``lambda``, ``yield``, ``await``
#: and class definitions are not, by omission.
_ALLOWED_NODES: tuple[type, ...] = (
    ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return,
    ast.Assign, ast.AugAssign, ast.AnnAssign, ast.For, ast.While, ast.If,
    ast.Break, ast.Continue, ast.Pass, ast.Expr,
    ast.Name, ast.Constant, ast.Attribute, ast.Subscript, ast.Slice,
    ast.Tuple, ast.List, ast.Dict, ast.Set,
    ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.comprehension,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp, ast.Call,
    ast.keyword, ast.Starred, ast.JoinedStr, ast.FormattedValue,
    ast.Load, ast.Store, ast.Del,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.LShift, ast.RShift, ast.BitOr, ast.BitXor, ast.BitAnd, ast.MatMult,
    ast.UAdd, ast.USub, ast.Invert, ast.Not, ast.And, ast.Or,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
    ast.Is, ast.IsNot,
)


def validate_widened(source: str) -> tuple[ast.Module | None, str | None]:
    """Accept a wider but still non-introspective Python subset.

    Returns ``(tree, None)`` when acceptable, or ``(None, reason)``.
    """
    try:
        encoded = len(source.encode("utf-8"))
    except (TypeError, UnicodeError):
        return None, "candidate must be UTF-8 text"
    if encoded > _MAX_CANDIDATE_BYTES:
        return None, "candidate source is too large"

    try:
        tree = ast.parse(source, mode="exec")
    except (SyntaxError, ValueError, RecursionError) as error:
        return None, f"invalid syntax: {type(error).__name__}"

    body = list(tree.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]  # module docstring
    functions = [node for node in body if isinstance(node, ast.FunctionDef)]
    if not functions or len(functions) != len(body):
        return None, "module must contain only function definitions"
    if not any(node.name == "solve" for node in functions):
        return None, "module must define solve(n)"

    solve = next(node for node in functions if node.name == "solve")
    positional = [*solve.args.posonlyargs, *solve.args.args]
    if len(positional) != 1:
        return None, "solve must take exactly one positional argument"
    if solve.decorator_list:
        return None, "decorators are not allowed"

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            return None, f"{type(node).__name__} is not allowed"
        # Dunder access is the standard route to the object graph, and closing
        # it is what makes permitting attributes at all defensible.
        if isinstance(node, ast.Attribute) and "__" in node.attr:
            return None, "dunder attribute access is not allowed"
        if isinstance(node, ast.Name) and "__" in node.id:
            return None, "dunder names are not allowed"
        if isinstance(node, ast.arg) and "__" in node.arg:
            return None, "dunder argument names are not allowed"
        if isinstance(node, ast.FunctionDef) and "__" in node.name:
            return None, "dunder function names are not allowed"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name = node.func.id
            local = {f.name for f in functions}
            if name not in ALLOWED_BUILTINS and name not in local:
                return None, f"calling {name}() is not allowed"

    return tree, None


__all__ = ["ALLOWED_BUILTINS", "validate_widened"]
