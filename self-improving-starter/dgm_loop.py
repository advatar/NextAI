"""The self-improvement loop: select -> propose -> evaluate -> archive.

One iteration of the Darwin Gödel Machine:
  1. Select a parent from the archive (∝ perf / (1 + children)).
  2. Ask the proposer (LLM) to mutate the parent's solution.
  3. Evaluate the candidate on the environment (execution-verified reward).
  4. Add it to the archive if it beats its parent OR adds novelty.

The returned trajectories are an audit-friendly object-level record. The
historical ``rl/dataset.py`` skeleton does not yet export them as verified model
completions; weight training remains gated on a separate isolated reward worker
and disjoint task splits.
"""

from __future__ import annotations

import random
import math
import numbers
from dataclasses import dataclass
from typing import Protocol

from archive import Archive, Node
from environments.base import Environment, ScoreResult
from proposer import Proposer


DEFAULT_MAX_CANDIDATE_BYTES = 256 * 1024


class CandidateProposer(Protocol):
    def propose(self, task_prompt: str, parent_source: str) -> str: ...


@dataclass
class Trajectory:
    round_index: int
    parent_id: int
    prompt: str
    solution: str | None
    reward: float | None
    correct: bool | None
    accepted: bool
    status: str
    detail: str


def _novel(source: str, archive: Archive) -> bool:
    """Use content novelty, not noisy scalar-reward novelty.

    DGM keeps some non-improving variants when they add novelty, because they can
    seed later breakthroughs. Source identity is still only a minimal proxy for
    behavioral novelty, but it does not mistake timing jitter for novelty.
    """
    return not archive.contains_source(source)


def _safe_error_detail(error: BaseException, *, limit: int = 2_000) -> str:
    try:
        detail = str(error)
    except Exception:
        detail = ""
    rendered = f"{type(error).__name__}: {detail}" if detail else type(error).__name__
    return rendered[:limit]


def _validate_score_result(result) -> str | None:
    if not isinstance(result, ScoreResult):
        return "evaluator must return ScoreResult"
    if type(result.reward) not in {int, float}:
        return "evaluator reward must be a finite real number"
    try:
        reward_is_finite = math.isfinite(float(result.reward))
    except (OverflowError, TypeError, ValueError):
        reward_is_finite = False
    if not reward_is_finite:
        return "evaluator reward must be a finite real number"
    if type(result.correct) is not bool:
        return "evaluator correctness must be a bool"
    if result.raw is not None:
        if type(result.raw) not in {int, float}:
            return "evaluator raw metric must be null or a finite real number"
        try:
            raw_is_finite = math.isfinite(float(result.raw))
        except (OverflowError, TypeError, ValueError):
            raw_is_finite = False
        if not raw_is_finite:
            return "evaluator raw metric must be null or a finite real number"
    if not isinstance(result.detail, str):
        return "evaluator detail must be text"
    return None


def run_loop(
    env: Environment,
    rounds: int,
    seed: int = 0,
    log=print,
    *,
    proposer: CandidateProposer | None = None,
    archive: Archive | None = None,
    min_improvement: float = 0.01,
    retain_novel: bool = True,
    max_candidate_bytes: int = DEFAULT_MAX_CANDIDATE_BYTES,
) -> tuple[Archive, list[Trajectory]]:
    if type(rounds) is not int or rounds < 0:
        raise ValueError("rounds must be a non-negative integer")
    if isinstance(min_improvement, bool) or not isinstance(min_improvement, numbers.Real):
        raise ValueError("min_improvement must be a non-negative finite real number")
    try:
        finite_minimum = math.isfinite(float(min_improvement))
    except (OverflowError, TypeError, ValueError):
        finite_minimum = False
    if not finite_minimum or min_improvement < 0:
        raise ValueError("min_improvement must be a non-negative finite real number")
    if type(retain_novel) is not bool:
        raise ValueError("retain_novel must be a bool")
    if type(max_candidate_bytes) is not int or max_candidate_bytes <= 0:
        raise ValueError("max_candidate_bytes must be a positive integer")
    rng = random.Random(seed)
    proposer = Proposer() if proposer is None else proposer
    archive = Archive() if archive is None else archive
    archive.validate()

    # Seed the archive with the environment's starting solution.
    if not archive.nodes:
        start_score = env.score(env.starting_solution)
        seed_error = _validate_score_result(start_score)
        if seed_error is not None or not start_score.correct:
            raise RuntimeError("environment produced an invalid seed evaluation")
        archive.seed(env.starting_solution, start_score.reward, start_score.correct, start_score.detail)
        log(f"[seed] {env.name}: reward={start_score.reward:.3f}  {start_score.detail}")

    trajectories: list[Trajectory] = []

    for i in range(1, rounds + 1):
        parent: Node = archive.select_parent(rng)
        archive.record_attempt(parent)
        try:
            candidate = proposer.propose(env.task_prompt, parent.source)
        except Exception as e:                      # API/parse failure: skip the round
            detail = _safe_error_detail(e)
            log(f"[{i:>3}] proposer error from node {parent.node_id}: {detail}")
            trajectories.append(
                Trajectory(i, parent.node_id, env.task_prompt, None, None, None,
                           False, "proposer_error", detail)
            )
            continue

        if not isinstance(candidate, str):
            detail = "proposer returned a non-text candidate"
            trajectories.append(
                Trajectory(i, parent.node_id, env.task_prompt, None, None, None,
                           False, "invalid_candidate", detail)
            )
            log(f"[{i:>3}] parent#{parent.node_id} -> invalid candidate: {detail}")
            continue
        try:
            candidate_size = len(candidate.encode("utf-8"))
        except UnicodeError:
            detail = "candidate is not valid UTF-8 text"
            trajectories.append(
                Trajectory(i, parent.node_id, env.task_prompt, None, None, None,
                           False, "invalid_candidate", detail)
            )
            log(f"[{i:>3}] parent#{parent.node_id} -> invalid candidate: {detail}")
            continue
        if candidate_size > max_candidate_bytes:
            detail = (
                f"candidate exceeds byte limit ({candidate_size}>{max_candidate_bytes})"
            )
            trajectories.append(
                Trajectory(i, parent.node_id, env.task_prompt, None, None, None,
                           False, "invalid_candidate", detail)
            )
            log(f"[{i:>3}] parent#{parent.node_id} -> invalid candidate: {detail}")
            continue

        if archive.contains_source(candidate):
            trajectories.append(
                Trajectory(i, parent.node_id, env.task_prompt, candidate, None, None,
                           False, "duplicate", "candidate source already archived")
            )
            log(f"[{i:>3}] parent#{parent.node_id} -> duplicate")
            continue

        try:
            result = env.score(candidate)
        except Exception as error:
            detail = _safe_error_detail(error)
            trajectories.append(
                Trajectory(i, parent.node_id, env.task_prompt, candidate, None, False,
                           False, "evaluator_error", detail)
            )
            log(f"[{i:>3}] evaluator error from node {parent.node_id}: {detail}")
            continue

        result_error = _validate_score_result(result)
        if result_error is not None:
            trajectories.append(
                Trajectory(i, parent.node_id, env.task_prompt, candidate, None, None,
                           False, "evaluator_error", result_error)
            )
            log(f"[{i:>3}] evaluator error from node {parent.node_id}: {result_error}")
            continue

        valid = result.correct
        improved = valid and result.reward >= parent.reward + min_improvement
        novel = valid and result.reward > 0 and retain_novel and _novel(candidate, archive)
        accepted = improved or novel

        trajectories.append(
            Trajectory(i, parent.node_id, env.task_prompt, candidate, result.reward,
                       result.correct, accepted, "accepted" if accepted else "rejected",
                       result.detail)
        )

        if accepted:
            archive.add(parent, candidate, result.reward, result.correct, result.detail)
            tag = "improve" if improved else "novel  "
            log(f"[{i:>3}] parent#{parent.node_id}(r={parent.reward:.3f}) -> {tag} "
                f"r={result.reward:.3f}  best={archive.best().reward:.3f}  {result.detail}")
        else:
            log(f"[{i:>3}] parent#{parent.node_id}(r={parent.reward:.3f}) -> reject "
                f"r={result.reward:.3f}  {result.detail}")

    return archive, trajectories
