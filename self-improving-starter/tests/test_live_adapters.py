from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from recursive_lab.fixtures import baseline_strategy  # noqa: E402
from recursive_lab.lab import DEVELOPMENT_SPLIT  # noqa: E402
from recursive_lab.live import AnthropicStrategyProposer, CorpusStrategyEvaluator, OpenAIStrategyProposer  # noqa: E402
from recursive_lab.artifacts import ArtifactRecord  # noqa: E402


class FakeMessages:
    def create(self, **kwargs):
        self.kwargs = kwargs
        text = json.dumps(baseline_strategy("live").to_payload())
        return SimpleNamespace(id="req_test", content=[SimpleNamespace(type="text", text=text)], usage=SimpleNamespace(input_tokens=10, output_tokens=20))


class FakeClient:
    def __init__(self): self.messages = FakeMessages()


class FakeResponses:
    def create(self, **kwargs):
        self.kwargs = kwargs
        text = json.dumps(baseline_strategy("openai").to_payload())
        return SimpleNamespace(id="resp_test", output_text=text, usage=SimpleNamespace(total_tokens=31))


class FakeOpenAIClient:
    def __init__(self): self.responses = FakeResponses()


class LiveAdapterTests(unittest.TestCase):
    def test_proposer_parses_typed_json_and_records_receipt(self):
        proposer = AnthropicStrategyProposer(model="pinned-test-model", client=FakeClient())
        artifact = baseline_strategy()
        record = ArtifactRecord(artifact, None, 0, proposer.proposer_digest, 0)
        result = proposer.propose(record, public_feedback="public only", seed=4)
        self.assertEqual(result.model_calls, 1)
        self.assertEqual(result.tokens, 30)
        self.assertEqual(result.model_version, "pinned-test-model")

    def test_corpus_evaluator_is_split_private(self):
        with tempfile.TemporaryDirectory() as directory:
            corpus = Path(directory) / "tasks.json"
            corpus.write_text(json.dumps([{"id": "one", "required_phrases": ["carefully"]}]))
            evaluator = CorpusStrategyEvaluator(corpus)
            result = evaluator.evaluate(baseline_strategy(), split=DEVELOPMENT_SPLIT, seed=0)
            self.assertEqual(result.task_count, 1)
            self.assertTrue(result.public_feedback)

    def test_openai_responses_proposer_records_receipt(self):
        proposer = OpenAIStrategyProposer(model="pinned-openai-model", client=FakeOpenAIClient())
        artifact = baseline_strategy()
        record = ArtifactRecord(artifact, None, 0, proposer.proposer_digest, 0)
        result = proposer.propose(record, public_feedback="public only", seed=4)
        self.assertEqual(result.tokens, 31)
        self.assertEqual(result.request_id, "resp_test")


if __name__ == "__main__": unittest.main()
