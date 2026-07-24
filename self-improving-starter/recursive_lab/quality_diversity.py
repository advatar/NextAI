"""Small quality-diversity archive adapted for governed candidate search."""

from __future__ import annotations

import math
import random
import uuid
from dataclasses import dataclass
from typing import Generic, Sequence, TypeVar

C = TypeVar("C")


class MechanismValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class SeededGenerator:
    def __init__(self, seed: int):
        if type(seed) is not int or not 0 <= seed < 1 << 64:
            raise MechanismValidationError("invalid_seed", "seed must be uint64")
        self.state = seed or 0x9E3779B97F4A7C15

    def next_uint64(self):
        self.state = (6364136223846793005 * self.state + 1442695040888963407) & (
            (1 << 64) - 1
        )
        return self.state

    def randrange(self, stop: int):
        if stop <= 0:
            raise MechanismValidationError(
                "invalid_upper_bound", "stop must be positive"
            )
        return self.next_uint64() % stop


def strategy_features(
    *,
    task_utilities: Sequence[float],
    correct: bool,
    tokens: int,
    token_cap: int = 4000,
) -> tuple[float, ...]:
    """Map governed live results to bounded behavior descriptors."""
    if not task_utilities or any(not 0 <= value <= 1 for value in task_utilities):
        raise ValueError("task utilities must be in [0, 1]")
    if tokens < 0 or token_cap < 1:
        raise ValueError("token values must be non-negative")
    return (
        sum(task_utilities) / len(task_utilities),
        min(task_utilities),
        1.0 if correct else 0.0,
        max(0.0, 1.0 - tokens / token_cap),
    )


@dataclass(frozen=True, slots=True)
class CandidateEvaluation:
    objective: float
    features: tuple[float, ...]
    metrics: dict[str, float]


@dataclass(frozen=True, slots=True)
class ArchiveEntry(Generic[C]):
    candidate: C
    evaluation: CandidateEvaluation
    generation: int
    id: str = ""
    parent_id: str | None = None


class QualityDiversityArchive(Generic[C]):
    def __init__(
        self,
        *,
        bins: Sequence[int],
        bounds: Sequence[tuple[float, float]] | None = None,
    ) -> None:
        if not bins or any(type(value) is not int or value < 1 for value in bins):
            raise ValueError("bins must contain positive integers")
        self.bins = tuple(bins)
        self.bounds = tuple(bounds or ((0.0, 1.0),) * len(self.bins))
        if len(self.bounds) != len(self.bins):
            raise ValueError("bounds must match bins")
        if any(
            not math.isfinite(lo) or not math.isfinite(hi) for lo, hi in self.bounds
        ):
            raise MechanismValidationError("non_finite_bound", "bounds must be finite")
        if any(lo >= hi for lo, hi in self.bounds):
            raise ValueError("lower bound must be below upper bound")
        self._entries: dict[tuple[int, ...], ArchiveEntry[C]] = {}
        self.evaluations = 0
        self.improvements = 0

    def _cell(self, features: tuple[float, ...]) -> tuple[int, ...]:
        if len(features) != len(self.bins):
            raise ValueError("feature dimensionality does not match archive")
        if any(not math.isfinite(value) for value in features):
            raise MechanismValidationError(
                "non_finite_feature", "features must be finite"
            )
        return tuple(
            max(
                0,
                min(size - 1, int(((min(max(value, lo), hi) - lo) / (hi - lo)) * size)),
            )
            for value, size, (lo, hi) in zip(features, self.bins, self.bounds)
        )

    def add(
        self,
        candidate: C,
        evaluation: CandidateEvaluation,
        generation: int,
        parent_id: str | None = None,
        entry_id: str | None = None,
    ) -> bool:
        if not isinstance(evaluation, CandidateEvaluation):
            raise ValueError("evaluation must be valid")
        if not math.isfinite(evaluation.objective):
            raise MechanismValidationError(
                "non_finite_objective", "objective must be finite"
            )
        if any(not math.isfinite(value) for value in evaluation.metrics.values()):
            raise MechanismValidationError(
                "non_finite_metric", "metrics must be finite"
            )
        cell = self._cell(evaluation.features)
        self.evaluations += 1
        current = self._entries.get(cell)
        if current is None or evaluation.objective > current.evaluation.objective:
            self._entries[cell] = ArchiveEntry(
                candidate,
                evaluation,
                generation,
                entry_id or str(uuid.uuid4()),
                parent_id,
            )
            self.improvements += 1
            return True
        return False

    @property
    def entries(self) -> tuple[ArchiveEntry[C], ...]:
        return tuple(self._entries.values())

    @property
    def best(self) -> ArchiveEntry[C] | None:
        return max(
            self.entries, key=lambda entry: entry.evaluation.objective, default=None
        )

    def select_parent(self, rng: random.Random) -> C | None:
        return rng.choice(self.entries).candidate if self.entries else None

    def select_entry_stable(self, rng: SeededGenerator) -> ArchiveEntry[C] | None:
        if not self._entries:
            return None
        cells = sorted(self._entries)
        return self._entries[cells[rng.randrange(len(cells))]]

    def entry_in_cell(self, cell: Sequence[int]) -> ArchiveEntry[C] | None:
        return self._entries.get(tuple(cell))

    def stats(self) -> dict[str, float | int | None]:
        best = self.best
        total = math.prod(self.bins)
        return {
            "evaluations": self.evaluations,
            "improvements": self.improvements,
            "occupied_cells": len(self._entries),
            "total_cells": total,
            "coverage": len(self._entries) / total,
            "best_objective": None if best is None else best.evaluation.objective,
        }


__all__ = [
    "ArchiveEntry",
    "CandidateEvaluation",
    "MechanismValidationError",
    "QualityDiversityArchive",
    "SeededGenerator",
    "strategy_features",
]
