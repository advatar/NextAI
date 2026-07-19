"""Matched-budget measurement of improvement productivity.

The improver injected here is a governor-owned runner: it is trusted to meter all
proposal work and to return that measured usage, but it is not allowed to attest
that its own successor is valid or safe.  Those decisive gates and their resource
use come from an independent external evaluator.

Every arm pays for two matched evaluator calls (the common seed and its
successor).  Reports retain the improver, seed-evaluation, successor-evaluation,
and total resource vectors.  A fixture evaluator may validate this plumbing, but
its metadata keeps the result explicitly classified as fixture evidence.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
from dataclasses import asdict, dataclass
from numbers import Real
from typing import Any, Literal, Protocol, Sequence


MIN_EVIDENCE_PAIRS = 5
MIN_BOOTSTRAP_SAMPLES = 1_000
EvidenceClass = Literal["fixture", "empirical"]


def _exact_nonnegative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an exact integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _finite_nonnegative_real(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return result


def _finite_real(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _stable_artifact_key(artifact: Any) -> str:
    artifact_id = getattr(artifact, "artifact_id", None)
    if isinstance(artifact_id, str) and artifact_id:
        return artifact_id
    try:
        encoded = json.dumps(
            artifact,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError, RecursionError) as error:
        raise TypeError(
            "each seed artifact must expose a stable artifact_id or be canonical JSON"
        ) from error
    identity = f"json:{type(artifact).__name__}:{encoded}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ExperimentBudget:
    max_proposals: int
    max_evaluations: int
    max_model_calls: int
    max_tokens: int
    max_wall_seconds: float

    def __post_init__(self) -> None:
        for name in (
            "max_proposals",
            "max_evaluations",
            "max_model_calls",
            "max_tokens",
        ):
            object.__setattr__(self, name, _exact_nonnegative_int(getattr(self, name), name))
        object.__setattr__(
            self,
            "max_wall_seconds",
            _finite_nonnegative_real(self.max_wall_seconds, "max_wall_seconds"),
        )


@dataclass(frozen=True, slots=True)
class ResourceUse:
    proposals: int = 0
    evaluations: int = 0
    model_calls: int = 0
    tokens: int = 0
    wall_seconds: float = 0.0

    def __post_init__(self) -> None:
        for name in ("proposals", "evaluations", "model_calls", "tokens"):
            object.__setattr__(self, name, _exact_nonnegative_int(getattr(self, name), name))
        object.__setattr__(
            self,
            "wall_seconds",
            _finite_nonnegative_real(self.wall_seconds, "wall_seconds"),
        )

    def __add__(self, other: "ResourceUse") -> "ResourceUse":
        if not isinstance(other, ResourceUse):
            return NotImplemented
        return ResourceUse(
            proposals=self.proposals + other.proposals,
            evaluations=self.evaluations + other.evaluations,
            model_calls=self.model_calls + other.model_calls,
            tokens=self.tokens + other.tokens,
            wall_seconds=self.wall_seconds + other.wall_seconds,
        )

    def within(self, budget: ExperimentBudget) -> bool:
        if not isinstance(budget, ExperimentBudget):
            raise TypeError("budget must be an ExperimentBudget")
        return (
            self.proposals <= budget.max_proposals
            and self.evaluations <= budget.max_evaluations
            and self.model_calls <= budget.max_model_calls
            and self.tokens <= budget.max_tokens
            and self.wall_seconds <= budget.max_wall_seconds
        )


@dataclass(frozen=True, slots=True)
class CostWeights:
    """Predeclared conversion from raw resources to comparison units."""

    proposal: float = 1.0
    evaluation: float = 1.0
    model_call: float = 1.0
    token: float = 0.0
    wall_second: float = 0.0

    def __post_init__(self) -> None:
        for name in ("proposal", "evaluation", "model_call", "token", "wall_second"):
            object.__setattr__(self, name, _finite_nonnegative_real(getattr(self, name), name))
        if not any(value > 0 for value in asdict(self).values()):
            raise ValueError("at least one cost weight must be positive")

    def units(self, usage: ResourceUse) -> float:
        if not isinstance(usage, ResourceUse):
            raise TypeError("usage must be ResourceUse")
        total = (
            self.proposal * usage.proposals
            + self.evaluation * usage.evaluations
            + self.model_call * usage.model_calls
            + self.token * usage.tokens
            + self.wall_second * usage.wall_seconds
        )
        if total <= 0 or not math.isfinite(total):
            raise ValueError("measured run has no positive finite cost")
        return total


@dataclass(frozen=True, slots=True)
class EvaluatorMetadata:
    evaluator_id: str
    evidence_class: EvidenceClass

    def __post_init__(self) -> None:
        if not isinstance(self.evaluator_id, str) or not self.evaluator_id.strip():
            raise ValueError("evaluator_id must be non-empty text")
        if self.evidence_class not in {"fixture", "empirical"}:
            raise ValueError("evidence_class must be 'fixture' or 'empirical'")


@dataclass(frozen=True, slots=True)
class ExternalEvaluation:
    """Governor-owned decisive measurement for one artifact.

    ``usage`` is measured by the evaluator runner, not supplied by the improver.
    One call must account for at least one evaluation.
    """

    utility: float
    usage: ResourceUse
    artifact_valid: bool
    correct: bool
    safety_preserved: bool
    evaluator_integrity: bool
    resource_compliance: bool
    detail: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "utility", _finite_real(self.utility, "utility"))
        if not isinstance(self.usage, ResourceUse):
            raise TypeError("evaluation usage must be ResourceUse")
        if self.usage.evaluations < 1:
            raise ValueError("each external evaluator call must record an evaluation")
        for name in (
            "artifact_valid",
            "correct",
            "safety_preserved",
            "evaluator_integrity",
            "resource_compliance",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be a bool")
        if not isinstance(self.detail, str):
            raise TypeError("detail must be text")

    @property
    def gates_passed(self) -> bool:
        return all(
            getattr(self, name)
            for name in (
                "artifact_valid",
                "correct",
                "safety_preserved",
                "evaluator_integrity",
                "resource_compliance",
            )
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["usage"] = asdict(self.usage)
        return value


class ExternalEvaluationError(RuntimeError):
    """Evaluator-runner failure carrying the resources consumed before failure."""

    def __init__(self, message: str, *, usage: ResourceUse) -> None:
        if not isinstance(message, str) or not message:
            raise ValueError("external evaluation error requires a message")
        if not isinstance(usage, ResourceUse) or usage.evaluations < 1:
            raise ValueError(
                "external evaluation error usage must count at least one evaluation"
            )
        self.usage = usage
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ImprovementRun:
    """Output of the trusted governor-owned improver runner.

    This object deliberately contains no validity, correctness, safety, or
    integrity claims.  The runner meters proposal work; an independent evaluator
    decides every acceptance-relevant gate.
    """

    successor: Any
    usage: ResourceUse
    detail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.usage, ResourceUse):
            raise TypeError("improver usage must be ResourceUse")
        if not isinstance(self.detail, str):
            raise TypeError("detail must be text")


class Improver(Protocol):
    name: str

    def improve(
        self, seed_artifact: Any, *, trial_seed: int, budget: ExperimentBudget
    ) -> ImprovementRun: ...


class ExternalEvaluator(Protocol):
    metadata: EvaluatorMetadata

    def evaluate(
        self, artifact: Any, *, split: str, trial_seed: int
    ) -> ExternalEvaluation: ...


@dataclass(frozen=True, slots=True)
class ArmResult:
    improver: str
    trial_seed: int
    seed_utility: float | None
    successor_utility: float | None
    uplift: float | None
    cost_units: float | None
    productivity: float | None
    improver_usage: ResourceUse
    seed_evaluation_usage: ResourceUse
    successor_evaluation_usage: ResourceUse
    total_usage: ResourceUse
    seed_evaluation: ExternalEvaluation | None
    successor_evaluation: ExternalEvaluation | None
    valid: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "improver": self.improver,
            "trial_seed": self.trial_seed,
            "seed_utility": self.seed_utility,
            "successor_utility": self.successor_utility,
            "uplift": self.uplift,
            "cost_units": self.cost_units,
            "productivity": self.productivity,
            "usage": {
                "improver": asdict(self.improver_usage),
                "seed_evaluation": asdict(self.seed_evaluation_usage),
                "successor_evaluation": asdict(self.successor_evaluation_usage),
                "total": asdict(self.total_usage),
            },
            "seed_evaluation": (
                None if self.seed_evaluation is None else self.seed_evaluation.to_dict()
            ),
            "successor_evaluation": (
                None
                if self.successor_evaluation is None
                else self.successor_evaluation.to_dict()
            ),
            "valid": self.valid,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class PairedTrial:
    trial_seed: int
    seed_artifact_id: str
    evaluation_order: tuple[str, str]
    ancestor: ArmResult
    descendant: ArmResult
    productivity_delta: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "trial_seed": self.trial_seed,
            "seed_artifact_id": self.seed_artifact_id,
            "evaluation_order": list(self.evaluation_order),
            "ancestor": self.ancestor.to_dict(),
            "descendant": self.descendant.to_dict(),
            "productivity_delta": self.productivity_delta,
        }


@dataclass(frozen=True, slots=True)
class TournamentReport:
    schema: str
    evaluator_id: str
    evidence_class: EvidenceClass
    split: str
    budget: ExperimentBudget
    cost_weights: CostWeights
    trials: tuple[PairedTrial, ...]
    valid_pairs: int
    mean_delta: float | None
    median_delta: float | None
    confidence_low: float | None
    confidence_high: float | None
    effect_threshold: float
    bootstrap_samples: int
    bootstrap_seed: int
    verdict: str

    @property
    def fixture_only(self) -> bool:
        return self.evidence_class == "fixture"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "evaluator_id": self.evaluator_id,
            "evidence_class": self.evidence_class,
            "split": self.split,
            "budget": asdict(self.budget),
            "cost_weights": asdict(self.cost_weights),
            "trials": [trial.to_dict() for trial in self.trials],
            "bootstrap": {
                "method": "paired_percentile",
                "samples": self.bootstrap_samples,
                "seed": self.bootstrap_seed,
            },
            "summary": {
                "valid_pairs": self.valid_pairs,
                "minimum_evidence_pairs": MIN_EVIDENCE_PAIRS,
                "mean_productivity_delta": self.mean_delta,
                "median_productivity_delta": self.median_delta,
                "paired_95pct_bootstrap_ci": [self.confidence_low, self.confidence_high],
                "effect_threshold": self.effect_threshold,
                "verdict": self.verdict,
                "evidence_class": self.evidence_class,
                "fixture_only": self.fixture_only,
            },
        }


def run_tournament(
    *,
    ancestor: Improver,
    descendant: Improver,
    seed_artifacts: Sequence[Any],
    trial_seeds: Sequence[int],
    evaluator: ExternalEvaluator,
    budget: ExperimentBudget,
    cost_weights: CostWeights,
    split: str = "sealed_final",
    effect_threshold: float,
    bootstrap_samples: int = 5000,
    bootstrap_seed: int = 0,
) -> TournamentReport:
    """Compare two improvers with matched seeds and counterbalanced arm order."""

    if not isinstance(budget, ExperimentBudget):
        raise TypeError("budget must be an ExperimentBudget")
    if not isinstance(cost_weights, CostWeights):
        raise TypeError("cost_weights must be CostWeights")
    if len(seed_artifacts) != len(trial_seeds):
        raise ValueError("seed_artifacts and trial_seeds must have equal length")
    if len(seed_artifacts) < MIN_EVIDENCE_PAIRS:
        raise ValueError(f"at least {MIN_EVIDENCE_PAIRS} paired trials are required")
    artifact_keys = tuple(_stable_artifact_key(artifact) for artifact in seed_artifacts)
    if len(set(artifact_keys)) != len(artifact_keys):
        raise ValueError(
            "seed artifacts must be distinct; repeated pseudo-replicates are not evidence"
        )
    normalized_seeds = tuple(
        _exact_nonnegative_int(seed, f"trial_seeds[{index}]")
        for index, seed in enumerate(trial_seeds)
    )
    if len(set(normalized_seeds)) != len(normalized_seeds):
        raise ValueError("trial seeds must be unique; duplicate pairs are not evidence")
    if budget.max_evaluations < 2:
        raise ValueError("each arm budget must allow seed and successor evaluations")
    if not isinstance(split, str) or not split.strip():
        raise ValueError("a named evaluation split is required")
    threshold = _finite_real(effect_threshold, "effect_threshold")
    if threshold <= 0:
        raise ValueError("effect_threshold must be strictly positive")
    if type(bootstrap_samples) is not int or bootstrap_samples < MIN_BOOTSTRAP_SAMPLES:
        raise ValueError(
            f"bootstrap_samples must be at least {MIN_BOOTSTRAP_SAMPLES}"
        )
    bootstrap_seed = _exact_nonnegative_int(bootstrap_seed, "bootstrap_seed")
    metadata = getattr(evaluator, "metadata", None)
    if not isinstance(metadata, EvaluatorMetadata):
        raise TypeError("evaluator.metadata must be EvaluatorMetadata")

    pairs: list[PairedTrial] = []
    deltas: list[float] = []
    for index, (seed_artifact, artifact_key, trial_seed) in enumerate(
        zip(seed_artifacts, artifact_keys, normalized_seeds)
    ):
        order = ("ancestor", "descendant") if index % 2 == 0 else (
            "descendant",
            "ancestor",
        )
        results: dict[str, ArmResult] = {}
        arms = {"ancestor": ancestor, "descendant": descendant}
        for label in order:
            results[label] = _run_arm(
                arms[label],
                seed_artifact,
                trial_seed,
                evaluator,
                budget,
                cost_weights,
                split,
            )
        ancestor_result = results["ancestor"]
        descendant_result = results["descendant"]
        delta = None
        if ancestor_result.valid and descendant_result.valid:
            assert ancestor_result.productivity is not None
            assert descendant_result.productivity is not None
            candidate_delta = descendant_result.productivity - ancestor_result.productivity
            if math.isfinite(candidate_delta):
                delta = candidate_delta
                deltas.append(delta)
        pairs.append(
            PairedTrial(
                trial_seed,
                artifact_key,
                order,
                ancestor_result,
                descendant_result,
                delta,
            )
        )

    low, high = _paired_bootstrap_interval(
        deltas, samples=bootstrap_samples, seed=bootstrap_seed
    )
    mean_delta = statistics.fmean(deltas) if deltas else None
    if len(deltas) != len(pairs):
        verdict = "invalid"
    elif len(deltas) < MIN_EVIDENCE_PAIRS or low is None or high is None:
        verdict = "inconclusive"
    elif mean_delta is not None and mean_delta > threshold and low > threshold:
        verdict = "passes_threshold"
    elif high < threshold:
        verdict = "fails_threshold"
    else:
        verdict = "inconclusive"

    return TournamentReport(
        schema="recursive-lab.metaproductivity-report.v2",
        evaluator_id=metadata.evaluator_id,
        evidence_class=metadata.evidence_class,
        split=split,
        budget=budget,
        cost_weights=cost_weights,
        trials=tuple(pairs),
        valid_pairs=len(deltas),
        mean_delta=mean_delta,
        median_delta=statistics.median(deltas) if deltas else None,
        confidence_low=low,
        confidence_high=high,
        effect_threshold=threshold,
        bootstrap_samples=bootstrap_samples,
        bootstrap_seed=bootstrap_seed,
        verdict=verdict,
    )


def _run_arm(
    improver: Improver,
    seed_artifact: Any,
    trial_seed: int,
    evaluator: ExternalEvaluator,
    budget: ExperimentBudget,
    cost_weights: CostWeights,
    split: str,
) -> ArmResult:
    zero = ResourceUse()
    improver_usage = zero
    seed_usage = zero
    successor_usage = zero
    seed_evaluation: ExternalEvaluation | None = None
    successor_evaluation: ExternalEvaluation | None = None
    reasons: list[str] = []

    try:
        run = improver.improve(seed_artifact, trial_seed=trial_seed, budget=budget)
        if not isinstance(run, ImprovementRun):
            raise TypeError("improver must return ImprovementRun")
        improver_usage = run.usage
    except Exception as error:
        reasons.append(f"improver_error:{type(error).__name__}:{error}")
        return _arm_result(
            improver,
            trial_seed,
            improver_usage,
            seed_usage,
            successor_usage,
            seed_evaluation,
            successor_evaluation,
            reasons,
            cost_weights,
        )

    if not improver_usage.within(budget):
        reasons.append("improver_budget_exceeded")
        return _arm_result(
            improver,
            trial_seed,
            improver_usage,
            seed_usage,
            successor_usage,
            seed_evaluation,
            successor_evaluation,
            reasons,
            cost_weights,
        )

    seed_evaluation, error, seed_usage = _external_evaluate(
        evaluator, seed_artifact, split=split, trial_seed=trial_seed
    )
    if error is not None:
        reasons.append(f"seed_{error}")
    else:
        assert seed_evaluation is not None
        reasons.extend(_gate_failures("seed", seed_evaluation))

    partial_usage = improver_usage + seed_usage
    if not partial_usage.within(budget):
        reasons.append("budget_exceeded_after_seed_evaluation")
    if reasons:
        return _arm_result(
            improver,
            trial_seed,
            improver_usage,
            seed_usage,
            successor_usage,
            seed_evaluation,
            successor_evaluation,
            reasons,
            cost_weights,
        )

    successor_evaluation, error, successor_usage = _external_evaluate(
        evaluator, run.successor, split=split, trial_seed=trial_seed
    )
    if error is not None:
        reasons.append(f"successor_{error}")
    else:
        assert successor_evaluation is not None
        reasons.extend(_gate_failures("successor", successor_evaluation))

    total_usage = partial_usage + successor_usage
    if not total_usage.within(budget):
        reasons.append("total_budget_exceeded")
    return _arm_result(
        improver,
        trial_seed,
        improver_usage,
        seed_usage,
        successor_usage,
        seed_evaluation,
        successor_evaluation,
        reasons,
        cost_weights,
    )


def _external_evaluate(
    evaluator: ExternalEvaluator,
    artifact: Any,
    *,
    split: str,
    trial_seed: int,
) -> tuple[ExternalEvaluation | None, str | None, ResourceUse]:
    try:
        result = evaluator.evaluate(artifact, split=split, trial_seed=trial_seed)
        if not isinstance(result, ExternalEvaluation):
            raise TypeError("external evaluator must return ExternalEvaluation")
        return result, None, result.usage
    except ExternalEvaluationError as error:
        return (
            None,
            f"evaluation_error:{type(error).__name__}:{error}",
            error.usage,
        )
    except Exception as error:
        # A call definitely occurred even if a broken adapter omitted its
        # detailed meter. Preserve that minimum charge and invalidate the arm.
        return (
            None,
            f"evaluation_error:{type(error).__name__}:{error}:usage_incomplete",
            ResourceUse(evaluations=1),
        )


def _gate_failures(prefix: str, evaluation: ExternalEvaluation) -> list[str]:
    failures = []
    for name in (
        "artifact_valid",
        "correct",
        "safety_preserved",
        "evaluator_integrity",
        "resource_compliance",
    ):
        if not getattr(evaluation, name):
            failures.append(f"{prefix}_{name}_failed")
    return failures


def _arm_result(
    improver: Improver,
    trial_seed: int,
    improver_usage: ResourceUse,
    seed_usage: ResourceUse,
    successor_usage: ResourceUse,
    seed_evaluation: ExternalEvaluation | None,
    successor_evaluation: ExternalEvaluation | None,
    reasons: Sequence[str],
    cost_weights: CostWeights,
) -> ArmResult:
    total_usage = improver_usage + seed_usage + successor_usage
    cost_units: float | None
    try:
        cost_units = cost_weights.units(total_usage)
    except (TypeError, ValueError):
        cost_units = None

    seed_utility = None if seed_evaluation is None else seed_evaluation.utility
    successor_utility = (
        None if successor_evaluation is None else successor_evaluation.utility
    )
    uplift = None
    productivity = None
    if not reasons and seed_utility is not None and successor_utility is not None:
        uplift = successor_utility - seed_utility
        if cost_units is None:
            reasons = (*reasons, "measurement_has_no_positive_cost")
        else:
            productivity = uplift / cost_units
            if not math.isfinite(productivity):
                reasons = (*reasons, "productivity_nonfinite")
                productivity = None

    return ArmResult(
        improver=getattr(improver, "name", type(improver).__name__),
        trial_seed=trial_seed,
        seed_utility=seed_utility,
        successor_utility=successor_utility,
        uplift=uplift,
        cost_units=cost_units,
        productivity=productivity,
        improver_usage=improver_usage,
        seed_evaluation_usage=seed_usage,
        successor_evaluation_usage=successor_usage,
        total_usage=total_usage,
        seed_evaluation=seed_evaluation,
        successor_evaluation=successor_evaluation,
        valid=not reasons,
        reasons=tuple(reasons),
    )


def _paired_bootstrap_interval(
    values: Sequence[float], *, samples: int, seed: int
) -> tuple[float | None, float | None]:
    if len(values) < MIN_EVIDENCE_PAIRS:
        return None, None
    rng = random.Random(seed)
    means = sorted(
        statistics.fmean(rng.choice(values) for _ in values) for _ in range(samples)
    )
    low_index = max(0, math.floor(0.025 * (samples - 1)))
    high_index = min(samples - 1, math.ceil(0.975 * (samples - 1)))
    return means[low_index], means[high_index]


__all__ = [
    "ArmResult",
    "CostWeights",
    "EvaluatorMetadata",
    "ExperimentBudget",
    "ExternalEvaluation",
    "ExternalEvaluationError",
    "ExternalEvaluator",
    "ImprovementRun",
    "Improver",
    "MIN_BOOTSTRAP_SAMPLES",
    "MIN_EVIDENCE_PAIRS",
    "PairedTrial",
    "ResourceUse",
    "TournamentReport",
    "run_tournament",
]
