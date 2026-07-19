"""RLVR reward: Reinforcement Learning with Verifiable Rewards.

The reward for an RL rollout is the environment's **execution-grounded** score of
the code the policy generated — the model's text is run in the sandbox and graded
by what it actually does, not only by a learned reward model. Execution can still
be reward-hacked when the candidate shares a trust boundary with the evaluator,
so this module refuses to run unless the operator explicitly marks the process
as a dedicated isolated reward worker.

verl calls a reward function with the generated string (and dataset metadata). We
extract the candidate source, score it against the environment, and return the
normalized reward. Broken generations score <= 0 rather than raising.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make the project root importable when verl runs this as a plugin.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from environments import REGISTRY  # noqa: E402
from proposer import _strip_fences  # reuse the fence stripper  # noqa: E402

# Environments are cheap to construct but calibrate on init; cache per name.
_ENV_CACHE: dict = {}


def _env(name: str):
    if name not in _ENV_CACHE:
        _ENV_CACHE[name] = REGISTRY[name]()
    return _ENV_CACHE[name]


def compute_score(data_source: str, solution_str: str, ground_truth=None, extra_info=None) -> float:
    """verl-compatible reward function.

    `data_source` carries the environment name (set by rl/dataset.py). `solution_str`
    is the model's raw generation. Returns the execution-verified normalized reward.
    """
    if os.environ.get("RECURSIVE_LAB_ISOLATED_REWARD_WORKER") != "1":
        raise RuntimeError(
            "RLVR execution is disabled in the trainer process. Route rewards "
            "through a dedicated isolated worker and set "
            "RECURSIVE_LAB_ISOLATED_REWARD_WORKER=1 only inside that worker."
        )
    env_name = (extra_info or {}).get("env", data_source)
    if env_name not in REGISTRY:
        return -1.0
    candidate = _strip_fences(solution_str)
    result = _env(env_name).score(candidate)
    return float(result.reward)
