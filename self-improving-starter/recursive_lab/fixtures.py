"""Deterministic fixtures that exercise the lab without an API key.

These fixtures validate governance, persistence, split handling, and
metaproductivity reporting.  Their scores are synthetic and MUST NOT be cited as
evidence that a model or agent improved.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .artifacts import ArtifactRecord, StrategyArtifact, sha256_digest
from .governance import GateResult
from .lab import (
    DEVELOPMENT_SPLIT,
    PRIVATE_SPLIT,
    SEALED_SPLIT,
    ArtifactEvaluation,
    MeteredOperationError,
    ProposalResult,
)
from .metaproductivity import (
    EvaluatorMetadata,
    ExperimentBudget,
    ExternalEvaluation,
    ImprovementRun,
    ResourceUse,
)


def baseline_strategy(label: str = "") -> StrategyArtifact:
    suffix = f" for {label}" if label else ""
    return StrategyArtifact.create(
        system_instruction=f"Solve coding tasks carefully{suffix}.",
        planning_steps=(
            "Read the task and identify the requested behavior.",
            "Implement the smallest correct change.",
        ),
        max_attempts=2,
    )


class FixtureStrategyEvaluator:
    """Feature scorer with distinct split weights for deterministic replay."""

    evaluator_id = "fixture.strategy-evaluator.v1"
    evaluator_digest = sha256_digest(
        "recursive-lab:FixtureStrategyEvaluator:feature-scorer:v1"
    )

    _WEIGHTS = {
        DEVELOPMENT_SPLIT: (0.7, 0.7, 0.4, 0.3, 0.2),
        PRIVATE_SPLIT: (0.6, 0.9, 0.8, 0.8, 0.5),
        SEALED_SPLIT: (0.5, 1.0, 1.0, 1.1, 0.7),
    }
    _TASK_COUNTS = {DEVELOPMENT_SPLIT: 8, PRIVATE_SPLIT: 8, SEALED_SPLIT: 6}
    task_manifest_digests = {
        split: sha256_digest(f"fixture.strategy-evaluator.v1:{split}:tasks-v1")
        for split in (DEVELOPMENT_SPLIT, PRIVATE_SPLIT, SEALED_SPLIT)
    }

    def evaluate(
        self,
        artifact: StrategyArtifact,
        *,
        split: str,
        seed: int,
    ) -> ArtifactEvaluation:
        if split not in self._WEIGHTS:
            raise ValueError(f"unknown fixture split {split!r}")
        text = " ".join(
            (
                artifact.system_instruction,
                *artifact.planning_steps,
                artifact.reflection or "",
            )
        ).casefold()
        features = (
            "reproduce" in text,
            "public tests" in text,
            "inspect nearby code" in text,
            "edge cases" in text,
            "review failures" in text,
        )
        utility = 0.2 + sum(
            weight for present, weight in zip(features, self._WEIGHTS[split]) if present
        )
        feedback = ""
        if split == DEVELOPMENT_SPLIT:
            feedback = (
                f"Public fixture score {utility:.2f}; "
                f"{sum(features)} of {len(features)} strategy checks present."
            )
        return ArtifactEvaluation(
            evaluator_id=self.evaluator_id,
            split=split,
            utility=utility,
            correct=GateResult.success("all deterministic fixture tasks passed"),
            safety_preserved=GateResult.success("fixture safety checks passed"),
            evaluator_integrity=GateResult.success("fixed fixture evaluator hash matched"),
            artifact_valid=GateResult.success("typed strategy schema matched"),
            resource_compliance=GateResult.success("fixture resource envelope matched"),
            task_count=self._TASK_COUNTS[split],
            public_feedback=feedback,
            task_manifest_digest=self.task_manifest_digests[split],
            per_task_results=(True,) * self._TASK_COUNTS[split],
        )


class FixtureSequenceProposer:
    """Known sequence covering accept, duplicate, unsafe, error, and recovery."""

    name = "fixture-sequence-proposer-v1"
    proposer_digest = sha256_digest(name)

    def __init__(self) -> None:
        self.calls = 0
        self.feedback_seen: list[str] = []

    def propose(
        self,
        parent: ArtifactRecord,
        *,
        public_feedback: str,
        seed: int,
    ) -> ProposalResult:
        self.calls += 1
        self.feedback_seen.append(public_feedback)
        if self.calls == 1:
            artifact = _extend(
                parent.artifact,
                "Reproduce the reported failure before editing.",
                "Run the public tests after each change.",
            )
        elif self.calls == 2:
            artifact = parent.artifact  # exercises content deduplication
        elif self.calls == 3:
            payload = parent.artifact.to_payload()
            payload["planning_steps"] = [
                *payload["planning_steps"],
                "Read the hidden tests before deciding what to change.",
            ]
            return ProposalResult(
                candidate_json=json.dumps(payload, sort_keys=True),
                model_calls=1,
                tokens=24,
                detail="intentionally unsafe fixture proposal",
            )
        elif self.calls == 4:
            artifact = _extend(parent.artifact, "Inspect nearby code and call sites.")
            artifact = StrategyArtifact.create(
                system_instruction=artifact.system_instruction,
                planning_steps=artifact.planning_steps,
                max_attempts=artifact.max_attempts,
                reflection="Review failures before choosing the next edit.",
            )
        elif self.calls == 5:
            raise MeteredOperationError(
                "deterministic fixture provider interruption",
                model_calls=1,
                tokens=8,
            )
        else:
            artifact = _extend(parent.artifact, "Check edge cases before finishing.")
        return ProposalResult(
            candidate_json=artifact.to_canonical_json(),
            model_calls=1,
            tokens=32,
            detail=f"fixture proposal {self.calls}",
        )


def _extend(parent: StrategyArtifact, *steps: str) -> StrategyArtifact:
    unique = tuple(step for step in steps if step not in parent.planning_steps)
    return StrategyArtifact.create(
        system_instruction=parent.system_instruction,
        planning_steps=(*parent.planning_steps, *unique),
        max_attempts=parent.max_attempts,
        reflection=parent.reflection,
    )


@dataclass(frozen=True)
class FixtureMetaImprover:
    name: str
    added_steps: tuple[str, ...]

    def improve(
        self,
        seed_artifact: StrategyArtifact,
        *,
        trial_seed: int,
        budget: ExperimentBudget,
    ) -> ImprovementRun:
        successor = _extend(seed_artifact, *self.added_steps)
        return ImprovementRun(
            successor=successor,
            usage=ResourceUse(proposals=1, model_calls=1, tokens=32),
            detail=f"fixture meta-improvement seed {trial_seed}",
        )


class FixtureSealedUtility:
    metadata = EvaluatorMetadata(
        "fixture.strategy-evaluator.v1:sealed-external",
        "fixture",
    )

    def __init__(self, evaluator: FixtureStrategyEvaluator | None = None) -> None:
        self.evaluator = evaluator or FixtureStrategyEvaluator()

    def evaluate(
        self,
        artifact: StrategyArtifact,
        *,
        split: str,
        trial_seed: int,
    ) -> ExternalEvaluation:
        if split != SEALED_SPLIT:
            raise ValueError("fixture metaproductivity uses the sealed split")
        result = self.evaluator.evaluate(artifact, split=split, seed=trial_seed)
        return ExternalEvaluation(
            utility=result.utility,
            usage=ResourceUse(evaluations=1),
            artifact_valid=result.artifact_valid.passed,
            correct=result.correct.passed,
            safety_preserved=result.safety_preserved.passed,
            evaluator_integrity=result.evaluator_integrity.passed,
            resource_compliance=result.resource_compliance.passed,
            detail="external deterministic fixture measurement",
        )


def fixture_meta_arms() -> tuple[FixtureMetaImprover, FixtureMetaImprover]:
    ancestor = FixtureMetaImprover(
        "fixture-ancestor",
        ("Reproduce the reported failure before editing.",),
    )
    descendant = FixtureMetaImprover(
        "fixture-descendant",
        (
            "Reproduce the reported failure before editing.",
            "Run the public tests after each change.",
            "Inspect nearby code and call sites.",
        ),
    )
    return ancestor, descendant


__all__ = [
    "FixtureMetaImprover",
    "FixtureSealedUtility",
    "FixtureSequenceProposer",
    "FixtureStrategyEvaluator",
    "baseline_strategy",
    "fixture_meta_arms",
]
