"""Loop guarding must bound work without changing correct programs.

E70 was defeated twice by the same underlying issue. A mutation search emits
non-terminating programs at a 25-58% rate, and a wall-clock timeout is the wrong
instrument for them: too long and the run never finishes (E70 spent 2h11m
accumulating 39s of CPU), too short and correct programs fail spuriously (E70b's
null_only control scored -0.4444 where exactly 0.0 is required). Bounding
iterations instead makes the result deterministic and independent of load.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from recursive_lab.loop_guard import (  # noqa: E402
    COUNTER_NAME,
    LoopGuardError,
    count_loops,
    guard_loops,
)

TERMINATING = (
    "def solve(n):\n"
    "    total = 0\n"
    "    for i in range(n):\n"
    "        total += i\n"
    "    return total\n"
)
INFINITE_WHILE = (
    "def solve(n):\n"
    "    value = n\n"
    "    total = 0\n"
    "    while value >= 0:\n"
    "        total += 1\n"
    "        value = value // 10\n"
    "    return total\n"
)
NESTED = (
    "def solve(n):\n"
    "    total = 0\n"
    "    for i in range(n):\n"
    "        for j in range(n):\n"
    "            total += 1\n"
    "    return total\n"
)


def run(source: str, argument: int):
    namespace: dict = {}
    exec(compile(source, "<guarded>", "exec"), namespace)  # noqa: S102 - fixture
    return namespace["solve"](argument)


class CorrectProgramsAreUnchanged(unittest.TestCase):
    def test_results_match_the_unguarded_program(self):
        guarded = guard_loops(TERMINATING)
        for argument in (0, 1, 5, 50, 500):
            self.assertEqual(run(guarded, argument), run(TERMINATING, argument))

    def test_nested_loops_still_compute_correctly(self):
        guarded = guard_loops(NESTED)
        for argument in (0, 1, 4, 12):
            self.assertEqual(run(guarded, argument), run(NESTED, argument))

    def test_guard_is_well_formed_python(self):
        """A malformed splice would raise here rather than at search time."""
        for source in (TERMINATING, NESTED, INFINITE_WHILE):
            compile(guard_loops(source), "<guarded>", "exec")


class NonTerminationBecomesBoundedWork(unittest.TestCase):
    def test_infinite_loop_terminates(self):
        """The whole point: no timeout involved, and it returns.

        Note the argument must be 0. A negative value exits the loop at once
        (``-5 >= 0`` is false); only 0 loops forever, because ``0 // 10 == 0``.
        """
        guarded = guard_loops(INFINITE_WHILE, limit=5_000)
        self.assertEqual(run(guarded, 0), 5_000)

    def test_unguarded_version_really_does_not_terminate(self):
        """Guards the premise: if this program halted, the test above proves
        nothing. Checked structurally rather than by running it."""
        self.assertEqual(run(INFINITE_WHILE, -1), 0)
        self.assertGreater(count_loops(INFINITE_WHILE), 0)

    def test_limit_is_respected_exactly(self):
        for limit in (10, 100, 1_000):
            guarded = guard_loops(INFINITE_WHILE, limit=limit)
            self.assertEqual(run(guarded, 0), limit)

    def test_nested_loops_share_one_budget(self):
        """Per-loop counters would allow limit**2 iterations; one counter does not."""
        guarded = guard_loops(NESTED, limit=50)
        self.assertLessEqual(run(guarded, 1_000), 51)

    def test_counter_resets_between_calls(self):
        """A program must be judged identically on every case."""
        guarded = guard_loops(INFINITE_WHILE, limit=100)
        first = run(guarded, 0)
        second = run(guarded, 0)
        self.assertEqual(first, second)


class GuardMechanics(unittest.TestCase):
    def test_counter_is_declared_at_function_entry(self):
        guarded = guard_loops(TERMINATING)
        body = guarded.splitlines()
        self.assertIn(COUNTER_NAME, body[1])

    def test_count_loops(self):
        self.assertEqual(count_loops(TERMINATING), 1)
        self.assertEqual(count_loops(NESTED), 2)
        self.assertEqual(count_loops("def solve(n):\n    return n\n"), 0)

    def test_program_without_loops_is_untouched_semantically(self):
        source = "def solve(n):\n    return n * 2\n"
        self.assertEqual(run(guard_loops(source), 21), 42)

    def test_invalid_limit_fails_closed(self):
        with self.assertRaises(LoopGuardError):
            guard_loops(TERMINATING, limit=0)

    def test_unparsable_source_fails_closed(self):
        with self.assertRaises(LoopGuardError):
            guard_loops("def solve(:\n")


if __name__ == "__main__":
    unittest.main()
