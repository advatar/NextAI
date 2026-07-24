import hashlib
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recursive_lab.alphaevolve import ProgramRecord, PromptSample
from recursive_lab.longemma_adapter import LongemmaProposer, parse_complete_program
from recursive_lab.quality_diversity import CandidateEvaluation


class Usage:
    prompt_tokens = 3
    completion_tokens = 4
    total_tokens = 7


class Response:
    text = '{"program":"def solve():\\n    return 1"}'
    model = "gemma-test"
    backend_name = "mock"
    usage = Usage()


class Backend:
    name = "mock"
    version = "test-1"

    def generate(self, *args, **kwargs):
        return Response()


class FailingBackend:
    name = "failing-mock"
    version = "test-2"

    def generate(self, *args, **kwargs):
        raise RuntimeError("fixture failure")


class AdapterTests(unittest.TestCase):
    def test_parser_and_receipt(self):
        parent = ProgramRecord(
            "p",
            "def solve(): return 0",
            CandidateEvaluation(0, (0,), {}),
            0,
            None,
            (),
            "seed",
        )
        proposer = LongemmaProposer(Backend(), "write solve")
        candidate = proposer.propose(PromptSample(parent, (), {}), random.Random(1))
        self.assertIn("return 1", candidate)
        self.assertEqual(len(proposer.receipts), 1)
        self.assertTrue(proposer.receipts[0].parse_ok)
        self.assertEqual(proposer.receipts[0].backend_version, "test-1")
        self.assertEqual(
            proposer.receipts[0].candidate_digest,
            hashlib.sha256(candidate.encode()).hexdigest(),
        )

    def test_parser_rejects_empty(self):
        with self.assertRaises(ValueError):
            parse_complete_program('{"wrong": "x"}')

    def test_failed_generation_is_charged_with_a_receipt(self):
        parent = ProgramRecord(
            "p",
            "def solve(): return 0",
            CandidateEvaluation(0, (0,), {}),
            0,
            None,
            (),
            "seed",
        )
        proposer = LongemmaProposer(FailingBackend(), "write solve")

        with self.assertRaisesRegex(ValueError, "fixture failure"):
            proposer.propose(PromptSample(parent, (), {}), random.Random(1))

        self.assertEqual(len(proposer.receipts), 1)
        receipt = proposer.receipts[0]
        self.assertFalse(receipt.parse_ok)
        self.assertIsNone(receipt.candidate_digest)
        self.assertEqual(receipt.backend_version, "test-2")
        self.assertIn("RuntimeError", receipt.error)


if __name__ == "__main__":
    unittest.main()
