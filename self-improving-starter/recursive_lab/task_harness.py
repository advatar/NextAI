"""Immutable execution-grounded task suite for live experiments."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from environments import REGISTRY
from .artifacts import sha256_digest


@dataclass(frozen=True, slots=True)
class TaskResult:
    task_id: str
    reward: float
    correct: bool
    detail: str


class ExecutableTaskSuite:
    """Runs operator-selected environments; tasks cannot be edited by a candidate."""

    def __init__(self, task_ids: tuple[str, ...] = ("optimize_function",)) -> None:
        if not task_ids or any(task_id not in REGISTRY for task_id in task_ids):
            raise ValueError("task_ids must name registered environments")
        self.task_ids = tuple(task_ids)
        self._envs = {task_id: REGISTRY[task_id]() for task_id in self.task_ids}
        manifests = []
        for task_id in self.task_ids:
            env = self._envs[task_id]
            manifests.append({"id": task_id, "prompt": env.task_prompt, "starting": env.starting_solution})
        self.manifest = tuple(manifests)
        self.manifest_digest = sha256_digest(json.dumps(manifests, sort_keys=True, separators=(",", ":")))

    def evaluate(self, solution_source: str, *, split: str = "private_selection") -> tuple[TaskResult, ...]:
        if not isinstance(solution_source, str) or not solution_source.strip():
            raise ValueError("solution_source must be non-empty text")
        return tuple(
            TaskResult(task_id, result.reward, result.correct, result.detail)
            for task_id in self.task_ids
            for result in (self._envs[task_id].score(solution_source),)
        )

    def baseline(self) -> tuple[TaskResult, ...]:
        return tuple(
            TaskResult(task_id, result.reward, result.correct, result.detail)
            for task_id in self.task_ids
            for result in (self._envs[task_id].score(self._envs[task_id].starting_solution),)
        )


__all__ = ["ExecutableTaskSuite", "TaskResult"]
