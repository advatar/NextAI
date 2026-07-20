"""Deterministic executable task: count primes below n."""
from __future__ import annotations
import math
import textwrap
from sandbox import run_python
from .base import Environment, ScoreResult
from .optimize_function import _validate_candidate

def _oracle(n: int) -> int:
    return sum(1 for value in range(max(0, n)) if value > 1 and all(value % d for d in range(2, math.isqrt(value) + 1)))

class CountPrimesEnv(Environment):
    name = "count_primes"
    @property
    def task_prompt(self) -> str:
        return textwrap.dedent("""Count prime integers below n. Contract: solve(n) returns the exact count for every integer n. Return only a Python module defining solve(n), with no imports or I/O.""")
    @property
    def starting_solution(self) -> str:
        return "def solve(n):\n    total = 0\n    for value in range(n):\n        if value > 1:\n            prime = 1\n            for divisor in range(2, value):\n                if value % divisor == 0:\n                    prime = 0\n                    break\n            total += prime\n    return total\n"
    def score(self, solution_source: str) -> ScoreResult:
        _, error = _validate_candidate(solution_source)
        if error: return ScoreResult(-1.0, False, None, error)
        cases = (-10, 0, 1, 2, 3, 10, 100, 999)
        checks = "\n".join(f"print('R', {i}, solve({n}))" for i, n in enumerate(cases))
        result = run_python(solution_source + "\n" + checks, timeout_s=5)
        if not result.ok: return ScoreResult(-1.0, False, None, "candidate execution failed")
        got = {}
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) == 3 and parts[0] == "R": got[int(parts[1])] = int(parts[2])
        correct = len(got) == len(cases) and all(got[i] == _oracle(n) for i, n in enumerate(cases))
        return ScoreResult(1.0 if correct else -1.0, correct, None, "correctness cases passed" if correct else "hidden correctness mismatch")
