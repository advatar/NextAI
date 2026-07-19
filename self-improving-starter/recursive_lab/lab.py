"""Dependency-injected orchestration for bounded strategy self-improvement.

The mutable artifact is a narrow :class:`StrategyArtifact`.  The governor,
evaluator, ledger, resource accounting, and promotion policy remain outside the
candidate boundary.  Private evaluation details are persisted for audit but are
never passed back into the proposer; only development feedback is.
"""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass
from numbers import Real
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from .artifacts import (
    ArtifactRecord,
    ArtifactValidationError,
    StrategyArtifact,
    sha256_digest,
)
from .governance import (
    AcceptancePolicy,
    BudgetAccount,
    BudgetExceeded,
    BudgetLimits,
    BudgetUsage,
    EvaluationEvidence,
    GateResult,
    PromotionDecision,
)
from .ledger import LineageLedger
from .manifest import ExperimentManifest, ManifestStore


DEVELOPMENT_SPLIT = "development"
PRIVATE_SPLIT = "private_selection"
SEALED_SPLIT = "sealed_final"
_SPLITS = frozenset({DEVELOPMENT_SPLIT, PRIVATE_SPLIT, SEALED_SPLIT})
MUTABLE_ARTIFACT_SCHEMA_ID = "recursive-lab.strategy-artifact.v1"
_RUNTIME_POLICY_ID = "typed-strategy-only:no-candidate-code:v1"


class MeteredOperationError(RuntimeError):
    """Trusted adapter failure with an explicit model-call/token receipt."""

    def __init__(
        self,
        message: str,
        *,
        model_calls: int = 0,
        tokens: int = 0,
    ) -> None:
        if not isinstance(message, str) or not message:
            raise ValueError("metered operation error requires a message")
        for name, value in (("model_calls", model_calls), ("tokens", tokens)):
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        self.model_calls = model_calls
        self.tokens = tokens
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ProposalResult:
    """Untrusted serialized candidate plus externally countable model usage."""

    candidate_json: str
    model_calls: int = 0
    tokens: int = 0
    detail: str = ""
    request_id: str | None = None
    model_version: str | None = None
    raw_response_digest: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_json, str):
            raise TypeError("candidate_json must be text")
        if len(self.candidate_json.encode("utf-8")) > 64 * 1024:
            raise ValueError("candidate_json exceeds the 64 KiB proposal limit")
        for name in ("model_calls", "tokens"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if not isinstance(self.detail, str):
            raise TypeError("detail must be text")
        for name in ("request_id", "model_version"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be non-empty text when present")
        if self.raw_response_digest is not None and (
            not isinstance(self.raw_response_digest, str)
            or len(self.raw_response_digest) != 64
            or any(character not in "0123456789abcdef" for character in self.raw_response_digest)
        ):
            raise ValueError("raw_response_digest must be a SHA-256 hex digest")


class StrategyProposer(Protocol):
    name: str
    proposer_digest: str

    def propose(
        self,
        parent: ArtifactRecord,
        *,
        public_feedback: str,
        seed: int,
    ) -> ProposalResult: ...


@dataclass(frozen=True, slots=True)
class ArtifactEvaluation:
    evaluator_id: str
    split: str
    utility: float
    correct: GateResult
    safety_preserved: GateResult
    evaluator_integrity: GateResult
    artifact_valid: GateResult
    resource_compliance: GateResult
    task_count: int
    model_calls: int = 0
    tokens: int = 0
    public_feedback: str = ""
    task_manifest_digest: str = "0" * 64
    per_task_results: tuple[bool, ...] = ()
    cpu_seconds: float = 0.0
    monetary_cost: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.evaluator_id, str) or not self.evaluator_id:
            raise ValueError("evaluator_id must be non-empty text")
        if self.split not in _SPLITS:
            raise ValueError(f"unsupported evaluation split: {self.split!r}")
        if isinstance(self.utility, bool) or not isinstance(self.utility, Real):
            raise TypeError("evaluation utility must be a real non-boolean number")
        utility = float(self.utility)
        if not math.isfinite(utility):
            raise ValueError("evaluation utility must be finite")
        object.__setattr__(self, "utility", utility)
        for name in (
            "correct",
            "safety_preserved",
            "evaluator_integrity",
            "artifact_valid",
            "resource_compliance",
        ):
            if not isinstance(getattr(self, name), GateResult):
                raise TypeError(f"{name} must be a GateResult")
        for name in ("task_count", "model_calls", "tokens"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if not isinstance(self.public_feedback, str):
            raise TypeError("public_feedback must be text")
        if self.split != DEVELOPMENT_SPLIT and self.public_feedback:
            raise ValueError("private and sealed evaluations cannot expose feedback")
        if (
            not isinstance(self.task_manifest_digest, str)
            or len(self.task_manifest_digest) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.task_manifest_digest
            )
        ):
            raise ValueError("task_manifest_digest must be a SHA-256 hex digest")
        if type(self.per_task_results) is not tuple or any(
            type(result) is not bool for result in self.per_task_results
        ):
            raise TypeError("per_task_results must be an immutable tuple of bools")
        if self.task_count == 0:
            raise ValueError("task_count must be positive")
        if len(self.per_task_results) != self.task_count:
            raise ValueError("per_task_results length must match task_count")
        if self.correct.passed and not all(self.per_task_results):
            raise ValueError(
                "correct cannot pass while one or more per-task results failed"
            )
        for name in ("cpu_seconds", "monetary_cost"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Real):
                raise TypeError(f"{name} must be a real non-boolean number")
            normalized = float(value)
            if not math.isfinite(normalized) or normalized < 0:
                raise ValueError(f"{name} must be finite and non-negative")
            object.__setattr__(self, name, normalized)

    def gate(self, name: str) -> GateResult:
        return getattr(self, name)

    def to_payload(self) -> dict[str, Any]:
        return {
            "artifact_valid": self.artifact_valid.to_dict(),
            "correct": self.correct.to_dict(),
            "evaluator_id": self.evaluator_id,
            "evaluator_integrity": self.evaluator_integrity.to_dict(),
            "model_calls": self.model_calls,
            "public_feedback": self.public_feedback,
            "resource_compliance": self.resource_compliance.to_dict(),
            "safety_preserved": self.safety_preserved.to_dict(),
            "split": self.split,
            "task_count": self.task_count,
            "task_manifest_digest": self.task_manifest_digest,
            "per_task_results": list(self.per_task_results),
            "cpu_seconds": self.cpu_seconds,
            "monetary_cost": self.monetary_cost,
            "tokens": self.tokens,
            "utility": self.utility,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ArtifactEvaluation":
        return cls(
            evaluator_id=payload["evaluator_id"],
            split=payload["split"],
            utility=payload["utility"],
            correct=GateResult.from_dict(payload["correct"]),
            safety_preserved=GateResult.from_dict(payload["safety_preserved"]),
            evaluator_integrity=GateResult.from_dict(payload["evaluator_integrity"]),
            artifact_valid=GateResult.from_dict(payload["artifact_valid"]),
            resource_compliance=GateResult.from_dict(payload["resource_compliance"]),
            task_count=payload["task_count"],
            model_calls=payload["model_calls"],
            tokens=payload["tokens"],
            public_feedback=payload["public_feedback"],
            task_manifest_digest=payload.get("task_manifest_digest", "0" * 64),
            per_task_results=tuple(payload.get("per_task_results", ())),
            cpu_seconds=payload.get("cpu_seconds", 0.0),
            monetary_cost=payload.get("monetary_cost", 0.0),
        )


class StrategyEvaluator(Protocol):
    evaluator_id: str
    evaluator_digest: str
    task_manifest_digests: Mapping[str, str]

    def evaluate(
        self,
        artifact: StrategyArtifact,
        *,
        split: str,
        seed: int,
    ) -> ArtifactEvaluation: ...


@dataclass(frozen=True, slots=True)
class LabSnapshot:
    champion: ArtifactRecord
    champion_private: ArtifactEvaluation
    public_feedback: str
    usage: BudgetUsage
    attempts: int
    ledger_head: str
    accepted_generations: int
    manifest_hash: str
    stopped_reason: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "accepted_generations": self.accepted_generations,
            "attempts": self.attempts,
            "champion": self.champion.to_payload(),
            "champion_private_utility": self.champion_private.utility,
            "ledger_head": self.ledger_head,
            "manifest_hash": self.manifest_hash,
            "public_feedback": self.public_feedback,
            "stopped_reason": self.stopped_reason,
            "usage": self.usage.to_dict(),
        }


def _all_success(evaluation: ArtifactEvaluation) -> bool:
    return all(
        evaluation.gate(name).passed
        for name in (
            "artifact_valid",
            "correct",
            "safety_preserved",
            "evaluator_integrity",
            "resource_compliance",
        )
    )


def _combine_gate(
    name: str,
    development: ArtifactEvaluation,
    private: ArtifactEvaluation,
) -> GateResult:
    failures = []
    for evaluation in (development, private):
        gate = evaluation.gate(name)
        if not gate.passed:
            failures.append(f"{evaluation.split}: {gate.reason}")
    if failures:
        return GateResult.failure("; ".join(failures))
    return GateResult.success(f"{name} passed on development and private selection")


def _usage_delta(before: BudgetUsage, after: BudgetUsage) -> BudgetUsage:
    values = {
        name: getattr(after, name) - getattr(before, name)
        for name in ("proposals", "evaluations", "model_calls", "tokens", "wall_seconds")
    }
    return BudgetUsage(**values)


class StrategyLab:
    """One governed lineage with durable attempts and resumable accepted state."""

    def __init__(
        self,
        *,
        proposer: StrategyProposer,
        evaluator: StrategyEvaluator,
        policy: AcceptancePolicy,
        limits: BudgetLimits,
        ledger_path: str | Path,
        run_seed: int = 0,
        manifest_path: str | Path | None = None,
        clock: Callable[[], float] = time.monotonic,
        head_observer: Callable[[str], None] | None = None,
        max_sealed_audits: int = 2,
    ) -> None:
        self.proposer = proposer
        self.evaluator = evaluator
        if not isinstance(policy, AcceptancePolicy):
            raise TypeError("policy must be an AcceptancePolicy")
        if not isinstance(limits, BudgetLimits):
            raise TypeError("limits must be BudgetLimits")
        self._policy = policy
        self._limits = limits
        self._clock = clock
        self._head_observer = head_observer
        if type(max_sealed_audits) is not int or max_sealed_audits < 0:
            raise ValueError("max_sealed_audits must be a non-negative integer")
        self._max_sealed_audits = max_sealed_audits
        self.ledger = LineageLedger(ledger_path)
        self._run_seed = run_seed
        self._validate_component_identity()
        self._manifest = self._make_manifest(run_seed)
        self._manifest_store = ManifestStore(
            manifest_path
            if manifest_path is not None
            else Path(f"{Path(ledger_path)}.manifest.json")
        )
        self._champion: ArtifactRecord | None = None
        self._champion_private: ArtifactEvaluation | None = None
        self._public_feedback = ""
        self._attempts = 0
        self._accepted_generations = 0
        self._accounting_compromised = False
        self._known_artifacts: set[str] = set()
        self._records: dict[str, ArtifactRecord] = {}
        self._sealed_audits: dict[str, ArtifactEvaluation] = {}
        self._sealed_queried_artifacts: set[str] = set()
        self._sealed_query_attempts = 0
        self._head = self.ledger.head_hash
        self._account = BudgetAccount(limits)
        ledger_nonempty = bool(self.ledger.verify().entry_count)
        if self._manifest_store.path.exists() or self._manifest_store.path.is_symlink():
            self._manifest_store.verify_resume(
                self._manifest,
                ledger_nonempty=ledger_nonempty,
            )
        else:
            self._manifest_store.initialize(
                self._manifest,
                ledger_nonempty=ledger_nonempty,
            )
        if ledger_nonempty:
            self._resume()
            self._publish_head(self._head)

    @property
    def initialized(self) -> bool:
        return self._champion is not None

    @property
    def policy(self) -> AcceptancePolicy:
        return self._policy

    @property
    def limits(self) -> BudgetLimits:
        return self._limits

    def initialize(self, artifact: StrategyArtifact, *, seed: int = 0) -> LabSnapshot:
        if self.initialized or self.ledger.verify().entry_count:
            raise RuntimeError("lab is already initialized")
        if type(seed) is not int or seed != self._run_seed:
            raise ValueError(
                f"seed must match the frozen experiment run_seed {self._run_seed}"
            )
        usage_before = self._account.snapshot()
        self._account.ensure_available(evaluations=2)
        record = ArtifactRecord(
            artifact=artifact,
            parent_id=None,
            generation=0,
            proposer_digest=self._proposer_digest,
            seed=seed,
        )
        development: ArtifactEvaluation | None = None
        private: ArtifactEvaluation | None = None
        try:
            development = self._evaluate(
                record, DEVELOPMENT_SPLIT, seed, attempt_index=0
            )
            private = self._evaluate(record, PRIVATE_SPLIT, seed, attempt_index=0)
        except Exception as error:
            self._append_event(
                attempt_index=0,
                outcome="rejected",
                candidate_digest=record.artifact_id,
                record=record,
                development=development,
                private=private,
                parent_private=None,
                decision=None,
                reason_codes=("seed_evaluation_failed",),
                usage_before=usage_before,
                proposal_detail_digest=sha256_digest(
                    f"{type(error).__name__}:{error}"
                ),
            )
            raise RuntimeError("seed strategy evaluation failed") from error
        assert development is not None and private is not None
        if not _all_success(development) or not _all_success(private):
            self._append_event(
                attempt_index=0,
                outcome="rejected",
                candidate_digest=record.artifact_id,
                record=record,
                development=development,
                private=private,
                parent_private=None,
                decision=None,
                reason_codes=("seed_gate_failed",),
                usage_before=usage_before,
                proposal_detail_digest=None,
            )
            raise RuntimeError("seed strategy failed an immutable evaluation gate")
        self._champion = record
        self._champion_private = private
        self._public_feedback = development.public_feedback
        self._known_artifacts.add(record.artifact_id)
        self._records[record.artifact_id] = record
        self._append_event(
            attempt_index=0,
            outcome="seed",
            candidate_digest=record.artifact_id,
            record=record,
            development=development,
            private=private,
            parent_private=None,
            decision=None,
            reason_codes=("seed",),
            usage_before=usage_before,
            proposal_detail_digest=None,
        )
        return self.snapshot()

    def run(self, rounds: int) -> LabSnapshot:
        if type(rounds) is not int or rounds < 0:
            raise ValueError("rounds must be a non-negative integer")
        if not self.initialized:
            raise RuntimeError("initialize the lab before running proposals")
        if self._accounting_compromised:
            raise RuntimeError(
                "search is closed because an operation lacked a usage receipt"
            )
        if self._sealed_query_attempts:
            raise RuntimeError("search is closed after the sealed suite has been consumed")

        stopped_reason: str | None = None
        for _ in range(rounds):
            self._assert_component_identity()
            try:
                self._account.ensure_available(proposals=1)
            except BudgetExceeded:
                stopped_reason = "proposal_budget_exhausted"
                break
            self._attempts += 1
            attempt_index = self._attempts
            usage_before = self._account.snapshot()
            assert self._champion is not None
            parent = self._champion
            self._account.charge(proposals=1)
            self._append_stage(
                attempt_index=attempt_index,
                stage="proposal_started",
                artifact_id=parent.artifact_id,
                split=None,
            )
            proposal_started = self._clock()
            try:
                proposal = self.proposer.propose(
                    parent,
                    public_feedback=self._public_feedback,
                    seed=attempt_index,
                )
                if not isinstance(proposal, ProposalResult):
                    raise TypeError("proposer must return ProposalResult")
            except Exception as error:
                elapsed = self._clock() - proposal_started
                metered = isinstance(error, MeteredOperationError)
                self._charge_or_note(
                    model_calls=error.model_calls if metered else 0,
                    tokens=error.tokens if metered else 0,
                    wall_seconds=elapsed,
                )
                if not metered:
                    self._accounting_compromised = True
                digest = sha256_digest(f"{type(error).__name__}:{error}")
                self._append_event(
                    attempt_index=attempt_index,
                    outcome="rejected",
                    candidate_digest=digest,
                    record=None,
                    development=None,
                    private=None,
                    parent_private=None,
                    decision=None,
                    reason_codes=(
                        "proposer_error" if metered else "proposer_error_unmetered",
                    ),
                    usage_before=usage_before,
                    proposal_detail_digest=None,
                )
                if not metered:
                    stopped_reason = "usage_receipt_missing"
                    break
                continue

            elapsed = self._clock() - proposal_started
            proposal_overrun = self._charge_or_note(
                model_calls=proposal.model_calls,
                tokens=proposal.tokens,
                wall_seconds=elapsed,
            )
            raw_digest = sha256_digest(proposal.candidate_json)
            proposal_detail_digest = (
                sha256_digest(proposal.detail) if proposal.detail else None
            )
            try:
                candidate = StrategyArtifact.from_json(proposal.candidate_json)
            except ArtifactValidationError:
                decision = self._policy.decide(
                    EvaluationEvidence(
                        artifact_valid=GateResult.failure("candidate schema rejected"),
                        correct=GateResult.failure("candidate was not evaluated"),
                        safety_preserved=GateResult.failure("candidate was not evaluated"),
                        evaluator_integrity=GateResult.success("governor remained external"),
                        resource_compliance=self._account.compliance_gate(),
                        utility_gain=math.nan,
                    )
                )
                self._append_event(
                    attempt_index=attempt_index,
                    outcome="rejected",
                    candidate_digest=raw_digest,
                    record=None,
                    development=None,
                    private=None,
                    parent_private=None,
                    decision=decision,
                    reason_codes=("artifact_invalid",),
                    usage_before=usage_before,
                    proposal_detail_digest=proposal_detail_digest,
                    proposal=proposal,
                )
                continue

            record = ArtifactRecord(
                artifact=candidate,
                parent_id=parent.artifact_id,
                generation=parent.generation + 1,
                proposer_digest=self._proposer_digest,
                seed=attempt_index,
            )
            if record.artifact_id in self._known_artifacts:
                self._append_event(
                    attempt_index=attempt_index,
                    outcome="rejected",
                    candidate_digest=record.artifact_id,
                    record=record,
                    development=None,
                    private=None,
                    parent_private=None,
                    decision=None,
                    reason_codes=("duplicate",),
                    usage_before=usage_before,
                    proposal_detail_digest=proposal_detail_digest,
                    proposal=proposal,
                )
                continue
            self._known_artifacts.add(record.artifact_id)
            self._records[record.artifact_id] = record

            if proposal_overrun or not self._account.can_charge(evaluations=3):
                self._append_event(
                    attempt_index=attempt_index,
                    outcome="rejected",
                    candidate_digest=record.artifact_id,
                    record=record,
                    development=None,
                    private=None,
                    parent_private=None,
                    decision=None,
                    reason_codes=("resource_budget_unavailable",),
                    usage_before=usage_before,
                    proposal_detail_digest=proposal_detail_digest,
                    proposal=proposal,
                )
                continue

            development: ArtifactEvaluation | None = None
            private: ArtifactEvaluation | None = None
            parent_private: ArtifactEvaluation | None = None
            try:
                development = self._evaluate(
                    record,
                    DEVELOPMENT_SPLIT,
                    attempt_index,
                    attempt_index=attempt_index,
                )
            except Exception:
                unmetered = self._accounting_compromised
                self._append_event(
                    attempt_index=attempt_index,
                    outcome="rejected",
                    candidate_digest=record.artifact_id,
                    record=record,
                    development=development,
                    private=None,
                    parent_private=None,
                    decision=None,
                    reason_codes=(
                        "evaluation_failed_unmetered"
                        if unmetered
                        else "evaluation_failed",
                    ),
                    usage_before=usage_before,
                    proposal_detail_digest=proposal_detail_digest,
                    proposal=proposal,
                )
                if unmetered:
                    stopped_reason = "usage_receipt_missing"
                    break
                continue

            if not _all_success(development):
                decision = self._policy.decide(
                    EvaluationEvidence(
                        artifact_valid=development.artifact_valid,
                        correct=development.correct,
                        safety_preserved=development.safety_preserved,
                        evaluator_integrity=development.evaluator_integrity,
                        resource_compliance=(
                            self._account.compliance_gate()
                            if development.resource_compliance.passed
                            else development.resource_compliance
                        ),
                        utility_gain=math.nan,
                    )
                )
                self._append_event(
                    attempt_index=attempt_index,
                    outcome="rejected",
                    candidate_digest=record.artifact_id,
                    record=record,
                    development=development,
                    private=None,
                    parent_private=None,
                    decision=decision,
                    reason_codes=("development_gate_failed",),
                    usage_before=usage_before,
                    proposal_detail_digest=proposal_detail_digest,
                    proposal=proposal,
                )
                continue

            try:
                # Counterbalance execution order while keeping both arms on the
                # identical task manifest and trial seed.
                if attempt_index % 2:
                    private = self._evaluate(
                        record,
                        PRIVATE_SPLIT,
                        attempt_index,
                        attempt_index=attempt_index,
                    )
                    parent_private = self._evaluate(
                        parent,
                        PRIVATE_SPLIT,
                        attempt_index,
                        attempt_index=attempt_index,
                    )
                else:
                    parent_private = self._evaluate(
                        parent,
                        PRIVATE_SPLIT,
                        attempt_index,
                        attempt_index=attempt_index,
                    )
                    private = self._evaluate(
                        record,
                        PRIVATE_SPLIT,
                        attempt_index,
                        attempt_index=attempt_index,
                    )
            except Exception:
                unmetered = self._accounting_compromised
                self._append_event(
                    attempt_index=attempt_index,
                    outcome="rejected",
                    candidate_digest=record.artifact_id,
                    record=record,
                    development=development,
                    private=private,
                    parent_private=parent_private,
                    decision=None,
                    reason_codes=(
                        "private_evaluation_failed_unmetered"
                        if unmetered
                        else "private_evaluation_failed",
                    ),
                    usage_before=usage_before,
                    proposal_detail_digest=proposal_detail_digest,
                    proposal=proposal,
                )
                if unmetered:
                    stopped_reason = "usage_receipt_missing"
                    break
                continue

            assert private is not None and parent_private is not None

            parent_control = (
                GateResult.success("paired parent control passed on private selection")
                if _all_success(parent_private)
                else GateResult.failure(
                    "paired parent control failed one or more immutable gates"
                )
            )
            candidate_integrity = _combine_gate(
                "evaluator_integrity", development, private
            )
            evaluator_integrity = (
                candidate_integrity
                if candidate_integrity.passed and parent_control.passed
                else GateResult.failure(
                    "; ".join(
                        gate.reason
                        for gate in (candidate_integrity, parent_control)
                        if not gate.passed
                    )
                )
            )
            evidence = EvaluationEvidence(
                artifact_valid=_combine_gate("artifact_valid", development, private),
                correct=_combine_gate("correct", development, private),
                safety_preserved=_combine_gate("safety_preserved", development, private),
                evaluator_integrity=evaluator_integrity,
                resource_compliance=(
                    self._account.compliance_gate()
                    if development.resource_compliance.passed
                    and private.resource_compliance.passed
                    and parent_private.resource_compliance.passed
                    else GateResult.failure("evaluation or run resource gate failed")
                ),
                utility_gain=(
                    private.utility - parent_private.utility
                    if _all_success(parent_private)
                    else math.nan
                ),
            )
            decision = self._policy.decide(evidence)
            outcome = "accepted" if decision.promoted else "rejected"
            reason_codes = ("promoted",) if decision.promoted else ("policy_rejected",)
            self._append_event(
                attempt_index=attempt_index,
                outcome=outcome,
                candidate_digest=record.artifact_id,
                record=record,
                development=development,
                private=private,
                parent_private=parent_private,
                decision=decision,
                reason_codes=reason_codes,
                usage_before=usage_before,
                proposal_detail_digest=proposal_detail_digest,
                proposal=proposal,
            )
            if decision.promoted:
                self._champion = record
                self._champion_private = private
                self._public_feedback = development.public_feedback
                self._accepted_generations += 1

        return self.snapshot(stopped_reason=stopped_reason)

    def evaluate_sealed(
        self,
        artifact: StrategyArtifact,
        *,
        seed: int,
        authorize_milestone: bool = False,
    ) -> ArtifactEvaluation:
        """Run a sealed/OOD audit without feeding its result back into search."""

        self._assert_component_identity()
        if not isinstance(artifact, StrategyArtifact):
            raise TypeError("sealed artifact must be a StrategyArtifact")
        if type(seed) is not int or not 0 <= seed <= (1 << 63) - 1:
            raise ValueError("sealed seed must be a non-negative 63-bit integer")
        if type(authorize_milestone) is not bool or not authorize_milestone:
            raise PermissionError("sealed evaluation requires explicit milestone authorization")
        if artifact.artifact_id in self._sealed_queried_artifacts:
            raise RuntimeError("this artifact has already consumed its sealed evaluation")
        if self._accounting_compromised:
            raise RuntimeError(
                "sealed evaluation is closed because an operation lacked a usage receipt"
            )
        if self._sealed_query_attempts >= self._max_sealed_audits:
            raise RuntimeError("sealed evaluation query limit is exhausted")
        self._account.ensure_available(evaluations=1)
        usage_before = self._account.snapshot()
        record = self._records.get(artifact.artifact_id)
        if record is None:
            record = ArtifactRecord(
                artifact=artifact,
                parent_id=None,
                generation=0,
                proposer_digest=self._proposer_digest,
                seed=seed,
            )
            self._records[record.artifact_id] = record
            self._known_artifacts.add(record.artifact_id)
        evaluation: ArtifactEvaluation | None = None
        failure: Exception | None = None
        try:
            evaluation = self._evaluate(
                record,
                SEALED_SPLIT,
                seed,
                attempt_index=self._attempts,
            )
        except Exception as error:
            failure = error
        payload = {
            "artifact_record": record.to_payload(),
            "cumulative_usage": self._account.snapshot().to_dict(),
            "evaluation": None if evaluation is None else evaluation.to_payload(),
            "evaluator_id": self._evaluator_id,
            "failure": (
                None
                if failure is None
                else {
                    "accounting_complete": not self._accounting_compromised,
                    "detail_digest": sha256_digest(
                        f"{type(failure).__name__}:{failure}"
                    ),
                    "error_type": type(failure).__name__,
                }
            ),
            "kind": "recursive_lab_audit",
            "manifest_hash": self._manifest.manifest_hash,
            "outcome": "passed" if failure is None else "failed",
            "resource_usage": _usage_delta(
                usage_before, self._account.snapshot()
            ).to_dict(),
            "schema_version": 1,
            "seed": seed,
        }
        entry = self.ledger.append(payload, expected_head=self._head)
        self._publish_head(entry.current_hash)
        if failure is not None:
            raise RuntimeError("sealed evaluation failed and its query was consumed") from failure
        assert evaluation is not None
        self._sealed_audits[record.artifact_id] = evaluation
        return evaluation

    def sealed_result(self, artifact_id: str) -> ArtifactEvaluation | None:
        """Return governor-owned prior audit evidence without issuing a new query."""

        return self._sealed_audits.get(artifact_id)

    def snapshot(self, *, stopped_reason: str | None = None) -> LabSnapshot:
        if self._champion is None or self._champion_private is None:
            raise RuntimeError("lab is not initialized")
        return LabSnapshot(
            champion=self._champion,
            champion_private=self._champion_private,
            public_feedback=self._public_feedback,
            usage=self._account.snapshot(),
            attempts=self._attempts,
            ledger_head=self._head,
            accepted_generations=self._accepted_generations,
            manifest_hash=self._manifest.manifest_hash,
            stopped_reason=stopped_reason,
        )

    def _validate_component_identity(self) -> None:
        if type(self._run_seed) is not int or self._run_seed < 0:
            raise ValueError("run_seed must be a non-negative integer")
        for owner, name in (
            (self.proposer, "proposer_digest"),
            (self.evaluator, "evaluator_digest"),
        ):
            value = getattr(owner, name, None)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
        manifests = getattr(self.evaluator, "task_manifest_digests", None)
        if not isinstance(manifests, Mapping) or set(manifests) != _SPLITS:
            raise ValueError("evaluator must freeze one task manifest digest per split")
        for split, digest in manifests.items():
            if (
                not isinstance(digest, str)
                or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
            ):
                raise ValueError(f"invalid task manifest digest for {split}")
        self._proposer_name = getattr(self.proposer, "name", None)
        self._proposer_digest = self.proposer.proposer_digest
        self._evaluator_id = getattr(self.evaluator, "evaluator_id", None)
        self._evaluator_digest = self.evaluator.evaluator_digest
        self._task_manifest_digests = dict(manifests)

    def _assert_component_identity(self) -> None:
        if (
            getattr(self.proposer, "name", None) != self._proposer_name
            or getattr(self.proposer, "proposer_digest", None)
            != self._proposer_digest
            or getattr(self.evaluator, "evaluator_id", None) != self._evaluator_id
            or getattr(self.evaluator, "evaluator_digest", None)
            != self._evaluator_digest
            or dict(getattr(self.evaluator, "task_manifest_digests", {}))
            != self._task_manifest_digests
            or self._policy.to_dict() != self._manifest.acceptance_policy
            or self._limits != self._manifest.budget_limits
            or self._run_seed != self._manifest.run_seed
            or sha256_digest(
                f"{_RUNTIME_POLICY_ID}:max-sealed-audits={self._max_sealed_audits}"
            )
            != self._manifest.candidate_runtime_policy_digest
        ):
            raise RuntimeError("a frozen experiment component or policy drifted")

    def _make_manifest(self, run_seed: int) -> ExperimentManifest:
        runtime_digest = sha256_digest(
            f"{_RUNTIME_POLICY_ID}:max-sealed-audits={self._max_sealed_audits}"
        )
        task_manifests = self._task_manifest_digests
        return ExperimentManifest(
            run_seed=run_seed,
            proposer_name=self._proposer_name,
            proposer_digest=self._proposer_digest,
            evaluator_id=self._evaluator_id,
            evaluator_digest=self._evaluator_digest,
            acceptance_policy=self._policy.to_dict(),
            budget_limits=self._limits,
            development_task_manifest_digest=task_manifests[DEVELOPMENT_SPLIT],
            private_task_manifest_digest=task_manifests[PRIVATE_SPLIT],
            sealed_task_manifest_digest=task_manifests[SEALED_SPLIT],
            mutable_artifact_schema_id=MUTABLE_ARTIFACT_SCHEMA_ID,
            candidate_runtime_policy_digest=runtime_digest,
        )

    def _evaluate(
        self,
        record: ArtifactRecord,
        split: str,
        seed: int,
        *,
        attempt_index: int,
    ) -> ArtifactEvaluation:
        self._assert_component_identity()
        self._account.charge(evaluations=1)
        self._append_stage(
            attempt_index=attempt_index,
            stage="evaluation_started",
            artifact_id=record.artifact_id,
            split=split,
        )
        started = self._clock()
        evaluation: ArtifactEvaluation | None = None
        failure_model_calls = 0
        failure_tokens = 0
        try:
            evaluation = self.evaluator.evaluate(record.artifact, split=split, seed=seed)
        except MeteredOperationError as error:
            failure_model_calls = error.model_calls
            failure_tokens = error.tokens
            raise
        except Exception:
            self._accounting_compromised = True
            raise
        finally:
            elapsed = self._clock() - started
            self._account.charge(
                model_calls=(
                    evaluation.model_calls
                    if isinstance(evaluation, ArtifactEvaluation)
                    else failure_model_calls
                ),
                tokens=(
                    evaluation.tokens
                    if isinstance(evaluation, ArtifactEvaluation)
                    else failure_tokens
                ),
                wall_seconds=elapsed,
            )
        if not isinstance(evaluation, ArtifactEvaluation):
            self._accounting_compromised = True
            raise TypeError("evaluator must return ArtifactEvaluation")
        if evaluation.evaluator_id != self._evaluator_id:
            raise ValueError("evaluator identity drifted")
        if evaluation.split != split:
            raise ValueError("evaluator returned the wrong split")
        if (
            evaluation.task_manifest_digest
            != self._task_manifest_digests[split]
        ):
            raise ValueError("evaluator task manifest drifted")
        return evaluation

    def _charge_or_note(self, **values: Any) -> bool:
        try:
            self._account.charge(**values)
        except BudgetExceeded:
            return True
        return False

    def _append_event(
        self,
        *,
        attempt_index: int,
        outcome: str,
        candidate_digest: str,
        record: ArtifactRecord | None,
        development: ArtifactEvaluation | None,
        private: ArtifactEvaluation | None,
        parent_private: ArtifactEvaluation | None,
        decision: PromotionDecision | None,
        reason_codes: tuple[str, ...],
        usage_before: BudgetUsage,
        proposal_detail_digest: str | None,
        proposal: ProposalResult | None = None,
    ) -> None:
        payload = {
            "artifact_record": None if record is None else record.to_payload(),
            "attempt_index": attempt_index,
            "candidate_digest": candidate_digest,
            "cumulative_usage": self._account.snapshot().to_dict(),
            "decision": None if decision is None else decision.to_dict(),
            "development_evaluation": (
                None if development is None else development.to_payload()
            ),
            "kind": "recursive_lab_attempt",
            "manifest_hash": self._manifest.manifest_hash,
            "outcome": outcome,
            "private_evaluation": None if private is None else private.to_payload(),
            "parent_private_evaluation": (
                None if parent_private is None else parent_private.to_payload()
            ),
            "proposer": {
                "detail_digest": proposal_detail_digest,
                "digest": self._proposer_digest,
                "name": self._proposer_name,
                "request_id": None if proposal is None else proposal.request_id,
                "model_version": None if proposal is None else proposal.model_version,
                "raw_response_digest": (
                    None if proposal is None else proposal.raw_response_digest
                ),
                "candidate_json_digest": (
                    None
                    if proposal is None
                    else sha256_digest(proposal.candidate_json)
                ),
            },
            "reason_codes": list(reason_codes),
            "resource_usage": _usage_delta(
                usage_before, self._account.snapshot()
            ).to_dict(),
            "schema_version": 1,
        }
        entry = self.ledger.append(payload, expected_head=self._head)
        self._publish_head(entry.current_hash)

    def _append_stage(
        self,
        *,
        attempt_index: int,
        stage: str,
        artifact_id: str,
        split: str | None,
    ) -> None:
        payload = {
            "artifact_id": artifact_id,
            "attempt_index": attempt_index,
            "cumulative_usage": self._account.snapshot().to_dict(),
            "evaluator_id": self._evaluator_id,
            "kind": "recursive_lab_stage",
            "manifest_hash": self._manifest.manifest_hash,
            "proposer_digest": self._proposer_digest,
            "schema_version": 1,
            "split": split,
            "stage": stage,
        }
        entry = self.ledger.append(payload, expected_head=self._head)
        if split == SEALED_SPLIT:
            self._sealed_query_attempts += 1
            self._sealed_queried_artifacts.add(artifact_id)
        self._publish_head(entry.current_hash)

    def _publish_head(self, head: str) -> None:
        self._head = head
        if self._head_observer is not None:
            self._head_observer(head)

    def _resume(self) -> None:
        entries = self.ledger.load()
        usage = BudgetUsage()
        for entry in entries:
            payload = entry.payload
            if payload.get("manifest_hash") != self._manifest.manifest_hash:
                raise RuntimeError("ledger event is not bound to the experiment manifest")
            if payload.get("kind") == "recursive_lab_stage":
                usage = BudgetUsage.from_dict(payload["cumulative_usage"])
                attempt_index = payload["attempt_index"]
                if type(attempt_index) is not int or attempt_index < 0:
                    raise RuntimeError("ledger contains an invalid stage attempt index")
                self._attempts = max(self._attempts, attempt_index)
                if payload.get("split") == SEALED_SPLIT:
                    artifact_id = payload.get("artifact_id")
                    if not isinstance(artifact_id, str):
                        raise RuntimeError("sealed stage lacks an artifact id")
                    self._sealed_query_attempts += 1
                    self._sealed_queried_artifacts.add(artifact_id)
                continue
            if payload.get("kind") == "recursive_lab_audit":
                usage = BudgetUsage.from_dict(payload["cumulative_usage"])
                record = ArtifactRecord.from_payload(payload["artifact_record"])
                self._known_artifacts.add(record.artifact_id)
                self._records.setdefault(record.artifact_id, record)
                evaluation_payload = payload.get("evaluation")
                failure_payload = payload.get("failure")
                if (
                    isinstance(failure_payload, dict)
                    and failure_payload.get("accounting_complete") is False
                ):
                    self._accounting_compromised = True
                if evaluation_payload is not None:
                    evaluation = ArtifactEvaluation.from_payload(evaluation_payload)
                    if record.artifact_id in self._sealed_audits:
                        raise RuntimeError("ledger contains a repeated sealed audit")
                    self._sealed_audits[record.artifact_id] = evaluation
                continue
            if payload.get("kind") != "recursive_lab_attempt":
                raise RuntimeError("ledger contains an event for another protocol")
            usage = BudgetUsage.from_dict(payload["cumulative_usage"])
            attempt_index = payload["attempt_index"]
            if type(attempt_index) is not int or attempt_index < 0:
                raise RuntimeError("ledger contains an invalid attempt index")
            self._attempts = max(self._attempts, attempt_index)
            if any(
                isinstance(reason, str) and reason.endswith("_unmetered")
                for reason in payload.get("reason_codes", ())
            ):
                self._accounting_compromised = True
            record_payload = payload["artifact_record"]
            record = None
            if record_payload is not None:
                record = ArtifactRecord.from_payload(record_payload)
                self._known_artifacts.add(record.artifact_id)
                # One content hash can appear in several rejected proposal
                # occurrences (notably a duplicate). Preserve the first
                # canonical provenance instead of overwriting it with a later
                # self-parenting duplicate occurrence.
                self._records.setdefault(record.artifact_id, record)
            if payload["outcome"] in {"seed", "accepted"}:
                if record is None or payload["private_evaluation"] is None:
                    raise RuntimeError("accepted ledger event lacks evaluation state")
                self._champion = record
                self._champion_private = ArtifactEvaluation.from_payload(
                    payload["private_evaluation"]
                )
                development_payload = payload["development_evaluation"]
                if development_payload is None:
                    raise RuntimeError("accepted ledger event lacks public state")
                development = ArtifactEvaluation.from_payload(development_payload)
                self._public_feedback = development.public_feedback
                if payload["outcome"] == "accepted":
                    self._accepted_generations += 1
        if self._champion is None:
            raise RuntimeError("ledger has no accepted seed")
        if self._sealed_query_attempts > self._max_sealed_audits:
            raise RuntimeError("ledger exceeds the frozen sealed-query limit")
        self._account = BudgetAccount(self._limits, usage)
        self._head = entries[-1].current_hash


__all__ = [
    "ArtifactEvaluation",
    "DEVELOPMENT_SPLIT",
    "LabSnapshot",
    "MeteredOperationError",
    "PRIVATE_SPLIT",
    "ProposalResult",
    "SEALED_SPLIT",
    "StrategyEvaluator",
    "StrategyLab",
    "StrategyProposer",
]
