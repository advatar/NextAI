"""Fail-closed opt-in for experiments that execute model-authored code locally."""

from __future__ import annotations

import argparse

UNSAFE_LOCAL_HELP = (
    "allow model-authored Python to execute on this host without a security "
    "isolation boundary"
)


def add_unsafe_local_demo_argument(parser: argparse.ArgumentParser) -> None:
    """Add the deliberately explicit unsafe-local execution switch."""

    parser.add_argument(
        "--unsafe-local-demo",
        action="store_true",
        help=UNSAFE_LOCAL_HELP,
    )


def require_unsafe_local_demo(parser: argparse.ArgumentParser, enabled: bool) -> None:
    """Refuse local model-authored execution unless the operator opted in."""

    if not enabled:
        parser.error(
            "this experiment executes model-authored Python on the host; "
            "use a reviewed container/VM, or pass --unsafe-local-demo to "
            "acknowledge the local trust boundary"
        )


__all__ = [
    "UNSAFE_LOCAL_HELP",
    "add_unsafe_local_demo_argument",
    "require_unsafe_local_demo",
]
