from .base import Environment, ScoreResult
from .optimize_function import OptimizeFunctionEnv
from .count_primes import CountPrimesEnv

REGISTRY = {
    OptimizeFunctionEnv.name: OptimizeFunctionEnv,
    CountPrimesEnv.name: CountPrimesEnv,
}

__all__ = ["Environment", "ScoreResult", "OptimizeFunctionEnv", "CountPrimesEnv", "REGISTRY"]
