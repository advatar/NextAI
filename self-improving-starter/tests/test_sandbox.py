from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from sandbox import run_python


class RunPythonTests(unittest.TestCase):
    def test_success_has_bounded_resource_metadata(self) -> None:
        result = run_python("print('hello')\n", timeout_s=1.0)

        self.assertTrue(result.ok)
        self.assertEqual(result.stdout, "hello\n")
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.returncode, 0)
        self.assertFalse(result.timed_out)
        self.assertGreater(result.duration_s, 0.0)
        self.assertEqual(result.stdout_bytes, len(b"hello\n"))
        self.assertEqual(result.stderr_bytes, 0)
        self.assertIsNone(result.termination_signal)

    def test_child_environment_is_sanitized_and_temp_scoped(self) -> None:
        key = "LOCAL_RUNNER_TEST_SECRET"
        old_value = os.environ.get(key)
        os.environ[key] = "must-not-leak"
        try:
            result = run_python(
                "import os\n"
                f"print(os.environ.get({key!r}, 'missing'))\n"
                "print(os.environ['HOME'] == os.getcwd())\n"
                "print(os.environ['TMPDIR'] == os.getcwd())\n",
                timeout_s=1.0,
            )
        finally:
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value

        self.assertTrue(result.ok, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["missing", "True", "True"])

    def test_stdout_and_stderr_are_truncated_without_deadlock(self) -> None:
        result = run_python(
            "import sys\n"
            "sys.stdout.write('x' * 100000)\n"
            "sys.stderr.write('y' * 100000)\n",
            timeout_s=2.0,
            max_output_bytes=257,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.stdout, "x" * 257)
        self.assertEqual(result.stderr, "y" * 257)
        self.assertTrue(result.stdout_truncated)
        self.assertTrue(result.stderr_truncated)
        self.assertEqual(result.stdout_bytes, 100000)
        self.assertEqual(result.stderr_bytes, 100000)

    def test_timeout_handles_binary_output_and_reports_marker(self) -> None:
        result = run_python(
            "import sys\n"
            "sys.stdout.buffer.write('héllo'.encode())\n"
            "sys.stdout.buffer.flush()\n"
            "sys.stderr.buffer.write(b'before-timeout')\n"
            "sys.stderr.buffer.flush()\n"
            "while True:\n"
            "    pass\n",
            timeout_s=0.15,
            max_output_bytes=1024,
        )

        self.assertFalse(result.ok)
        self.assertTrue(result.timed_out)
        self.assertIn("héllo", result.stdout)
        self.assertIn("before-timeout", result.stderr)
        self.assertTrue(result.stderr.endswith("[timeout]"))
        self.assertGreaterEqual(result.duration_s, 0.1)
        if os.name == "posix":
            self.assertEqual(result.termination_signal, 9)

    @unittest.skipUnless(os.name == "posix", "process-group assertion requires POSIX")
    def test_timeout_kills_descendant_process_group(self) -> None:
        with tempfile.TemporaryDirectory() as test_dir:
            marker = Path(test_dir) / "escaped-child.txt"
            child_program = (
                "import pathlib,sys,time;"
                "time.sleep(0.45);"
                "pathlib.Path(sys.argv[1]).write_text('escaped')"
            )
            source = (
                "import subprocess,sys\n"
                f"subprocess.Popen([sys.executable, '-c', {child_program!r}, sys.argv[1]])\n"
                "while True:\n"
                "    pass\n"
            )
            result = run_python(source, argv=[str(marker)], timeout_s=0.12)
            self.assertTrue(result.timed_out)
            time.sleep(0.55)
            self.assertFalse(marker.exists(), "a descendant survived the timed-out session")

    def test_invalid_limits_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            run_python("pass\n", timeout_s=0)
        with self.assertRaises(ValueError):
            run_python("pass\n", max_output_bytes=-1)


if __name__ == "__main__":
    unittest.main()
