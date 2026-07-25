"""Non-executing evaluator for a tiny, expression-only ``solve(n)`` language."""

from __future__ import annotations

import ast
import operator


class NumericProgramError(ValueError):
    pass


_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_COMPARE = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}


def parse_solve_expression(source: str) -> ast.expr:
    if not isinstance(source, str) or len(source.encode("utf-8")) > 16 * 1024:
        raise NumericProgramError("candidate must be UTF-8 text under 16 KiB")
    try:
        module = ast.parse(source, mode="exec")
    except (SyntaxError, ValueError, RecursionError) as error:
        raise NumericProgramError("invalid Python syntax") from error
    body = list(module.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    if len(body) != 1 or not isinstance(body[0], ast.FunctionDef):
        raise NumericProgramError("module must contain only def solve(n)")
    function = body[0]
    arguments = [*function.args.posonlyargs, *function.args.args]
    if (
        function.name != "solve"
        or len(arguments) != 1
        or arguments[0].arg != "n"
        or function.decorator_list
        or function.args.defaults
        or function.args.kw_defaults
        or function.args.vararg is not None
        or function.args.kwarg is not None
        or function.args.kwonlyargs
    ):
        raise NumericProgramError("solve must be exactly def solve(n)")
    statements = list(function.body)
    if (
        statements
        and isinstance(statements[0], ast.Expr)
        and isinstance(statements[0].value, ast.Constant)
        and isinstance(statements[0].value.value, str)
    ):
        statements = statements[1:]
    expression: ast.expr | None = None
    if len(statements) == 1 and isinstance(statements[0], ast.Return):
        expression = statements[0].value
    elif len(statements) == 1 and isinstance(statements[0], ast.If):
        branch = statements[0]
        if (
            len(branch.body) == 1
            and isinstance(branch.body[0], ast.Return)
            and len(branch.orelse) == 1
            and isinstance(branch.orelse[0], ast.Return)
            and branch.body[0].value is not None
            and branch.orelse[0].value is not None
        ):
            expression = ast.IfExp(
                test=branch.test,
                body=branch.body[0].value,
                orelse=branch.orelse[0].value,
            )
    if expression is None:
        raise NumericProgramError(
            "solve must contain one return expression or one if/else with returns"
        )
    # Validate by interpreting one harmless input; every recursive branch is
    # structurally checked before conditional selection.
    _evaluate(expression, 0, depth=0, validate_only=True)
    return expression


def _evaluate(node: ast.AST, n: int, *, depth: int, validate_only: bool = False):
    if depth > 64:
        raise NumericProgramError("expression nesting exceeds 64")
    if isinstance(node, ast.Constant):
        if type(node.value) not in (int, bool):
            raise NumericProgramError("only integer and boolean constants are allowed")
        return node.value
    if isinstance(node, ast.Name):
        if node.id != "n":
            raise NumericProgramError("only the input name n is allowed")
        return n
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left = _evaluate(node.left, n, depth=depth + 1, validate_only=validate_only)
        right = _evaluate(node.right, n, depth=depth + 1, validate_only=validate_only)
        if isinstance(node.op, ast.Pow) and (not isinstance(right, int) or abs(right) > 8):
            raise NumericProgramError("power exponent must be an integer from -8 to 8")
        if validate_only and isinstance(node.op, (ast.FloorDiv, ast.Mod)) and right == 0:
            right = 1
        try:
            result = _BINARY[type(node.op)](left, right)
        except (ArithmeticError, OverflowError) as error:
            raise NumericProgramError("invalid arithmetic") from error
        if type(result) is not int or abs(result) > 10**30:
            raise NumericProgramError("result leaves the bounded integer domain")
        return result
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](
            _evaluate(node.operand, n, depth=depth + 1, validate_only=validate_only)
        )
    if (
        isinstance(node, ast.Compare)
        and len(node.ops) == 1
        and len(node.comparators) == 1
        and type(node.ops[0]) in _COMPARE
    ):
        left = _evaluate(node.left, n, depth=depth + 1, validate_only=validate_only)
        right = _evaluate(
            node.comparators[0], n, depth=depth + 1, validate_only=validate_only
        )
        return _COMPARE[type(node.ops[0])](left, right)
    if isinstance(node, ast.IfExp):
        condition = _evaluate(node.test, n, depth=depth + 1, validate_only=validate_only)
        # Validate both branches even though only one supplies the value.
        body = _evaluate(node.body, n, depth=depth + 1, validate_only=validate_only)
        alternative = _evaluate(
            node.orelse, n, depth=depth + 1, validate_only=validate_only
        )
        return body if condition else alternative
    raise NumericProgramError(f"disallowed syntax: {type(node).__name__}")


def evaluate_solve(expression: ast.expr, n: int) -> int:
    if type(n) is not int:
        raise TypeError("n must be an integer")
    result = _evaluate(expression, n, depth=0)
    if type(result) is not int:
        raise NumericProgramError("solve result must be an integer")
    return result
