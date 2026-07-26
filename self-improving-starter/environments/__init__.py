from .base import Environment, ScoreResult
from .optimize_function import OptimizeFunctionEnv
from .count_primes import CountPrimesEnv
from .sum_digits import SumDigitsEnv
from .count_primes_v2 import CountPrimesV2Env
from .power_mod import PowerModEnv
from .timed_task import TimedTaskEnvironment

REGISTRY = {
    OptimizeFunctionEnv.name: OptimizeFunctionEnv,
    CountPrimesEnv.name: CountPrimesEnv,
    SumDigitsEnv.name: SumDigitsEnv,
    CountPrimesV2Env.name: CountPrimesV2Env,
    PowerModEnv.name: PowerModEnv,
}

#: Tasks E63 rejected as unable to measure an improvement, kept registered so
#: the historical records that used them stay interpretable.  ``count_primes``
#: normalised against a single noisy sample and clamped the reward; sum_digits
#: ships already solved.  Nothing should score a search on these.
E63_REJECTED = ("count_primes", "sum_digits")

__all__ = [
    "Environment",
    "ScoreResult",
    "OptimizeFunctionEnv",
    "CountPrimesEnv",
    "SumDigitsEnv",
    "CountPrimesV2Env",
    "PowerModEnv",
    "TimedTaskEnvironment",
    "REGISTRY",
    "E63_REJECTED",
]
