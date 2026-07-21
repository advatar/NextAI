"""Executable task: sum decimal digits of the absolute value of n."""
from __future__ import annotations
from sandbox import run_python
from .base import Environment, ScoreResult
from .optimize_function import _validate_candidate

def _oracle(n: int) -> int:
    value = -n if n < 0 else n
    total = 0
    while value:
        total += value % 10
        value //= 10
    return total

class SumDigitsEnv(Environment):
    name = "sum_digits"
    @property
    def task_prompt(self) -> str:
        return "Return a Python module defining solve(n), which returns the sum of the decimal digits of abs(n) for every integer n. Use only integer arithmetic, range, loops, conditionals, and local variables; no imports or I/O."
    @property
    def starting_solution(self) -> str:
        return "def solve(n):\n    value = -n if n < 0 else n\n    total = 0\n    while value:\n        total += value % 10\n        value //= 10\n    return total\n"
    def score(self, solution_source: str) -> ScoreResult:
        _, error = _validate_candidate(solution_source)
        if error: return ScoreResult(-1.0, False, None, error)
        cases = (-10001, -10, -1, 0, 1, 9, 10, 123456789)
        checks = "\n".join(f"print('R', {i}, solve({n}))" for i, n in enumerate(cases))
        result = run_python(solution_source + "\n" + checks, timeout_s=5)
        if not result.ok: return ScoreResult(-1.0, False, None, "candidate execution failed")
        got = {}
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) == 3 and parts[0] == "R": got[int(parts[1])] = int(parts[2])
        correct = len(got) == len(cases) and all(got[i] == _oracle(n) for i, n in enumerate(cases))
        return ScoreResult(1.0 if correct else -1.0, correct, None, "correctness cases passed" if correct else "hidden correctness mismatch")
