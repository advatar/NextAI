"""Fail-closed candidate-diversity accounting for proposer streams.

This module exists because of a concrete measurement defect.  Experiment
``E58-gemma-governed-program`` spent six live model calls on a local Gemma
model and recorded six receipts in ``model_receipts``.  Every one of those
receipts carries the *same* ``candidate_digest`` and the same
``response_digest``: the proposer emitted one program six times.  The run
nevertheless reported ``valid_candidates: 6``, ``promotion_parity: true`` and
``adoption_gate.passed: true``, because each of those properties is trivially
true when the search only ever saw a single distinct candidate.  Six calls were
billed, one sample was drawn, and the report read as a pass.

The lesson is that a collapsed proposer stream is not a weak result --- it is an
absence of result.  Parity between two selection policies means nothing when
both policies are handed the same single point, and an adoption gate that never
had an alternative to reject has not been exercised.  So this module makes
candidate diversity a precommitted, first-class admission requirement rather
than something a reader is expected to notice by eye afterwards.

Vocabulary (used deliberately and consistently below):

``admissible``
    The stream met its diversity requirement.  Whatever the run then measured
    is a real measurement, and may pass or fail on its merits.
``void``
    The stream did not meet its diversity requirement.  The run is *not* a
    failure and *not* a pass; it produced no evidence about the question it
    claimed to ask, and its comparative claims must be withdrawn rather than
    reported with a negative sign.  A void run is a spent budget, not a result.

The distinction matters scientifically: recording E58 as "failed" would imply
the governed policy was tested and lost, which is exactly the false claim this
module prevents.  :func:`require_diversity` raises
:class:`DegenerateCandidateStreamError` so that a live runner cannot reach the
line that writes a passing experiment report from a collapsed stream.

Like :mod:`recursive_lab.governance`, this module is deliberately
self-contained and uses only the Python standard library.  Report identity is
the SHA-256 digest of a canonical JSON encoding, matching the ``report_digest``
convention used throughout ``experiments/``.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass
from numbers import Real
from typing import Any, ClassVar, Iterable, Mapping


DEFAULT_DIGEST_KEY = "candidate_digest"

#: Run status for a stream that satisfied its diversity requirement.
RUN_STATUS_ADMISSIBLE = "admissible"

#: Run status for a stream that did not.  See the module docstring: a void run
#: is neither a pass nor a failure, and its comparative claims are withdrawn.
RUN_STATUS_VOID = "void"


class DegenerateCandidateStreamError(RuntimeError):
    """Raised when a proposer stream collapsed and the run is therefore void.

    The attached :attr:`report` is the full :class:`DiversityReport`, so a
    caller that catches this error can persist the void verdict as evidence
    instead of persisting a report that would have read as a pass.
    """

    def __init__(self, report: DiversityReport) -> None:
        if not isinstance(report, DiversityReport):
            raise TypeError("report must be a DiversityReport instance")
        self.report = report
        detail = "; ".join(report.failures) or "diversity requirement unmet"
        super().__init__(
            f"run is {RUN_STATUS_VOID}: degenerate candidate stream "
            f"({report.unique_candidates}/{report.total_candidates} unique): {detail}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": type(self).__name__,
            "message": str(self),
            "run_status": RUN_STATUS_VOID,
            "diversity": self.report.to_dict(),
        }


def _require_positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer, not {type(value).__name__}")
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value


def _require_nonnegative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer, not {type(value).__name__}")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _require_unit_interval(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number, not {type(value).__name__}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must lie in [0.0, 1.0], got {result!r}")
    return result


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


def canonical_json(value: Any) -> str:
    """Return deterministic JSON suitable for hashing and durable storage."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def report_digest(payload: Mapping[str, Any]) -> str:
    """Return the SHA-256 digest of ``payload`` under canonical JSON encoding."""

    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping")
    return hashlib.sha256(canonical_json(dict(payload)).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class DiversityRequirement:
    """A precommitted lower bound on how much a proposer stream must explore.

    ``minimum_unique_candidates`` guards against the E58 shape directly: a
    stream of identical programs can never reach two.  ``minimum_unique_ratio``
    additionally scales with effort, so buying more model calls cannot dilute
    the requirement.  ``maximum_repeat_ratio`` bounds the share of the stream a
    single digest may occupy, which is the clearest signature of a stuck
    proposer even when a few stray variants keep the other two counters happy.
    """

    minimum_unique_candidates: int = 2
    minimum_unique_ratio: float = 0.5
    minimum_total_candidates: int = 2
    maximum_repeat_ratio: float = 1.0

    FIELDS: ClassVar[tuple[str, ...]] = (
        "minimum_unique_candidates",
        "minimum_unique_ratio",
        "minimum_total_candidates",
        "maximum_repeat_ratio",
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "minimum_unique_candidates",
            _require_positive_int(self.minimum_unique_candidates, "minimum_unique_candidates"),
        )
        object.__setattr__(
            self,
            "minimum_total_candidates",
            _require_positive_int(self.minimum_total_candidates, "minimum_total_candidates"),
        )
        object.__setattr__(
            self,
            "minimum_unique_ratio",
            _require_unit_interval(self.minimum_unique_ratio, "minimum_unique_ratio"),
        )
        object.__setattr__(
            self,
            "maximum_repeat_ratio",
            _require_unit_interval(self.maximum_repeat_ratio, "maximum_repeat_ratio"),
        )
        if self.maximum_repeat_ratio <= 0.0:
            raise ValueError("maximum_repeat_ratio must be greater than 0.0")
        if self.minimum_unique_candidates > self.minimum_total_candidates:
            raise ValueError(
                "minimum_unique_candidates "
                f"{self.minimum_unique_candidates!r} cannot exceed "
                f"minimum_total_candidates {self.minimum_total_candidates!r}"
            )

    def to_dict(self) -> dict[str, int | float]:
        return {name: getattr(self, name) for name in self.FIELDS}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> DiversityRequirement:
        _require_exact_keys(payload, set(cls.FIELDS), "DiversityRequirement")
        return cls(**{name: payload[name] for name in cls.FIELDS})  # type: ignore[arg-type]

    def assess(
        self,
        candidates: Iterable[str | Mapping[str, Any]],
        *,
        digest_key: str = DEFAULT_DIGEST_KEY,
    ) -> DiversityReport:
        """Convenience wrapper around :func:`assess_candidate_diversity`."""

        return assess_candidate_diversity(candidates, self, digest_key=digest_key)


#: The default requirement.  Two distinct candidates out of at least two draws,
#: at least half of them distinct.  This is the weakest bound that still voids
#: the E58 collapse.
DEFAULT_DIVERSITY_REQUIREMENT = DiversityRequirement()


@dataclass(frozen=True, slots=True)
class DiversityReport:
    """An immutable, auditable verdict on one proposer stream.

    ``failures`` is stored as a tuple so the report stays frozen and hashable;
    :meth:`to_dict` emits it as a JSON list, matching the ``reasons`` handling
    in :mod:`recursive_lab.governance`.  ``most_repeated_digest`` and
    ``most_repeated_count`` are carried explicitly because they are what an
    operator actually needs when diagnosing a stuck proposer: they name the one
    program the model kept re-emitting and say how many calls it consumed.
    """

    requirement: DiversityRequirement
    total_candidates: int
    unique_candidates: int
    unique_ratio: float
    satisfied: bool
    failures: tuple[str, ...] = ()
    most_repeated_digest: str | None = None
    most_repeated_count: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.requirement, DiversityRequirement):
            raise TypeError("requirement must be a DiversityRequirement instance")
        object.__setattr__(
            self,
            "total_candidates",
            _require_nonnegative_int(self.total_candidates, "total_candidates"),
        )
        object.__setattr__(
            self,
            "unique_candidates",
            _require_nonnegative_int(self.unique_candidates, "unique_candidates"),
        )
        object.__setattr__(
            self,
            "most_repeated_count",
            _require_nonnegative_int(self.most_repeated_count, "most_repeated_count"),
        )
        object.__setattr__(
            self,
            "unique_ratio",
            _require_unit_interval(self.unique_ratio, "unique_ratio"),
        )
        if type(self.satisfied) is not bool:
            raise TypeError("satisfied must be a bool")
        if self.unique_candidates > self.total_candidates:
            raise ValueError("unique_candidates cannot exceed total_candidates")
        if self.most_repeated_count > self.total_candidates:
            raise ValueError("most_repeated_count cannot exceed total_candidates")
        if self.most_repeated_digest is not None and not isinstance(
            self.most_repeated_digest, str
        ):
            raise TypeError("most_repeated_digest must be a string or None")
        failures = tuple(self.failures)
        if any(not isinstance(item, str) or not item.strip() for item in failures):
            raise ValueError("every failure reason must be a non-empty string")
        if self.satisfied and failures:
            raise ValueError("a satisfied report cannot carry failure reasons")
        if not self.satisfied and not failures:
            raise ValueError("an unsatisfied report must carry at least one reason")
        object.__setattr__(self, "failures", failures)

    @property
    def void(self) -> bool:
        """Whether the run must be treated as void rather than passed or failed."""

        return not self.satisfied

    @property
    def admissible(self) -> bool:
        return self.satisfied

    @property
    def run_status(self) -> str:
        """Either :data:`RUN_STATUS_ADMISSIBLE` or :data:`RUN_STATUS_VOID`."""

        return RUN_STATUS_ADMISSIBLE if self.satisfied else RUN_STATUS_VOID

    @property
    def repeat_ratio(self) -> float:
        if self.total_candidates == 0:
            return 0.0
        return self.most_repeated_count / self.total_candidates

    @property
    def collapsed(self) -> bool:
        """Whether every observed candidate was byte-identical (the E58 shape)."""

        return self.total_candidates > 0 and self.unique_candidates == 1

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "requirement": self.requirement.to_dict(),
            "total_candidates": self.total_candidates,
            "unique_candidates": self.unique_candidates,
            "unique_ratio": self.unique_ratio,
            "satisfied": self.satisfied,
            "run_status": self.run_status,
            "collapsed": self.collapsed,
            "failures": list(self.failures),
            "most_repeated_digest": self.most_repeated_digest,
            "most_repeated_count": self.most_repeated_count,
            "repeat_ratio": self.repeat_ratio,
        }
        payload["report_digest"] = report_digest(payload)
        return payload

    @property
    def digest(self) -> str:
        """Content digest of this report, matching the ``report_digest`` field."""

        payload = self.to_dict()
        payload.pop("report_digest")
        return report_digest(payload)

    def require(self) -> DiversityReport:
        """Convenience wrapper around :func:`require_diversity`."""

        return require_diversity(self)


def _normalize_digest(value: object, position: int, digest_key: str) -> str:
    if isinstance(value, Mapping):
        if digest_key not in value:
            raise ValueError(
                f"candidate {position} is a mapping without a {digest_key!r} key; "
                "cannot account for diversity fail-closed"
            )
        value = value[digest_key]
    if value is None:
        raise ValueError(
            f"candidate {position} has a null digest; filter unusable receipts "
            "explicitly rather than letting them dilute the diversity count"
        )
    if not isinstance(value, str):
        raise TypeError(
            f"candidate {position} digest must be a string, not {type(value).__name__}"
        )
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"candidate {position} digest must not be empty")
    return normalized


def extract_candidate_digests(
    candidates: Iterable[str | Mapping[str, Any]],
    *,
    digest_key: str = DEFAULT_DIGEST_KEY,
) -> tuple[str, ...]:
    """Normalize bare digests or receipt mappings into a tuple of digests.

    Both shapes are supported on purpose: ``model_receipts`` entries in
    ``experiments/*.json`` are mappings carrying ``candidate_digest``, while an
    in-process runner usually already holds the digests themselves.
    """

    if isinstance(candidates, (str, bytes, Mapping)):
        raise TypeError("candidates must be an iterable of digests or receipt mappings")
    if not isinstance(digest_key, str) or not digest_key:
        raise ValueError("digest_key must be a non-empty string")
    return tuple(
        _normalize_digest(item, position, digest_key)
        for position, item in enumerate(candidates)
    )


def assess_candidate_diversity(
    candidates: Iterable[str | Mapping[str, Any]],
    requirement: DiversityRequirement = DEFAULT_DIVERSITY_REQUIREMENT,
    *,
    digest_key: str = DEFAULT_DIGEST_KEY,
) -> DiversityReport:
    """Measure a proposer stream against ``requirement`` and return a report.

    This never raises on a degenerate stream; it reports one.  Call
    :func:`require_diversity` (or :func:`enforce_candidate_diversity`) at the
    point where a run would otherwise commit a result to disk.
    """

    if not isinstance(requirement, DiversityRequirement):
        raise TypeError("requirement must be a DiversityRequirement instance")

    digests = extract_candidate_digests(candidates, digest_key=digest_key)
    total = len(digests)
    counts = Counter(digests)
    unique = len(counts)
    ratio = unique / total if total else 0.0

    if counts:
        # Sort by descending count then by digest, so ties resolve identically
        # on every runtime and the report digest stays reproducible.
        most_repeated_digest, most_repeated_count = min(
            counts.items(), key=lambda item: (-item[1], item[0])
        )
    else:
        most_repeated_digest, most_repeated_count = None, 0

    failures: list[str] = []
    if total < requirement.minimum_total_candidates:
        failures.append(
            f"observed {total} candidates, requires at least "
            f"{requirement.minimum_total_candidates}"
        )
    if unique < requirement.minimum_unique_candidates:
        failures.append(
            f"observed {unique} unique candidates, requires at least "
            f"{requirement.minimum_unique_candidates}"
        )
    if total and ratio < requirement.minimum_unique_ratio:
        failures.append(
            f"unique ratio {ratio:.6f} is below required minimum "
            f"{requirement.minimum_unique_ratio:.6f}"
        )
    if total and most_repeated_count / total > requirement.maximum_repeat_ratio:
        failures.append(
            f"digest {most_repeated_digest} occupies "
            f"{most_repeated_count}/{total} of the stream, above the permitted "
            f"repeat ratio {requirement.maximum_repeat_ratio:.6f}"
        )

    return DiversityReport(
        requirement=requirement,
        total_candidates=total,
        unique_candidates=unique,
        unique_ratio=ratio,
        satisfied=not failures,
        failures=tuple(failures),
        most_repeated_digest=most_repeated_digest,
        most_repeated_count=most_repeated_count,
    )


def require_diversity(report: DiversityReport) -> DiversityReport:
    """Return ``report`` if the stream was admissible, else void the run.

    A live runner calls this *before* writing its experiment report, so a
    collapsed stream raises :class:`DegenerateCandidateStreamError` instead of
    producing a file whose ``promotion_parity`` and ``adoption_gate`` fields are
    true only because there was nothing to compare.
    """

    if not isinstance(report, DiversityReport):
        raise TypeError("report must be a DiversityReport instance")
    if report.void:
        raise DegenerateCandidateStreamError(report)
    return report


def enforce_candidate_diversity(
    candidates: Iterable[str | Mapping[str, Any]],
    requirement: DiversityRequirement = DEFAULT_DIVERSITY_REQUIREMENT,
    *,
    digest_key: str = DEFAULT_DIGEST_KEY,
) -> DiversityReport:
    """Assess and immediately require diversity in one fail-closed call."""

    return require_diversity(
        assess_candidate_diversity(candidates, requirement, digest_key=digest_key)
    )


def void_run_payload(
    report: DiversityReport,
    *,
    experiment_id: str,
    claim_boundary: str = "",
) -> dict[str, Any]:
    """Build the record a voided run should persist instead of its results.

    The payload deliberately carries no scores.  A void run has no comparative
    claim to make; what it has is a spent budget and a diagnosis.
    """

    if not isinstance(experiment_id, str) or not experiment_id.strip():
        raise ValueError("experiment_id must be a non-empty string")
    if not isinstance(claim_boundary, str):
        raise TypeError("claim_boundary must be a string")
    if not isinstance(report, DiversityReport):
        raise TypeError("report must be a DiversityReport instance")

    payload: dict[str, Any] = {
        "experiment_id": experiment_id.strip(),
        "run_status": report.run_status,
        "claim_boundary": claim_boundary.strip()
        or "no comparative claim: candidate stream did not meet its diversity "
        "requirement, so the run is void rather than passed or failed",
        "diversity": report.to_dict(),
    }
    payload["report_digest"] = report_digest(payload)
    return payload


__all__ = [
    "DEFAULT_DIGEST_KEY",
    "DEFAULT_DIVERSITY_REQUIREMENT",
    "RUN_STATUS_ADMISSIBLE",
    "RUN_STATUS_VOID",
    "DegenerateCandidateStreamError",
    "DiversityReport",
    "DiversityRequirement",
    "assess_candidate_diversity",
    "canonical_json",
    "enforce_candidate_diversity",
    "extract_candidate_digests",
    "report_digest",
    "require_diversity",
    "void_run_payload",
]
