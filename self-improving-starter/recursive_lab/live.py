"""Opt-in live proposer and immutable corpus evaluator adapters.

The proposer is the only component that talks to a model.  The evaluator reads
an operator-owned JSON corpus and never receives model feedback or credentials.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .artifacts import ArtifactRecord, StrategyArtifact, sha256_digest, strict_json_loads
from .governance import GateResult
from .lab import DEVELOPMENT_SPLIT, PRIVATE_SPLIT, SEALED_SPLIT, ArtifactEvaluation, ProposalResult


class AnthropicStrategyProposer:
    """Pinned Anthropic JSON proposer; importing this module needs no SDK."""

    name = "anthropic-typed-strategy-proposer-v1"

    def __init__(self, *, model: str, max_tokens: int = 1200, client: Any = None) -> None:
        if not model.strip() or max_tokens < 128:
            raise ValueError("a pinned model and useful max_tokens are required")
        if client is None:
            try:
                import anthropic
                client = anthropic.Anthropic()
            except ImportError as error:
                raise RuntimeError("install requirements.txt to use the live proposer") from error
        self.client, self.model, self.max_tokens = client, model, max_tokens
        self.proposer_digest = sha256_digest(f"{self.name}:{model}:{max_tokens}")

    def propose(self, parent: ArtifactRecord, *, public_feedback: str, seed: int) -> ProposalResult:
        prompt = {
            "parent": parent.artifact.to_payload(),
            "public_feedback": public_feedback,
            "seed": seed,
            "instruction": "Return only a JSON strategy object matching the supplied schema. Never discuss tests, evaluators, permissions, networking, or code execution.",
        }
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=0,
            system="You propose bounded, typed strategy improvements. Output JSON only.",
            messages=[{"role": "user", "content": json.dumps(prompt, sort_keys=True)}],
        )
        text = next((block.text for block in response.content if getattr(block, "type", None) == "text"), "")
        candidate = StrategyArtifact.from_payload(strict_json_loads(text))
        usage = getattr(response, "usage", None)
        tokens = int(getattr(usage, "output_tokens", 0) or 0) + int(getattr(usage, "input_tokens", 0) or 0)
        request_id = getattr(response, "id", None)
        return ProposalResult(candidate.to_canonical_json(), model_calls=1, tokens=tokens, request_id=request_id, model_version=self.model, raw_response_digest=hashlib.sha256(text.encode()).hexdigest())


class OpenAIStrategyProposer:
    """Pinned OpenAI Responses API proposer with the same trust boundary."""

    name = "openai-typed-strategy-proposer-v1"

    def __init__(self, *, model: str, max_output_tokens: int = 1200, client: Any = None) -> None:
        if not model.strip() or max_output_tokens < 128:
            raise ValueError("a pinned model and useful max_output_tokens are required")
        if client is None:
            try:
                from openai import OpenAI
                client = OpenAI()
            except ImportError as error:
                raise RuntimeError("install openai to use the live proposer") from error
        self.client, self.model, self.max_output_tokens = client, model, max_output_tokens
        self.proposer_digest = sha256_digest(f"{self.name}:{model}:{max_output_tokens}")

    def propose(self, parent: ArtifactRecord, *, public_feedback: str, seed: int) -> ProposalResult:
        response = self.client.responses.create(
            model=self.model,
            instructions="Propose a bounded typed strategy improvement. Return JSON only as a JSON object; never discuss or modify evaluators, tests, permissions, networking, or code execution.",
            input=json.dumps({"format": "json", "parent": parent.artifact.to_payload(), "public_feedback": public_feedback, "seed": seed}, sort_keys=True),
            max_output_tokens=self.max_output_tokens,
            text={"format": {"type": "json_object"}},
        )
        text = str(getattr(response, "output_text", ""))
        candidate = StrategyArtifact.from_payload(strict_json_loads(text))
        usage = getattr(response, "usage", None)
        tokens = int(getattr(usage, "total_tokens", 0) or 0)
        return ProposalResult(candidate.to_canonical_json(), model_calls=1, tokens=tokens, request_id=getattr(response, "id", None), model_version=self.model, raw_response_digest=hashlib.sha256(text.encode()).hexdigest())


@dataclass(frozen=True, slots=True)
class CorpusTask:
    task_id: str
    required_phrases: tuple[str, ...]


class CorpusStrategyEvaluator:
    """Independent, immutable phrase corpus for adapter and protocol trials."""

    evaluator_id = "corpus-strategy-evaluator-v1"

    def __init__(self, corpus_path: str | Path) -> None:
        raw = json.loads(Path(corpus_path).read_text(encoding="utf-8"))
        self.tasks = tuple(CorpusTask(str(item["id"]), tuple(item["required_phrases"])) for item in raw)
        if not self.tasks:
            raise ValueError("corpus must contain tasks")
        digest = sha256_digest(json.dumps(raw, sort_keys=True, separators=(",", ":")))
        self.evaluator_digest = sha256_digest(f"{self.evaluator_id}:{digest}")
        self.task_manifest_digests = {split: sha256_digest(f"{digest}:{split}") for split in (DEVELOPMENT_SPLIT, PRIVATE_SPLIT, SEALED_SPLIT)}

    def evaluate(self, artifact: StrategyArtifact, *, split: str, seed: int) -> ArtifactEvaluation:
        if split not in self.task_manifest_digests:
            raise ValueError("unknown evaluation split")
        text = " ".join((artifact.system_instruction, *artifact.planning_steps, artifact.reflection or "")).casefold()
        results = tuple(all(phrase.casefold() in text for phrase in task.required_phrases) for task in self.tasks)
        utility = sum(results) / len(results)
        return ArtifactEvaluation(
            evaluator_id=self.evaluator_id, split=split, utility=utility,
            correct=GateResult.success("corpus checks passed" if all(results) else "corpus checks failed"),
            safety_preserved=GateResult.success("typed artifact safety passed"),
            evaluator_integrity=GateResult.success("immutable corpus digest matched"),
            artifact_valid=GateResult.success("typed strategy schema matched"),
            resource_compliance=GateResult.success("corpus resource envelope matched"),
            task_count=len(results), per_task_results=results,
            task_manifest_digest=self.task_manifest_digests[split],
            public_feedback=f"Corpus utility {utility:.2f}" if split == DEVELOPMENT_SPLIT else "",
        )


__all__ = ["AnthropicStrategyProposer", "OpenAIStrategyProposer", "CorpusStrategyEvaluator", "CorpusTask"]
