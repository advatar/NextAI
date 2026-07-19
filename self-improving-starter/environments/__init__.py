from .base import Environment, ScoreResult
from .optimize_function import OptimizeFunctionEnv

REGISTRY = {
    OptimizeFunctionEnv.name: OptimizeFunctionEnv,
}

__all__ = ["Environment", "ScoreResult", "OptimizeFunctionEnv", "REGISTRY"]
