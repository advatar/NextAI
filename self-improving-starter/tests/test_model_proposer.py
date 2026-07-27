"""The proposer must never see the grading set, and must record what it did.

The trust boundary is the reason this module exists. A proposer shown the hidden
cases, the oracle or the reference solution is not proposing -- it is being told
the answer -- and any improvement it produces measures nothing. ``build_prompt``
takes only public inputs, so the boundary is enforced by the signature.

Receipts matter for the second reason: E58 recorded six model calls that returned
one identical program and reported ``adoption_gate.passed: True`` on a search
that never searched. Digests per call are what let
:mod:`recursive_lab.candidate_diversity` catch that.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from recursive_lab.candidate_diversity import assess_candidate_diversity  # noqa: E402
from recursive_lab.model_proposer import (  # noqa: E402
    ModelProgramProposer,
    build_prompt,
    extract_program,
)

TASK = "solve(n) must return the sum of the decimal digits of abs(n)."
PROGRAM = "def solve(n):\n    return 0\n"
SECRET_CASES = "(-987654, -10001, 12345)"
SECRET_REFERENCE = "def solve(n):\n    return 42\n"


class ScriptedClient:
    """Returns queued replies; records what it was asked."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.seen = []

    def complete(self, *, model, system, user, temperature, max_tokens):
        self.seen.append({"system": system, "user": user, "temperature": temperature})
        text = self.replies.pop(0)
        if isinstance(text, Exception):
            raise text
        return text, 10, 20


class ExplodingClient:
    def complete(self, **kwargs):
        raise ConnectionError("server unreachable")


class TrustBoundary(unittest.TestCase):
    def test_prompt_contains_only_public_inputs(self):
        prompt = build_prompt(TASK, PROGRAM, "passes 9 of 16 cases")
        self.assertIn(TASK, prompt)
        self.assertIn("def solve", prompt)
        self.assertNotIn(SECRET_CASES, prompt)
        self.assertNotIn("42", prompt)

    def test_build_prompt_has_no_channel_for_the_grading_set(self):
        """Structural, not textual: there is no parameter to leak through."""
        import inspect

        parameters = list(inspect.signature(build_prompt).parameters)
        self.assertEqual(
            parameters, ["task_prompt", "current_program", "public_feedback"]
        )

    def test_proposer_sends_nothing_beyond_the_prompt(self):
        client = ScriptedClient(["```python\ndef solve(n):\n    return 1\n```"])
        proposer = ModelProgramProposer(client, model="m")
        proposer.propose(TASK, PROGRAM, "passes 9 of 16 cases")
        sent = client.seen[0]["system"] + client.seen[0]["user"]
        self.assertNotIn(SECRET_REFERENCE, sent)
        self.assertNotIn(SECRET_CASES, sent)


class ProgramExtraction(unittest.TestCase):
    def test_extracts_from_a_fenced_block(self):
        text = "Here:\n```python\ndef solve(n):\n    return n\n```\nDone."
        self.assertIn("def solve", extract_program(text))
        self.assertNotIn("Here:", extract_program(text))

    def test_extracts_from_an_unfenced_reply(self):
        self.assertIsNotNone(extract_program("def solve(n):\n    return n\n"))

    def test_returns_none_without_a_solve_definition(self):
        self.assertIsNone(extract_program("I cannot help with that."))
        self.assertIsNone(extract_program("```python\nx = 1\n```"))


class Receipts(unittest.TestCase):
    def test_successful_call_records_digests_and_tokens(self):
        client = ScriptedClient(["```python\ndef solve(n):\n    return 1\n```"])
        proposer = ModelProgramProposer(client, model="m")
        result = proposer.propose(TASK, PROGRAM, "fb")
        self.assertTrue(result.receipt.parse_ok)
        self.assertEqual(result.receipt.total_tokens, 30)
        self.assertTrue(result.receipt.candidate_digest)
        self.assertIsNone(result.receipt.error)

    def test_unparsable_reply_is_recorded_not_raised(self):
        client = ScriptedClient(["sorry, no"])
        proposer = ModelProgramProposer(client, model="m")
        result = proposer.propose(TASK, PROGRAM, "fb")
        self.assertIsNone(result.candidate)
        self.assertFalse(result.receipt.parse_ok)
        self.assertIn("no solve()", result.receipt.error)

    def test_transport_failure_is_recorded_not_raised(self):
        """A dead server must not abort a search mid-run."""
        proposer = ModelProgramProposer(ExplodingClient(), model="m")
        result = proposer.propose(TASK, PROGRAM, "fb")
        self.assertIsNone(result.candidate)
        self.assertIn("ConnectionError", result.receipt.error)
        self.assertEqual(proposer.calls, 1)

    def test_call_and_token_counters_accumulate(self):
        client = ScriptedClient(["```python\ndef solve(n):\n    return %d\n```" % i for i in range(3)])
        proposer = ModelProgramProposer(client, model="m")
        for _ in range(3):
            proposer.propose(TASK, PROGRAM, "fb")
        self.assertEqual(proposer.calls, 3)
        self.assertEqual(proposer.total_tokens, 90)


class DiversityDetection(unittest.TestCase):
    def test_collapsed_stream_is_void(self):
        """The E58 shape: many calls, one program. Reproduced locally against
        this same model at temperature 1.0, so the check is not hypothetical."""
        reply = "```python\ndef solve(n):\n    return 1\n```"
        client = ScriptedClient([reply] * 6)
        proposer = ModelProgramProposer(client, model="m")
        digests = [
            proposer.propose(TASK, PROGRAM, "fb").receipt.candidate_digest
            for _ in range(6)
        ]
        report = assess_candidate_diversity(digests)
        self.assertEqual(report.total_candidates, 6)
        self.assertEqual(report.unique_candidates, 1)
        self.assertTrue(report.void)

    def test_varied_stream_is_not_void(self):
        client = ScriptedClient(
            ["```python\ndef solve(n):\n    return %d\n```" % i for i in range(6)]
        )
        proposer = ModelProgramProposer(client, model="m")
        digests = [
            proposer.propose(TASK, PROGRAM, "fb").receipt.candidate_digest
            for _ in range(6)
        ]
        report = assess_candidate_diversity(digests)
        self.assertEqual(report.unique_candidates, 6)
        self.assertFalse(report.void)


if __name__ == "__main__":
    unittest.main()
