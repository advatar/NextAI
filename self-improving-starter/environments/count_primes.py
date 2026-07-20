"""Deterministic executable task: count primes below n."""
from __future__ import annotations
import math
import textwrap
import time
from sandbox import run_python
from .base import Environment, ScoreResult
from .optimize_function import _validate_candidate

def _oracle(n: int) -> int:
    return sum(1 for value in range(max(0, n)) if value > 1 and all(value % d for d in range(2, math.isqrt(value) + 1)))

class CountPrimesEnv(Environment):
    name = "count_primes"
    def __init__(self) -> None:
        self._baseline_time = self._measure(self.starting_solution)
    @property
    def task_prompt(self) -> str:
        return textwrap.dedent("""Count prime integers below n. Contract: solve(n) returns the exact count for every integer n. Return only a Python module defining solve(n), with no imports or I/O. Use only integer arithmetic, range, loops, conditionals, and local variables; do not call max, int, sum, all, or sqrt.""")
    @property
    def starting_solution(self) -> str:
        return "def solve(n):\n    total = 0\n    for value in range(n):\n        if value > 1:\n            prime = 1\n            for divisor in range(2, value):\n                if value % divisor == 0:\n                    prime = 0\n                    break\n            total += prime\n    return total\n"
    def score(self, solution_source: str) -> ScoreResult:
        _, error = _validate_candidate(solution_source)
        if error: return ScoreResult(-1.0, False, None, error)
        cases = (-10, 0, 1, 2, 3, 10, 100, 999)
        checks = "\n".join(f"print('R', {i}, solve({n}))" for i, n in enumerate(cases))
        checks += "\n_t=time.perf_counter(); [solve(999) for _ in range(3)]; print('T', time.perf_counter()-_t)"
        result = run_python("import time\n" + solution_source + "\n" + checks, timeout_s=5)
        if not result.ok: return ScoreResult(-1.0, False, None, "candidate execution failed")
        got = {}
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) == 3 and parts[0] == "R": got[int(parts[1])] = int(parts[2])
        correct = len(got) == len(cases) and all(got[i] == _oracle(n) for i, n in enumerate(cases))
        timing = next((float(line.split()[1]) for line in result.stdout.splitlines() if line.startswith('T ')), None)
        if not correct or timing is None: return ScoreResult(-1.0, False, timing, "hidden correctness mismatch")
        if solution_source.strip() == self.starting_solution.strip():
            return ScoreResult(0.0, True, timing, f"correct; {timing*1e3:.3f} ms (baseline)")
        reward = max(0.0, min(1.0, (self._baseline_time - timing) / self._baseline_time))
        return ScoreResult(round(reward, 4), True, timing, f"correct; {timing*1e3:.3f} ms")

    def _measure(self, source: str) -> float:
        result = run_python("import time\n" + source + "\n_t=time.perf_counter(); [solve(999) for _ in range(3)]; print(time.perf_counter()-_t)")
        if not result.ok: return 1.0
        return float(result.stdout.strip().splitlines()[-1])
