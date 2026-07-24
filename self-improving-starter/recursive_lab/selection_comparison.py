"""Matched-budget comparison of simple selection policies.

This module deliberately separates the search policy from proposal generation
and evaluation.  The same seeded mutation stream and the same evaluation count
are used for greedy, random-mutation, and quality-diversity runs.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import asdict, dataclass
from typing import Callable, Mapping, TypeVar

from .quality_diversity import CandidateEvaluation, QualityDiversityArchive

C = TypeVar("C")
POLICIES = ("greedy", "random_mutation", "quality_diversity")


@dataclass(frozen=True, slots=True)
class ComparisonBudget:
    proposals: int
    tasks_per_evaluation: int = 3

    def __post_init__(self) -> None:
        if type(self.proposals) is not int or self.proposals < 1:
            raise ValueError("proposals must be a positive integer")
        if type(self.tasks_per_evaluation) is not int or self.tasks_per_evaluation < 1:
            raise ValueError("tasks_per_evaluation must be a positive integer")


@dataclass(frozen=True, slots=True)
class SearchStep:
    proposal: int
    parent_objective: float | None
    candidate_objective: float
    accepted: bool
    best_objective: float
    occupied_cells: int | None


@dataclass(frozen=True, slots=True)
class PolicyResult:
    policy: str
    seed: int
    proposal_budget: int
    candidate_evaluations: int
    task_evaluations: int
    best_objective: float
    best_metrics: dict[str, float]
    occupied_cells: int | None
    trajectory: tuple[SearchStep, ...]


def _validate_evaluation(value: CandidateEvaluation) -> None:
    if not isinstance(value, CandidateEvaluation):
        raise ValueError("evaluator must return CandidateEvaluation")
    values = (value.objective, *value.features, *value.metrics.values())
    if not values or any(
        type(item) not in {int, float} or not math.isfinite(float(item))
        for item in values
    ):
        raise ValueError("evaluation values must be finite real numbers")
    if any(not 0.0 <= feature <= 1.0 for feature in value.features):
        raise ValueError("behavior features must be in [0, 1]")


def run_policy(
    *,
    policy: str,
    initial: C,
    mutate: Callable[[C, random.Random], C],
    evaluate: Callable[[C], CandidateEvaluation],
    budget: ComparisonBudget,
    seed: int,
    bins: tuple[int, ...],
) -> PolicyResult:
    """Run one policy; the initial evaluation is outside the proposal budget."""
    if policy not in POLICIES:
        raise ValueError(f"policy must be one of {POLICIES}")
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    rng = random.Random(seed)
    initial_evaluation = evaluate(initial)
    _validate_evaluation(initial_evaluation)
    if len(initial_evaluation.features) != len(bins):
        raise ValueError("bins must match evaluator feature dimensionality")

    best_candidate, best_evaluation = initial, initial_evaluation
    population: list[tuple[C, CandidateEvaluation]] = [(initial, initial_evaluation)]
    archive: QualityDiversityArchive[C] | None = None
    if policy == "quality_diversity":
        archive = QualityDiversityArchive(bins=bins)
        archive.add(initial, initial_evaluation, 0)

    steps: list[SearchStep] = []
    for proposal in range(1, budget.proposals + 1):
        if policy == "greedy":
            parent, parent_evaluation = best_candidate, best_evaluation
        elif policy == "random_mutation":
            # Uniform parent sampling is the neutral control: fitness and
            # archive cells do not influence which mutation gets attempted.
            parent, parent_evaluation = rng.choice(population)
        else:
            assert archive is not None
            parent = archive.select_parent(rng)
            assert parent is not None
            parent_evaluation = next(
                entry.evaluation
                for entry in archive.entries
                if entry.candidate is parent or entry.candidate == parent
            )

        candidate = mutate(parent, rng)
        candidate_evaluation = evaluate(candidate)
        _validate_evaluation(candidate_evaluation)
        population.append((candidate, candidate_evaluation))

        if policy == "greedy":
            accepted = candidate_evaluation.objective > best_evaluation.objective
        elif policy == "random_mutation":
            accepted = True
        else:
            assert archive is not None
            accepted = archive.add(candidate, candidate_evaluation, proposal)

        if candidate_evaluation.objective > best_evaluation.objective:
            best_candidate, best_evaluation = candidate, candidate_evaluation
        steps.append(
            SearchStep(
                proposal=proposal,
                parent_objective=parent_evaluation.objective,
                candidate_objective=candidate_evaluation.objective,
                accepted=accepted,
                best_objective=best_evaluation.objective,
                occupied_cells=None if archive is None else len(archive.entries),
            )
        )

    return PolicyResult(
        policy=policy,
        seed=seed,
        proposal_budget=budget.proposals,
        candidate_evaluations=budget.proposals,
        task_evaluations=budget.proposals * budget.tasks_per_evaluation,
        best_objective=best_evaluation.objective,
        best_metrics=dict(best_evaluation.metrics),
        occupied_cells=None if archive is None else len(archive.entries),
        trajectory=tuple(steps),
    )


def run_archive_recombination(
    *,
    initial: C,
    crossover: Callable[[C, C, random.Random], C],
    mutate: Callable[[C, random.Random], C],
    evaluate: Callable[[C], CandidateEvaluation],
    budget: ComparisonBudget,
    seed: int,
    bins: tuple[int, ...],
) -> PolicyResult:
    """Run an AlphaEvolve-style two-parent archive search under a fixed budget."""
    rng = random.Random(seed)
    initial_evaluation = evaluate(initial)
    _validate_evaluation(initial_evaluation)
    if len(initial_evaluation.features) != len(bins):
        raise ValueError("bins must match evaluator feature dimensionality")
    archive: QualityDiversityArchive[C] = QualityDiversityArchive(bins=bins)
    archive.add(initial, initial_evaluation, 0)
    best_evaluation = initial_evaluation
    steps = []
    for proposal in range(1, budget.proposals + 1):
        entries = archive.entries
        first = rng.choice(entries)
        second = rng.choice(entries)
        child = mutate(crossover(first.candidate, second.candidate, rng), rng)
        evaluation = evaluate(child)
        _validate_evaluation(evaluation)
        accepted = archive.add(child, evaluation, proposal)
        if evaluation.objective > best_evaluation.objective:
            best_evaluation = evaluation
        steps.append(
            SearchStep(
                proposal,
                max(first.evaluation.objective, second.evaluation.objective),
                evaluation.objective,
                accepted,
                best_evaluation.objective,
                len(archive.entries),
            )
        )
    return PolicyResult(
        "archive_recombination",
        seed,
        budget.proposals,
        budget.proposals,
        budget.proposals * budget.tasks_per_evaluation,
        best_evaluation.objective,
        dict(best_evaluation.metrics),
        len(archive.entries),
        tuple(steps),
    )


def compare_policies(
    *,
    initial: C,
    mutate: Callable[[C, random.Random], C],
    evaluate: Callable[[C], CandidateEvaluation],
    budget: ComparisonBudget,
    seeds: tuple[int, ...],
    bins: tuple[int, ...],
) -> dict:
    if (
        not seeds
        or any(type(seed) is not int for seed in seeds)
        or len(set(seeds)) != len(seeds)
    ):
        raise ValueError("seeds must be distinct integers")
    results = [
        run_policy(
            policy=policy,
            initial=initial,
            mutate=mutate,
            evaluate=evaluate,
            budget=budget,
            seed=seed,
            bins=bins,
        )
        for seed in seeds
        for policy in POLICIES
    ]
    summaries = {}
    for policy in POLICIES:
        cohort = [result for result in results if result.policy == policy]
        objectives = [result.best_objective for result in cohort]
        summaries[policy] = {
            "runs": len(cohort),
            "mean_best_objective": math.fsum(objectives) / len(objectives),
            "min_best_objective": min(objectives),
            "max_best_objective": max(objectives),
            "proposal_budget_per_run": budget.proposals,
            "candidate_evaluations_per_run": budget.proposals,
            "task_evaluations_per_run": budget.proposals * budget.tasks_per_evaluation,
        }
    payload = {
        "schema_version": 1,
        "claim_boundary": "deterministic three-task search-policy comparison; no recursive-improvement claim",
        "policies": list(POLICIES),
        "seeds": list(seeds),
        "budget": asdict(budget),
        "matched_budget": all(
            result.candidate_evaluations == budget.proposals
            and result.task_evaluations
            == budget.proposals * budget.tasks_per_evaluation
            for result in results
        ),
        "summaries": summaries,
        "runs": [asdict(result) for result in results],
    }
    canonical = json.dumps(
        payload, allow_nan=False, sort_keys=True, separators=(",", ":")
    )
    payload["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    return payload


def budget_curve(
    report: Mapping, checkpoints: tuple[int, ...], *, target_objective: float = 1.0
) -> dict:
    """Summarize exact trajectory prefixes from one maximum-budget run."""
    if (
        not checkpoints
        or any(type(value) is not int or value < 1 for value in checkpoints)
        or tuple(sorted(set(checkpoints))) != checkpoints
    ):
        raise ValueError("checkpoints must be unique increasing positive integers")
    if type(target_objective) not in {int, float} or not math.isfinite(
        float(target_objective)
    ):
        raise ValueError("target_objective must be finite")
    runs = report.get("runs") if isinstance(report, Mapping) else None
    policies = report.get("policies") if isinstance(report, Mapping) else None
    seeds = report.get("seeds") if isinstance(report, Mapping) else None
    if (
        not isinstance(runs, list)
        or not isinstance(policies, list)
        or not isinstance(seeds, list)
    ):
        raise ValueError("report is missing comparison runs, policies, or seeds")
    if any(
        not isinstance(run, Mapping) or run.get("proposal_budget", 0) < checkpoints[-1]
        for run in runs
    ):
        raise ValueError("checkpoint exceeds a run's proposal budget")
    points = []
    for checkpoint in checkpoints:
        summaries = {}
        for policy in policies:
            cohort = [run for run in runs if run.get("policy") == policy]
            if len(cohort) != len(seeds):
                raise ValueError("each policy must have exactly one run per seed")
            values = [
                run["trajectory"][checkpoint - 1]["best_objective"] for run in cohort
            ]
            first_hits = [
                next(
                    (
                        step["proposal"]
                        for step in run["trajectory"][:checkpoint]
                        if step["best_objective"] >= target_objective
                    ),
                    None,
                )
                for run in cohort
            ]
            hits = [value for value in first_hits if value is not None]
            summaries[policy] = {
                "mean_best_objective": math.fsum(values) / len(values),
                "target_hit_rate": len(hits) / len(first_hits),
                "mean_proposals_to_target_when_hit": None
                if not hits
                else math.fsum(hits) / len(hits),
                "candidate_evaluations_per_run": checkpoint,
                "task_evaluations_per_run": checkpoint
                * report["budget"]["tasks_per_evaluation"],
            }
        points.append({"proposal_budget": checkpoint, "policies": summaries})
    return {
        "target_objective": float(target_objective),
        "checkpoints": list(checkpoints),
        "points": points,
    }


__all__ = [
    "ComparisonBudget",
    "POLICIES",
    "PolicyResult",
    "SearchStep",
    "budget_curve",
    "compare_policies",
    "run_archive_recombination",
    "run_policy",
]
