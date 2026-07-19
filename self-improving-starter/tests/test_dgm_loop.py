from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dgm_loop import run_loop  # noqa: E402
from environments.base import Environment, ScoreResult  # noqa: E402


class FixtureEnvironment(Environment):
    name = "fixture"

    def __init__(self):
        self.calls: list[str] = []

    @property
    def task_prompt(self):
        return "improve"

    @property
    def starting_solution(self):
        return "seed"

    def score(self, source):
        self.calls.append(source)
        if source == "seed":
            return ScoreResult(0.0, True, 0.0, "seed")
        if source == "invalid-high":
            return ScoreResult(999.0, False, None, "incorrect")
        if source == "nan":
            return ScoreResult(math.nan, True, None, "nonfinite")
        if source == "inf":
            return ScoreResult(math.inf, True, None, "nonfinite")
        if source == "none-result":
            return None
        if source == "bool-reward":
            return ScoreResult(True, True, None, "bad reward type")
        if source == "bad-correctness":
            return ScoreResult(1.0, "yes", None, "bad correctness type")
        if source == "bad-raw":
            return ScoreResult(1.0, True, math.nan, "bad raw metric")
        if source == "bad-detail":
            return ScoreResult(1.0, True, None, 7)
        if source == "boom":
            raise RuntimeError("evaluator exploded")
        if source.startswith("good"):
            return ScoreResult(float(source[-1]), True, 1.0, "correct")
        return ScoreResult(-1.0, False, None, "bad")


class SequenceProposer:
    def __init__(self, values):
        self.values = iter(values)

    def propose(self, task_prompt, parent_source):
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        return value


class FalseySequenceProposer(SequenceProposer):
    def __bool__(self):
        return False


class HostileError(RuntimeError):
    def __str__(self):
        raise RuntimeError("stringification failed")


class DgmLoopTests(unittest.TestCase):
    def test_injected_proposer_needs_no_model_sdk_and_logs_every_attempt(self):
        env = FixtureEnvironment()
        proposer = SequenceProposer(
            ["invalid-high", "nan", "seed", RuntimeError("provider down"), "boom", "good1"]
        )
        archive, trajectories = run_loop(
            env,
            rounds=6,
            proposer=proposer,
            log=lambda *_: None,
            min_improvement=0.1,
        )

        self.assertEqual(len(trajectories), 6)
        self.assertEqual(
            [trajectory.status for trajectory in trajectories],
            ["rejected", "evaluator_error", "duplicate", "proposer_error", "evaluator_error", "accepted"],
        )
        self.assertEqual(len(archive.nodes), 2)
        self.assertEqual(archive.best().source, "good1")
        self.assertEqual(sum(node.attempts for node in archive.nodes), 6)

    def test_incorrect_and_nonfinite_candidates_never_enter_archive(self):
        env = FixtureEnvironment()
        archive, _ = run_loop(
            env,
            rounds=2,
            proposer=SequenceProposer(["invalid-high", "nan"]),
            log=lambda *_: None,
        )
        self.assertEqual([node.source for node in archive.nodes], ["seed"])

    def test_invalid_proposer_outputs_are_charged_without_evaluation(self):
        env = FixtureEnvironment()
        archive, trajectories = run_loop(
            env,
            rounds=5,
            proposer=SequenceProposer([None, b"bytes", "x" * 11, "\ud800", "good1"]),
            log=lambda *_: None,
            max_candidate_bytes=10,
        )

        self.assertEqual(
            [trajectory.status for trajectory in trajectories],
            ["invalid_candidate"] * 4 + ["accepted"],
        )
        self.assertEqual(env.calls, ["seed", "good1"])
        self.assertEqual(sum(node.attempts for node in archive.nodes), 5)
        self.assertTrue(all(t.solution is None for t in trajectories[:4]))

    def test_malformed_score_results_are_errors_and_never_archived(self):
        env = FixtureEnvironment()
        malformed = [
            "none-result",
            "bool-reward",
            "bad-correctness",
            "bad-raw",
            "bad-detail",
            "inf",
        ]
        archive, trajectories = run_loop(
            env,
            rounds=len(malformed) + 1,
            proposer=SequenceProposer(malformed + ["good1"]),
            log=lambda *_: None,
        )

        self.assertEqual(
            [trajectory.status for trajectory in trajectories],
            ["evaluator_error"] * len(malformed) + ["accepted"],
        )
        self.assertEqual([node.source for node in archive.nodes], ["seed", "good1"])
        self.assertEqual(sum(node.attempts for node in archive.nodes), len(malformed) + 1)
        for trajectory in trajectories[:-1]:
            self.assertIsNone(trajectory.reward)
            self.assertIsNone(trajectory.correct)

    def test_falsey_injected_proposer_is_preserved(self):
        env = FixtureEnvironment()
        archive, trajectories = run_loop(
            env,
            rounds=1,
            proposer=FalseySequenceProposer(["good1"]),
            log=lambda *_: None,
        )
        self.assertEqual(trajectories[0].status, "accepted")
        self.assertEqual(archive.best().source, "good1")

    def test_hostile_exception_stringification_does_not_escape_loop(self):
        env = FixtureEnvironment()
        archive, trajectories = run_loop(
            env,
            rounds=1,
            proposer=SequenceProposer([HostileError()]),
            log=lambda *_: None,
        )
        self.assertEqual(trajectories[0].status, "proposer_error")
        self.assertIn("HostileError", trajectories[0].detail)
        self.assertEqual(sum(node.attempts for node in archive.nodes), 1)

    def test_invalid_loop_configuration_fails_closed(self):
        env = FixtureEnvironment()
        cases = [
            {"rounds": True},
            {"rounds": -1},
            {"rounds": 0, "min_improvement": math.nan},
            {"rounds": 0, "min_improvement": 10**10_000},
            {"rounds": 0, "retain_novel": 1},
            {"rounds": 0, "max_candidate_bytes": True},
            {"rounds": 0, "max_candidate_bytes": 0},
        ]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                run_loop(env, proposer=SequenceProposer([]), log=lambda *_: None, **kwargs)


if __name__ == "__main__":
    unittest.main()
