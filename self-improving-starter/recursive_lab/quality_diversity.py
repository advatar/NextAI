"""Small quality-diversity archive adapted for governed candidate search."""
from __future__ import annotations
import random
from dataclasses import dataclass
from typing import Any, Callable, Generic, Sequence, TypeVar

C = TypeVar("C")

def strategy_features(*, task_utilities: Sequence[float], correct: bool, tokens: int, token_cap: int = 4000) -> tuple[float, ...]:
    """Map governed live results to bounded behavior descriptors."""
    if not task_utilities or any(not 0 <= value <= 1 for value in task_utilities):
        raise ValueError("task utilities must be in [0, 1]")
    if tokens < 0 or token_cap < 1:
        raise ValueError("token values must be non-negative")
    return (sum(task_utilities) / len(task_utilities), min(task_utilities), 1.0 if correct else 0.0, max(0.0, 1.0 - tokens / token_cap))

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

class QualityDiversityArchive(Generic[C]):
    def __init__(self, *, bins: Sequence[int]) -> None:
        if not bins or any(type(value) is not int or value < 1 for value in bins):
            raise ValueError("bins must contain positive integers")
        self.bins = tuple(bins)
        self._entries: dict[tuple[int, ...], ArchiveEntry[C]] = {}
        self.evaluations = 0

    def _cell(self, features: tuple[float, ...]) -> tuple[int, ...]:
        if len(features) != len(self.bins):
            raise ValueError("feature dimensionality does not match archive")
        return tuple(max(0, min(size - 1, int(value * size))) for value, size in zip(features, self.bins))

    def add(self, candidate: C, evaluation: CandidateEvaluation, generation: int) -> bool:
        if not isinstance(evaluation, CandidateEvaluation) or evaluation.objective != evaluation.objective:
            raise ValueError("evaluation must be finite and valid")
        cell = self._cell(evaluation.features); self.evaluations += 1
        current = self._entries.get(cell)
        if current is None or evaluation.objective > current.evaluation.objective:
            self._entries[cell] = ArchiveEntry(candidate, evaluation, generation)
            return True
        return False

    @property
    def entries(self) -> tuple[ArchiveEntry[C], ...]:
        return tuple(self._entries.values())

    @property
    def best(self) -> ArchiveEntry[C] | None:
        return max(self.entries, key=lambda entry: entry.evaluation.objective, default=None)

    def select_parent(self, rng: random.Random) -> C | None:
        return rng.choice(self.entries).candidate if self.entries else None

    def stats(self) -> dict[str, float | int | None]:
        best = self.best
        return {"evaluations": self.evaluations, "occupied_cells": len(self._entries), "best_objective": None if best is None else best.evaluation.objective}

__all__ = ["ArchiveEntry", "CandidateEvaluation", "QualityDiversityArchive", "strategy_features"]
