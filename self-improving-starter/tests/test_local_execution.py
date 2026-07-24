from __future__ import annotations

import argparse
import contextlib
import io
import unittest

from recursive_lab.local_execution import (
    add_unsafe_local_demo_argument,
    require_unsafe_local_demo,
)


class LocalExecutionGateTests(unittest.TestCase):
    def parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(prog="unsafe-fixture")
        add_unsafe_local_demo_argument(parser)
        return parser

    def test_refuses_host_execution_without_explicit_opt_in(self) -> None:
        parser = self.parser()
        args = parser.parse_args([])

        with (
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as raised,
        ):
            require_unsafe_local_demo(parser, args.unsafe_local_demo)

        self.assertEqual(raised.exception.code, 2)

    def test_accepts_explicit_unsafe_local_opt_in(self) -> None:
        parser = self.parser()
        args = parser.parse_args(["--unsafe-local-demo"])

        require_unsafe_local_demo(parser, args.unsafe_local_demo)


if __name__ == "__main__":
    unittest.main()
