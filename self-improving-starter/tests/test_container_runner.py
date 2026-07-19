from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from container_runner import (  # noqa: E402
    ContainerPolicy,
    container_runtime_available,
    run_python_container,
)


class ContainerRunnerTests(unittest.TestCase):
    image = "python:3.12-slim"

    @classmethod
    def setUpClass(cls):
        if not container_runtime_available(cls.image):
            raise unittest.SkipTest(f"reviewed local image {cls.image} is unavailable")

    def policy(self, **changes):
        values = {
            "image": self.image,
            "timeout_seconds": 10.0,
            "memory_megabytes": 64,
            "cpu_count": 0.5,
            "pids_limit": 16,
            "tmpfs_megabytes": 8,
            "max_output_bytes": 4096,
        }
        values.update(changes)
        return ContainerPolicy(**values)

    def assert_container_removed(self, name):
        result = subprocess.run(
            ["docker", "ps", "-a", "--quiet", "--filter", f"name=^{name}$"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.stdout.strip(), "")

    def test_executes_as_nonroot_with_read_only_root_and_sanitized_environment(self):
        source = """
import os
assert os.getuid() == 65534
assert 'RECURSIVE_LAB_PARENT_SECRET' not in os.environ
try:
    open('/escape', 'w').write('no')
except OSError:
    pass
else:
    raise SystemExit('root filesystem was writable')
open('/tmp/allowed', 'w').write('yes')
print('contained')
"""
        with mock.patch.dict(os.environ, {"RECURSIVE_LAB_PARENT_SECRET": "canary"}):
            result = run_python_container(source, policy=self.policy())
        self.assertTrue(result.ok, repr(result))
        self.assertEqual(result.stdout.strip(), "contained")
        self.assertTrue(result.image_id.startswith("sha256:"))
        self.assert_container_removed(result.container_name)

    def test_network_is_disabled(self):
        source = """
import socket
try:
    socket.create_connection(('1.1.1.1', 53), timeout=0.2)
except OSError:
    print('blocked')
else:
    raise SystemExit('network unexpectedly available')
"""
        result = run_python_container(source, policy=self.policy())
        self.assertTrue(result.ok, result.stderr)
        self.assertEqual(result.stdout.strip(), "blocked")
        self.assert_container_removed(result.container_name)

    def test_candidate_failure_is_not_reported_as_success(self):
        result = run_python_container(
            "raise RuntimeError('expected fixture failure')\n",
            policy=self.policy(),
        )
        self.assertFalse(result.ok)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.failure_kind, "candidate_failed")
        self.assertIn("expected fixture failure", result.stderr)
        self.assert_container_removed(result.container_name)

    def test_timeout_fails_closed_and_removes_container(self):
        result = run_python_container(
            "while True: pass\n",
            policy=self.policy(timeout_seconds=0.3),
        )
        self.assertFalse(result.ok)
        self.assertTrue(result.timed_out)
        self.assertEqual(result.failure_kind, "timeout")
        self.assertTrue(result.cleanup_succeeded)
        self.assert_container_removed(result.container_name)

    def test_output_limit_fails_closed_and_removes_container(self):
        result = run_python_container(
            "while True: print('x' * 1000)\n",
            policy=self.policy(max_output_bytes=2048),
        )
        self.assertFalse(result.ok)
        self.assertTrue(result.output_limit_exceeded)
        self.assertEqual(result.failure_kind, "output_limit")
        self.assertLessEqual(len(result.stdout.encode()), 2048)
        self.assert_container_removed(result.container_name)


if __name__ == "__main__":
    unittest.main()
