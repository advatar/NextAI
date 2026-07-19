"""Immutable resource budgets and fail-closed promotion governance.

This module is deliberately self-contained and uses only the Python standard
library.  It belongs to the immutable governor: candidate artifacts may supply
evidence to it, but they must not be able to replace the policy or its counters.

Budget accounting has one important semantic: :meth:`BudgetAccount.charge`
records a charge *before* reporting an overrun.  This means an operation that
has already consumed resources cannot disappear from the ledger merely because
it crossed a limit.  Call :meth:`BudgetAccount.ensure_available` before starting
work when a pre-flight reservation check is possible.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real
from threading import RLock
from typing import ClassVar, Mapping


_BUDGET_FIELDS = (
    "proposals",
    "evaluations",
    "model_calls",
    "tokens",
    "wall_seconds",
)
_COUNT_FIELDS = _BUDGET_FIELDS[:-1]


def _require_nonnegative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer, not {type(value).__name__}")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _require_nonnegative_finite_real(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number, not {type(value).__name__}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if result < 0.0:
        raise ValueError(f"{name} must be non-negative")
    return result


def _require_real(value: object, name: str) -> float:
    """Return a float while intentionally allowing NaN and infinities.

    Evaluation evidence may contain a non-finite measurement.  Constructing
    that evidence is allowed so the acceptance policy can turn it into an
    explicit rejection rather than crashing or silently dropping the record.
    """

    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number, not {type(value).__name__}")
    return float(value)


def _require_exact_keys(payload: Mapping[str, object], expected: set[str], name: str) -> None:
    actual = set(payload)
    missing = expected - actual
    extra = actual - expected
    if missing or extra:
        parts: list[str] = []
        if missing:
            parts.append(f"missing {sorted(missing)!r}")
        if extra:
            parts.append(f"unexpected {sorted(extra)!r}")
        raise ValueError(f"invalid {name}: " + ", ".join(parts))


def _wire_float(value: float) -> float | str:
    """Encode non-finite floats without relying on non-standard JSON tokens."""

    if math.isnan(value):
        return "NaN"
    if value == math.inf:
        return "Infinity"
    if value == -math.inf:
        return "-Infinity"
    return value


def _unwire_float(value: object, name: str) -> float:
    if value == "NaN":
        return math.nan
    if value == "Infinity":
        return math.inf
    if value == "-Infinity":
        return -math.inf
    return _require_real(value, name)


@dataclass(frozen=True, slots=True)
class BudgetLimits:
    """Hard upper bounds for one bounded improvement run."""

    proposals: int
    evaluations: int
    model_calls: int
    tokens: int
    wall_seconds: float

    def __post_init__(self) -> None:
        for name in _COUNT_FIELDS:
            object.__setattr__(self, name, _require_nonnegative_int(getattr(self, name), name))
        object.__setattr__(
            self,
            "wall_seconds",
            _require_nonnegative_finite_real(self.wall_seconds, "wall_seconds"),
        )

    def to_dict(self) -> dict[str, int | float]:
        return {name: getattr(self, name) for name in _BUDGET_FIELDS}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> BudgetLimits:
        _require_exact_keys(payload, set(_BUDGET_FIELDS), "BudgetLimits")
        return cls(**{name: payload[name] for name in _BUDGET_FIELDS})  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class BudgetUsage:
    """An immutable snapshot of resources already consumed."""

    proposals: int = 0
    evaluations: int = 0
    model_calls: int = 0
    tokens: int = 0
    wall_seconds: float = 0.0

    def __post_init__(self) -> None:
        for name in _COUNT_FIELDS:
            object.__setattr__(self, name, _require_nonnegative_int(getattr(self, name), name))
        object.__setattr__(
            self,
            "wall_seconds",
            _require_nonnegative_finite_real(self.wall_seconds, "wall_seconds"),
        )

    def __add__(self, other: BudgetUsage) -> BudgetUsage:
        if not isinstance(other, BudgetUsage):
            return NotImplemented
        return BudgetUsage(
            proposals=self.proposals + other.proposals,
            evaluations=self.evaluations + other.evaluations,
            model_calls=self.model_calls + other.model_calls,
            tokens=self.tokens + other.tokens,
            wall_seconds=self.wall_seconds + other.wall_seconds,
        )

    def to_dict(self) -> dict[str, int | float]:
        return {name: getattr(self, name) for name in _BUDGET_FIELDS}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> BudgetUsage:
        _require_exact_keys(payload, set(_BUDGET_FIELDS), "BudgetUsage")
        return cls(**{name: payload[name] for name in _BUDGET_FIELDS})  # type: ignore[arg-type]


class BudgetExceeded(RuntimeError):
    """Raised whenever projected or recorded usage exceeds a hard limit."""

    def __init__(
        self,
        *,
        usage: BudgetUsage,
        limits: BudgetLimits,
        dimensions: tuple[str, ...],
        committed: bool,
    ) -> None:
        self.usage = usage
        self.limits = limits
        self.dimensions = dimensions
        self.committed = committed
        detail = ", ".join(
            f"{name} (used {getattr(usage, name)!r}, limit {getattr(limits, name)!r})"
            for name in dimensions
        )
        state = "recorded" if committed else "projected"
        super().__init__(f"budget exceeded by {state} usage: {detail}")

    def to_dict(self) -> dict[str, object]:
        return {
            "error": type(self).__name__,
            "message": str(self),
            "dimensions": list(self.dimensions),
            "committed": self.committed,
            "usage": self.usage.to_dict(),
            "limits": self.limits.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class GateResult:
    """The independent result of one non-compensating acceptance gate."""

    passed: bool
    reason: str = ""

    def __post_init__(self) -> None:
        if type(self.passed) is not bool:
            raise TypeError("passed must be a bool")
        if not isinstance(self.reason, str):
            raise TypeError("reason must be a string")
        normalized = self.reason.strip()
        if not self.passed and not normalized:
            raise ValueError("a failed gate must include an explicit reason")
        object.__setattr__(self, "reason", normalized)

    @classmethod
    def success(cls, reason: str = "") -> GateResult:
        return cls(True, reason)

    @classmethod
    def failure(cls, reason: str) -> GateResult:
        return cls(False, reason)

    def to_dict(self) -> dict[str, bool | str]:
        return {"passed": self.passed, "reason": self.reason}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> GateResult:
        _require_exact_keys(payload, {"passed", "reason"}, "GateResult")
        return cls(passed=payload["passed"], reason=payload["reason"])  # type: ignore[arg-type]


def _exceeded_dimensions(usage: BudgetUsage, limits: BudgetLimits) -> tuple[str, ...]:
    return tuple(
        name for name in _BUDGET_FIELDS if getattr(usage, name) > getattr(limits, name)
    )


class BudgetAccount:
    """Thread-safe mutable counter exposing only immutable usage snapshots.

    A charge that crosses a limit is retained in ``usage`` and then raises
    :class:`BudgetExceeded`.  Once breached, every subsequent charge also
    raises, even a zero charge, so callers cannot accidentally resume a run.
    """

    __slots__ = ("_limits", "_lock", "_usage")

    def __init__(
        self,
        limits: BudgetLimits,
        initial_usage: BudgetUsage | None = None,
    ) -> None:
        if not isinstance(limits, BudgetLimits):
            raise TypeError("limits must be a BudgetLimits instance")
        if initial_usage is not None and not isinstance(initial_usage, BudgetUsage):
            raise TypeError("initial_usage must be a BudgetUsage instance")
        self._limits = limits
        self._usage = initial_usage or BudgetUsage()
        self._lock = RLock()

    @property
    def limits(self) -> BudgetLimits:
        return self._limits

    @property
    def usage(self) -> BudgetUsage:
        return self.snapshot()

    def snapshot(self) -> BudgetUsage:
        with self._lock:
            return self._usage

    @property
    def exceeded_dimensions(self) -> tuple[str, ...]:
        with self._lock:
            return _exceeded_dimensions(self._usage, self._limits)

    @property
    def compliant(self) -> bool:
        return not self.exceeded_dimensions

    @property
    def breached(self) -> bool:
        return not self.compliant

    @property
    def exhausted(self) -> bool:
        """Whether any dimension has no capacity left (including a breach)."""

        with self._lock:
            return any(
                getattr(self._usage, name) >= getattr(self._limits, name)
                for name in _BUDGET_FIELDS
            )

    def remaining(self) -> BudgetUsage:
        """Return non-negative headroom in every budget dimension."""

        with self._lock:
            values = {
                name: max(0, getattr(self._limits, name) - getattr(self._usage, name))
                for name in _BUDGET_FIELDS
            }
        return BudgetUsage(**values)  # type: ignore[arg-type]

    @staticmethod
    def _make_delta(
        delta: BudgetUsage | None,
        *,
        proposals: int,
        evaluations: int,
        model_calls: int,
        tokens: int,
        wall_seconds: float,
    ) -> BudgetUsage:
        keyword_delta = BudgetUsage(
            proposals=proposals,
            evaluations=evaluations,
            model_calls=model_calls,
            tokens=tokens,
            wall_seconds=wall_seconds,
        )
        if delta is None:
            return keyword_delta
        if not isinstance(delta, BudgetUsage):
            raise TypeError("delta must be a BudgetUsage instance")
        if keyword_delta != BudgetUsage():
            raise ValueError("provide either delta or keyword charges, not both")
        return delta

    def ensure_available(
        self,
        delta: BudgetUsage | None = None,
        *,
        proposals: int = 0,
        evaluations: int = 0,
        model_calls: int = 0,
        tokens: int = 0,
        wall_seconds: float = 0.0,
    ) -> BudgetUsage:
        """Check a projected charge without changing the account."""

        charge = self._make_delta(
            delta,
            proposals=proposals,
            evaluations=evaluations,
            model_calls=model_calls,
            tokens=tokens,
            wall_seconds=wall_seconds,
        )
        with self._lock:
            projected = self._usage + charge
            exceeded = _exceeded_dimensions(projected, self._limits)
            if exceeded:
                raise BudgetExceeded(
                    usage=projected,
                    limits=self._limits,
                    dimensions=exceeded,
                    committed=False,
                )
            return projected

    def can_charge(
        self,
        delta: BudgetUsage | None = None,
        *,
        proposals: int = 0,
        evaluations: int = 0,
        model_calls: int = 0,
        tokens: int = 0,
        wall_seconds: float = 0.0,
    ) -> bool:
        """Return whether a valid charge fits; malformed charges still raise."""

        try:
            self.ensure_available(
                delta,
                proposals=proposals,
                evaluations=evaluations,
                model_calls=model_calls,
                tokens=tokens,
                wall_seconds=wall_seconds,
            )
        except BudgetExceeded:
            return False
        return True

    def charge(
        self,
        delta: BudgetUsage | None = None,
        *,
        proposals: int = 0,
        evaluations: int = 0,
        model_calls: int = 0,
        tokens: int = 0,
        wall_seconds: float = 0.0,
    ) -> BudgetUsage:
        """Record usage atomically and raise after retaining any overrun."""

        charge = self._make_delta(
            delta,
            proposals=proposals,
            evaluations=evaluations,
            model_calls=model_calls,
            tokens=tokens,
            wall_seconds=wall_seconds,
        )
        with self._lock:
            self._usage = self._usage + charge
            exceeded = _exceeded_dimensions(self._usage, self._limits)
            if exceeded:
                raise BudgetExceeded(
                    usage=self._usage,
                    limits=self._limits,
                    dimensions=exceeded,
                    committed=True,
                )
            return self._usage

    def record_proposal(self, *, wall_seconds: float = 0.0) -> BudgetUsage:
        return self.charge(proposals=1, wall_seconds=wall_seconds)

    def record_evaluation(self, *, wall_seconds: float = 0.0) -> BudgetUsage:
        return self.charge(evaluations=1, wall_seconds=wall_seconds)

    def record_model_call(
        self,
        *,
        tokens: int = 0,
        wall_seconds: float = 0.0,
    ) -> BudgetUsage:
        return self.charge(model_calls=1, tokens=tokens, wall_seconds=wall_seconds)

    def compliance_gate(self) -> GateResult:
        exceeded = self.exceeded_dimensions
        if not exceeded:
            return GateResult.success("usage is within configured limits")
        usage = self.snapshot()
        detail = ", ".join(
            f"{name}={getattr(usage, name)!r}>{getattr(self._limits, name)!r}"
            for name in exceeded
        )
        return GateResult.failure(f"budget overrun: {detail}")

    def to_dict(self) -> dict[str, object]:
        return {
            "limits": self._limits.to_dict(),
            "usage": self.snapshot().to_dict(),
            "compliant": self.compliant,
            "exceeded_dimensions": list(self.exceeded_dimensions),
        }


@dataclass(frozen=True, slots=True)
class EvaluationEvidence:
    """Externally produced evidence supplied to the immutable policy.

    The five gates stay distinct so a high utility score can never compensate
    for invalidity, incorrectness, a safety regression, evaluator tampering, or
    a resource overrun.
    """

    artifact_valid: GateResult
    correct: GateResult
    safety_preserved: GateResult
    evaluator_integrity: GateResult
    resource_compliance: GateResult
    utility_gain: float

    GATE_NAMES: ClassVar[tuple[str, ...]] = (
        "artifact_valid",
        "correct",
        "safety_preserved",
        "evaluator_integrity",
        "resource_compliance",
    )

    def __post_init__(self) -> None:
        for name in self.GATE_NAMES:
            if not isinstance(getattr(self, name), GateResult):
                raise TypeError(f"{name} must be a GateResult instance")
        object.__setattr__(self, "utility_gain", _require_real(self.utility_gain, "utility_gain"))

    def gate_items(self) -> tuple[tuple[str, GateResult], ...]:
        return tuple((name, getattr(self, name)) for name in self.GATE_NAMES)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            name: result.to_dict() for name, result in self.gate_items()
        }
        payload["utility_gain"] = _wire_float(self.utility_gain)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> EvaluationEvidence:
        expected = set(cls.GATE_NAMES) | {"utility_gain"}
        _require_exact_keys(payload, expected, "EvaluationEvidence")
        gate_values: dict[str, GateResult] = {}
        for name in cls.GATE_NAMES:
            raw_gate = payload[name]
            if not isinstance(raw_gate, Mapping):
                raise TypeError(f"{name} must be a mapping")
            gate_values[name] = GateResult.from_dict(raw_gate)
        return cls(
            **gate_values,
            utility_gain=_unwire_float(payload["utility_gain"], "utility_gain"),
        )


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    """A serialization-friendly, auditable promotion verdict."""

    promoted: bool
    utility_gain: float
    min_gain: float
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.promoted) is not bool:
            raise TypeError("promoted must be a bool")
        object.__setattr__(self, "utility_gain", _require_real(self.utility_gain, "utility_gain"))
        object.__setattr__(
            self,
            "min_gain",
            _require_nonnegative_finite_real(self.min_gain, "min_gain"),
        )
        normalized_reasons = tuple(self.reasons)
        if any(not isinstance(reason, str) or not reason.strip() for reason in normalized_reasons):
            raise ValueError("every decision reason must be a non-empty string")
        if self.promoted and normalized_reasons:
            raise ValueError("a promoted decision cannot contain failure reasons")
        if not self.promoted and not normalized_reasons:
            raise ValueError("a rejected decision must contain at least one failure reason")
        object.__setattr__(self, "reasons", normalized_reasons)

    @property
    def accepted(self) -> bool:
        return self.promoted

    @property
    def rejected(self) -> bool:
        return not self.promoted

    @property
    def failure_reasons(self) -> tuple[str, ...]:
        return self.reasons

    def to_dict(self) -> dict[str, object]:
        return {
            "promoted": self.promoted,
            "utility_gain": _wire_float(self.utility_gain),
            "min_gain": self.min_gain,
            "reasons": list(self.reasons),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> PromotionDecision:
        expected = {"promoted", "utility_gain", "min_gain", "reasons"}
        _require_exact_keys(payload, expected, "PromotionDecision")
        raw_reasons = payload["reasons"]
        if isinstance(raw_reasons, (str, bytes)) or not isinstance(raw_reasons, (list, tuple)):
            raise TypeError("reasons must be a list or tuple")
        return cls(
            promoted=payload["promoted"],  # type: ignore[arg-type]
            utility_gain=_unwire_float(payload["utility_gain"], "utility_gain"),
            min_gain=payload["min_gain"],  # type: ignore[arg-type]
            reasons=tuple(raw_reasons),  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class AcceptancePolicy:
    """Conjunctive promotion policy with no score averaging across gates."""

    min_gain: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "min_gain",
            _require_nonnegative_finite_real(self.min_gain, "min_gain"),
        )

    def to_dict(self) -> dict[str, float]:
        return {"min_gain": self.min_gain}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> AcceptancePolicy:
        _require_exact_keys(payload, {"min_gain"}, "AcceptancePolicy")
        return cls(min_gain=payload["min_gain"])  # type: ignore[arg-type]

    def decide(self, evidence: EvaluationEvidence) -> PromotionDecision:
        if not isinstance(evidence, EvaluationEvidence):
            raise TypeError("evidence must be an EvaluationEvidence instance")

        reasons: list[str] = []
        for name, result in evidence.gate_items():
            if not result.passed:
                reasons.append(f"{name} failed: {result.reason}")

        gain = evidence.utility_gain
        if not math.isfinite(gain):
            reasons.append(f"utility_gain is not finite: {_wire_float(gain)}")
        elif gain < self.min_gain:
            reasons.append(
                f"utility_gain {gain!r} is below required minimum {self.min_gain!r}"
            )

        return PromotionDecision(
            promoted=not reasons,
            utility_gain=gain,
            min_gain=self.min_gain,
            reasons=tuple(reasons),
        )


__all__ = [
    "AcceptancePolicy",
    "BudgetAccount",
    "BudgetExceeded",
    "BudgetLimits",
    "BudgetUsage",
    "EvaluationEvidence",
    "GateResult",
    "PromotionDecision",
]
