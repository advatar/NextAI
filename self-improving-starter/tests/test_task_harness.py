from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from recursive_lab.task_harness import ExecutableTaskSuite  # noqa: E402


class ExecutableTaskSuiteTests(unittest.TestCase):
    def test_manifest_is_stable_and_baseline_is_executable(self):
        suite = ExecutableTaskSuite()
        self.assertEqual(suite.manifest_digest, ExecutableTaskSuite().manifest_digest)
        result = suite.baseline()[0]
        self.assertTrue(result.correct)
        self.assertGreaterEqual(result.reward, 0.0)

    def test_invalid_task_is_rejected(self):
        with self.assertRaises(ValueError):
            ExecutableTaskSuite(("not-a-task",))


if __name__ == "__main__":
    unittest.main()
