from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from environments.base import ScoreResult  # noqa: E402
from rl import reward  # noqa: E402


class FixtureEnvironment:
    def score(self, candidate):
        return ScoreResult(0.75, True, 1.0, candidate)


class RlRewardBoundaryTests(unittest.TestCase):
    def tearDown(self):
        reward._ENV_CACHE.clear()

    def test_trainer_process_execution_is_disabled_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "dedicated isolated worker"):
                reward.compute_score("fixture", "def solve(n): return n")

    def test_explicit_isolated_worker_can_use_registered_environment(self):
        with mock.patch.dict(reward.REGISTRY, {"fixture": FixtureEnvironment}):
            with mock.patch.dict(
                os.environ, {"RECURSIVE_LAB_ISOLATED_REWARD_WORKER": "1"}, clear=True
            ):
                score = reward.compute_score("fixture", "def solve(n): return n")
        self.assertEqual(score, 0.75)


if __name__ == "__main__":
    unittest.main()
