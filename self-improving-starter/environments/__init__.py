from .base import Environment, ScoreResult
from .optimize_function import OptimizeFunctionEnv
from .count_primes import CountPrimesEnv
from .sum_digits import SumDigitsEnv

REGISTRY = {
    OptimizeFunctionEnv.name: OptimizeFunctionEnv,
    CountPrimesEnv.name: CountPrimesEnv,
    SumDigitsEnv.name: SumDigitsEnv,
}

__all__ = ["Environment", "ScoreResult", "OptimizeFunctionEnv", "CountPrimesEnv", "SumDigitsEnv", "REGISTRY"]
