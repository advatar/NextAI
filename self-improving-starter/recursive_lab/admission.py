"""Pre-registration admission gate for benchmark cohorts.

Experiment E51 discovered, *after* a cohort had already produced results, that
the cohort could not have measured anything: random exploration reached the
target on 80% of the tasks and the candidate router never once disagreed with
the linear baseline.  No search policy, however good, could have demonstrated an
advantage on that cohort.  The audit was correct but arrived too late, so the
uninformative cohort had already emitted experiment JSON that looked like
evidence.

This module turns that post-hoc audit into a *precondition*.  A runner is
expected to compute :class:`CohortObservations` for a proposed cohort, call
:func:`evaluate_admission`, and then call :func:`require_admitted` before it is
allowed to write any experiment artifact.  A cohort with no measurement headroom
therefore fails closed at pre-registration time and structurally cannot generate
experiment evidence.

The critical semantic is the source of the observations: admission must be
decided from a **random or baseline policy's** behaviour on the cohort — the
question is "can undirected search already solve this?" — and never from the
results of the candidate policy under test.  Admitting a cohort because the
policy under test did well on it would make the benchmark a function of its own
answer, which is precisely the circularity this gate exists to prevent.
:meth:`CohortObservations.from_random_baseline` is the intended constructor and
names that provenance explicitly; the disagreement count is likewise a
structural property of the cohort (do the policies ever behave differently?),
not a measure of whether the candidate policy won.

Only Python's standard library is used, and every dataclass here is frozen so an
admission decision cannot be edited into existence after the fact.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from numbers import Real
from typing import Mapping


SCHEMA_VERSION = 1

_CRITERIA_FIELDS = (
    "maximum_exploration_target_rate",
    "minimum_tasks",
    "minimum_policy_disagreements",
    "minimum_policy_disagreement_rate",
)
_OBSERVATION_FIELDS = (
    "exploration_target_rate",
    "policy_disagreements",
    "tasks",
)


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


def _require_rate(value: object, name: str) -> float:
    """Return a rate in ``[0, 1]``, rejecting non-finite and out-of-range input."""

    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number, not {type(value).__name__}")
    rate = float(value)
    if not math.isfinite(rate):
        raise ValueError(f"{name} must be finite")
    if not 0.0 <= rate <= 1.0:
        raise ValueError(f"{name} must lie in [0, 1], got {rate!r}")
    return rate


def _require_nonnegative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer, not {type(value).__name__}")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _require_positive_int(value: object, name: str) -> int:
    count = _require_nonnegative_int(value, name)
    if count == 0:
        raise ValueError(f"{name} must be positive")
    return count


@dataclass(frozen=True, slots=True)
class AdmissionCriteria:
    """Pre-registered thresholds a cohort must satisfy to be measurable.

    ``maximum_exploration_target_rate`` bounds how often a random/baseline
    policy may already reach the target: a saturated cohort leaves no headroom.
    ``minimum_policy_disagreements`` requires the compared policies to actually
    behave differently somewhere in the cohort, otherwise every comparison is a
    tie by construction.  ``minimum_tasks`` keeps the other two statistics from
    being read off a cohort too small to mean anything.

    ``minimum_policy_disagreement_rate`` exists because an absolute count is
    scale-dependent and becomes vacuous as a cohort grows.  E59 exposed this:
    the ``plateau`` family cleared a minimum of 3 with 8 disagreements over 120
    tasks -- a rate of 6.7% -- and then measured a paired effect of *exactly*
    zero with a degenerate ``[0, 0]`` interval.  A count of 3 is a meaningful
    bar at 5 tasks and no bar at all at 120.  The rate is checked *in addition*
    to the count, conjunctively, consistent with the rest of the governor: a
    cohort must clear both.
    """

    maximum_exploration_target_rate: float = 0.2
    minimum_tasks: int = 5
    minimum_policy_disagreements: int = 3
    minimum_policy_disagreement_rate: float = 0.2

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "maximum_exploration_target_rate",
            _require_rate(
                self.maximum_exploration_target_rate,
                "maximum_exploration_target_rate",
            ),
        )
        object.__setattr__(
            self, "minimum_tasks", _require_positive_int(self.minimum_tasks, "minimum_tasks")
        )
        object.__setattr__(
            self,
            "minimum_policy_disagreements",
            _require_positive_int(
                self.minimum_policy_disagreements, "minimum_policy_disagreements"
            ),
        )
        object.__setattr__(
            self,
            "minimum_policy_disagreement_rate",
            _require_rate(
                self.minimum_policy_disagreement_rate,
                "minimum_policy_disagreement_rate",
            ),
        )
        if self.minimum_policy_disagreements > self.minimum_tasks:
            raise ValueError(
                "minimum_policy_disagreements "
                f"{self.minimum_policy_disagreements!r} cannot exceed minimum_tasks "
                f"{self.minimum_tasks!r}: no cohort could ever satisfy both"
            )

    def to_dict(self) -> dict[str, float | int]:
        return {name: getattr(self, name) for name in _CRITERIA_FIELDS}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> AdmissionCriteria:
        _require_exact_keys(payload, set(_CRITERIA_FIELDS), "AdmissionCriteria")
        return cls(**{name: payload[name] for name in _CRITERIA_FIELDS})  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class CohortObservations:
    """Measured properties of a proposed cohort, taken from baseline behaviour.

    ``exploration_target_rate`` is the fraction of cohort tasks on which a
    random/baseline policy already reaches the target.  It must never be derived
    from the candidate policy under test — see the module docstring.
    """

    exploration_target_rate: float
    policy_disagreements: int
    tasks: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "exploration_target_rate",
            _require_rate(self.exploration_target_rate, "exploration_target_rate"),
        )
        object.__setattr__(
            self,
            "policy_disagreements",
            _require_nonnegative_int(self.policy_disagreements, "policy_disagreements"),
        )
        object.__setattr__(self, "tasks", _require_positive_int(self.tasks, "tasks"))
        if self.policy_disagreements > self.tasks:
            raise ValueError(
                f"policy_disagreements {self.policy_disagreements!r} cannot exceed "
                f"tasks {self.tasks!r}"
            )

    @property
    def policy_disagreement_rate(self) -> float:
        """Fraction of cohort tasks on which the reference policies differ.

        Scale-free companion to the raw count: a cohort where the policies can
        barely ever behave differently cannot express an effect, however many
        tasks it contains.
        """
        return self.policy_disagreements / self.tasks

    @classmethod
    def from_random_baseline(
        cls,
        *,
        tasks: int,
        exploration_target_hits: int,
        policy_disagreements: int,
    ) -> CohortObservations:
        """Build observations from a random/baseline sweep over the cohort.

        ``exploration_target_hits`` counts the tasks a random or baseline policy
        already solved.  This constructor exists so the provenance of the
        admission decision is stated in the call site: the rate is a property of
        undirected search on the cohort, not of the candidate policy.
        """

        task_count = _require_positive_int(tasks, "tasks")
        hits = _require_nonnegative_int(exploration_target_hits, "exploration_target_hits")
        if hits > task_count:
            raise ValueError(
                f"exploration_target_hits {hits!r} cannot exceed tasks {task_count!r}"
            )
        return cls(
            exploration_target_rate=hits / task_count,
            policy_disagreements=policy_disagreements,
            tasks=task_count,
        )

    def to_dict(self) -> dict[str, float | int]:
        return {name: getattr(self, name) for name in _OBSERVATION_FIELDS}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> CohortObservations:
        _require_exact_keys(payload, set(_OBSERVATION_FIELDS), "CohortObservations")
        return cls(**{name: payload[name] for name in _OBSERVATION_FIELDS})  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class AdmissionResult:
    """An auditable verdict on whether a cohort may produce evidence at all."""

    criteria: AdmissionCriteria
    observations: CohortObservations
    admitted: bool
    failures: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.criteria, AdmissionCriteria):
            raise TypeError("criteria must be an AdmissionCriteria instance")
        if not isinstance(self.observations, CohortObservations):
            raise TypeError("observations must be a CohortObservations instance")
        if type(self.admitted) is not bool:
            raise TypeError("admitted must be a bool")
        normalized = tuple(self.failures)
        if any(not isinstance(failure, str) or not failure.strip() for failure in normalized):
            raise ValueError("every failure must be a non-empty string")
        if self.admitted and normalized:
            raise ValueError("an admitted cohort cannot carry failures")
        if not self.admitted and not normalized:
            raise ValueError("a rejected cohort must carry at least one failure")
        object.__setattr__(self, "failures", normalized)

    @property
    def rejected(self) -> bool:
        return not self.admitted

    @property
    def decision(self) -> str:
        return "admit" if self.admitted else "reject and redesign cohort"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "criteria": self.criteria.to_dict(),
            "observed": self.observations.to_dict(),
            "admitted": self.admitted,
            "decision": self.decision,
            "failures": list(self.failures),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> AdmissionResult:
        expected = {"schema_version", "criteria", "observed", "admitted", "decision", "failures"}
        _require_exact_keys(payload, expected, "AdmissionResult")
        if payload["schema_version"] != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported AdmissionResult schema_version {payload['schema_version']!r}"
            )
        raw_criteria = payload["criteria"]
        raw_observed = payload["observed"]
        if not isinstance(raw_criteria, Mapping):
            raise TypeError("criteria must be a mapping")
        if not isinstance(raw_observed, Mapping):
            raise TypeError("observed must be a mapping")
        raw_failures = payload["failures"]
        if isinstance(raw_failures, (str, bytes)) or not isinstance(raw_failures, (list, tuple)):
            raise TypeError("failures must be a list or tuple")
        result = cls(
            criteria=AdmissionCriteria.from_dict(raw_criteria),
            observations=CohortObservations.from_dict(raw_observed),
            admitted=payload["admitted"],  # type: ignore[arg-type]
            failures=tuple(raw_failures),  # type: ignore[arg-type]
        )
        if payload["decision"] != result.decision:
            raise ValueError(
                f"decision {payload['decision']!r} disagrees with admitted "
                f"{result.admitted!r}"
            )
        return result

    def canonical_json(self) -> str:
        """Return deterministic JSON, matching the repository's digest format."""

        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def digest(self) -> str:
        """Return the SHA-256 digest of :meth:`canonical_json`."""

        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def to_report(self) -> dict[str, object]:
        """Return :meth:`to_dict` plus the ``report_digest`` used by experiments."""

        report = self.to_dict()
        report["report_digest"] = self.digest()
        return report


class BenchmarkNotAdmittedError(RuntimeError):
    """Raised when a cohort without measurement headroom tries to produce evidence."""

    def __init__(self, result: AdmissionResult) -> None:
        if not isinstance(result, AdmissionResult):
            raise TypeError("result must be an AdmissionResult instance")
        if result.admitted:
            raise ValueError("BenchmarkNotAdmittedError requires a rejected result")
        self.result = result
        detail = "; ".join(result.failures)
        super().__init__(f"benchmark cohort is not admitted: {detail}")

    def to_dict(self) -> dict[str, object]:
        return {
            "error": type(self).__name__,
            "message": str(self),
            "admission": self.result.to_report(),
        }


def evaluate_admission(
    observations: CohortObservations,
    criteria: AdmissionCriteria | None = None,
) -> AdmissionResult:
    """Judge cohort observations against pre-registered criteria.

    ``observations`` must describe a random/baseline sweep over the cohort, not
    the candidate policy's results.  Every unmet criterion is reported, so one
    call names every reason a cohort has to be redesigned.
    """

    if not isinstance(observations, CohortObservations):
        raise TypeError("observations must be a CohortObservations instance")
    if criteria is None:
        criteria = AdmissionCriteria()
    elif not isinstance(criteria, AdmissionCriteria):
        raise TypeError("criteria must be an AdmissionCriteria instance")

    failures: list[str] = []
    if observations.exploration_target_rate > criteria.maximum_exploration_target_rate:
        failures.append(
            f"exploration_target_rate {observations.exploration_target_rate:.2f} "
            f"exceeds maximum {criteria.maximum_exploration_target_rate:.2f}"
        )
    if observations.policy_disagreements < criteria.minimum_policy_disagreements:
        failures.append(
            f"policy_disagreements {observations.policy_disagreements} "
            f"is below minimum {criteria.minimum_policy_disagreements}"
        )
    if (
        observations.policy_disagreement_rate
        < criteria.minimum_policy_disagreement_rate
    ):
        failures.append(
            f"policy_disagreement_rate {observations.policy_disagreement_rate:.3f} "
            f"is below minimum {criteria.minimum_policy_disagreement_rate:.3f}"
        )
    if observations.tasks < criteria.minimum_tasks:
        failures.append(
            f"tasks {observations.tasks} is below minimum {criteria.minimum_tasks}"
        )

    return AdmissionResult(
        criteria=criteria,
        observations=observations,
        admitted=not failures,
        failures=tuple(failures),
    )


def require_admitted(result: AdmissionResult) -> AdmissionResult:
    """Return ``result`` if admitted, otherwise raise :class:`BenchmarkNotAdmittedError`.

    This is the hard precondition: a runner calls it before it is permitted to
    write experiment JSON, so a cohort that cannot measure anything never emits
    an artifact that could later be mistaken for evidence.
    """

    if not isinstance(result, AdmissionResult):
        raise TypeError("result must be an AdmissionResult instance")
    if not result.admitted:
        raise BenchmarkNotAdmittedError(result)
    return result


def admit_cohort(
    observations: CohortObservations,
    criteria: AdmissionCriteria | None = None,
) -> AdmissionResult:
    """Evaluate and enforce admission in one call, raising on a rejected cohort."""

    return require_admitted(evaluate_admission(observations, criteria))


__all__ = [
    "AdmissionCriteria",
    "AdmissionResult",
    "BenchmarkNotAdmittedError",
    "CohortObservations",
    "SCHEMA_VERSION",
    "admit_cohort",
    "evaluate_admission",
    "require_admitted",
]
