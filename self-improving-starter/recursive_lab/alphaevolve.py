"""Auditable, model-agnostic AlphaEvolve-style program evolution loop."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Callable, Generic, Protocol, Sequence, TypeVar

from .quality_diversity import CandidateEvaluation, QualityDiversityArchive

C = TypeVar("C")


@dataclass(frozen=True, slots=True)
class ProgramRecord(Generic[C]):
    program_id: str
    candidate: C
    evaluation: CandidateEvaluation
    generation: int
    parent_id: str | None
    inspiration_ids: tuple[str, ...]
    proposer: str


@dataclass(frozen=True, slots=True)
class PromptSample(Generic[C]):
    parent: ProgramRecord[C]
    inspirations: tuple[ProgramRecord[C], ...]
    feedback: dict[str, float]


class ProgramProposer(Protocol[C]):
    name: str

    def propose(self, sample: PromptSample[C], rng: random.Random) -> C: ...


@dataclass(frozen=True, slots=True)
class EvolutionBudget:
    proposals: int
    task_evaluations_per_proposal: int
    inspirations: int = 2

    def __post_init__(self):
        if any(
            type(v) is not int or v < 1
            for v in (
                self.proposals,
                self.task_evaluations_per_proposal,
                self.inspirations,
            )
        ):
            raise ValueError("budget values must be positive integers")


@dataclass(frozen=True, slots=True)
class EvolutionResult(Generic[C]):
    records: tuple[ProgramRecord[C], ...]
    best: ProgramRecord[C]
    model_calls: int
    candidate_evaluations: int
    task_evaluations: int
    proposer_calls: dict[str, int]


class ProgramDatabase(Generic[C]):
    def __init__(self, bins: Sequence[int], fingerprint: Callable[[C], str]):
        self.archive = QualityDiversityArchive[ProgramRecord[C]](bins=bins)
        self.records: list[ProgramRecord[C]] = []
        self._fingerprint = fingerprint
        self._seen: set[str] = set()

    def add(
        self,
        candidate: C,
        evaluation: CandidateEvaluation,
        generation: int,
        parent_id: str | None,
        inspiration_ids: tuple[str, ...],
        proposer: str,
    ) -> ProgramRecord[C] | None:
        digest = self._fingerprint(candidate)
        if digest in self._seen:
            return None
        self._seen.add(digest)
        record = ProgramRecord(
            digest,
            candidate,
            evaluation,
            generation,
            parent_id,
            inspiration_ids,
            proposer,
        )
        self.records.append(record)
        self.archive.add(record, evaluation, generation)
        return record

    def sample(self, rng: random.Random, inspiration_count: int) -> PromptSample[C]:
        entries = self.archive.entries
        if not entries:
            raise RuntimeError("program database is empty")
        # Mix exploitation and exploration: half the time use the champion,
        # otherwise uniformly sample an occupied behavior cell.
        parent = (
            self.archive.best.candidate
            if rng.random() < 0.5
            else rng.choice(entries).candidate
        )
        pool = [
            entry.candidate
            for entry in entries
            if entry.candidate.program_id != parent.program_id
        ]
        inspirations = tuple(rng.sample(pool, min(inspiration_count, len(pool))))
        return PromptSample(parent, inspirations, dict(parent.evaluation.metrics))


def evolve_programs(
    *,
    initial: C,
    proposers: Sequence[ProgramProposer[C]],
    evaluate: Callable[[C], CandidateEvaluation],
    fingerprint: Callable[[C], str],
    budget: EvolutionBudget,
    seed: int,
    bins: tuple[int, ...],
) -> EvolutionResult[C]:
    if not proposers:
        raise ValueError("at least one proposer is required")
    rng = random.Random(seed)
    database = ProgramDatabase(bins, fingerprint)
    initial_eval = evaluate(initial)
    seed_record = database.add(initial, initial_eval, 0, None, (), "seed")
    assert seed_record is not None
    calls = {proposer.name: 0 for proposer in proposers}
    for generation in range(1, budget.proposals + 1):
        proposer = proposers[(generation - 1) % len(proposers)]
        sample = database.sample(rng, budget.inspirations)
        candidate = proposer.propose(sample, rng)
        calls[proposer.name] += 1
        evaluation = evaluate(candidate)
        database.add(
            candidate,
            evaluation,
            generation,
            sample.parent.program_id,
            tuple(item.program_id for item in sample.inspirations),
            proposer.name,
        )
    best_entry = database.archive.best
    assert best_entry is not None
    return EvolutionResult(
        tuple(database.records),
        best_entry.candidate,
        budget.proposals,
        budget.proposals,
        budget.proposals * budget.task_evaluations_per_proposal,
        calls,
    )


def text_fingerprint(value: object) -> str:
    return hashlib.sha256(repr(value).encode()).hexdigest()


__all__ = [
    "EvolutionBudget",
    "EvolutionResult",
    "ProgramDatabase",
    "ProgramProposer",
    "ProgramRecord",
    "PromptSample",
    "evolve_programs",
    "text_fingerprint",
]
