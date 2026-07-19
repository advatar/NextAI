"""Bounded archive and promotion gate for improving the improver.

The tournament measures an improver; this module decides whether that measured
result is allowed to become the next outer-loop parent.  The candidate itself
is never trusted to report its own productivity.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .metaproductivity import MIN_EVIDENCE_PAIRS, TournamentReport


@dataclass(frozen=True, slots=True)
class ImproverEntry:
    digest: str
    name: str
    parent_digest: str | None
    verdict: str
    evidence_class: str
    mean_delta: float | None
    valid_pairs: int
    generation: int


class ImproverArchive:
    """Content-addressed outer-loop archive with explicit promotion policy."""

    def __init__(self) -> None:
        self._entries: dict[str, ImproverEntry] = {}
        self._objects: dict[str, Any] = {}

    @staticmethod
    def digest(improver: Any) -> str:
        name = getattr(improver, "name", None)
        if not isinstance(name, str) or not name.strip():
            raise TypeError("improver must expose a non-empty name")
        try:
            payload = json.dumps(vars(improver), sort_keys=True, default=str)
        except TypeError as error:
            raise TypeError("improver state must be serializable") from error
        return hashlib.sha256(f"{name}\n{payload}".encode()).hexdigest()

    def seed(self, improver: Any) -> ImproverEntry:
        digest = self.digest(improver)
        entry = ImproverEntry(digest, improver.name, None, "seed", "external", None, 0, 0)
        self._entries[digest] = entry
        self._objects[digest] = improver
        return entry

    def consider(
        self,
        improver: Any,
        report: TournamentReport,
        *,
        parent_digest: str,
        allow_fixture: bool = False,
    ) -> ImproverEntry:
        if parent_digest not in self._entries:
            raise KeyError("parent improver is not in archive")
        if report.evidence_class == "fixture" and not allow_fixture:
            verdict = "rejected_fixture_evidence"
        elif report.verdict != "passes_threshold":
            verdict = f"rejected_{report.verdict}"
        elif report.valid_pairs < MIN_EVIDENCE_PAIRS:
            verdict = "rejected_insufficient_pairs"
        else:
            verdict = "promoted"
        digest = self.digest(improver)
        parent = self._entries[parent_digest]
        entry = ImproverEntry(
            digest, improver.name, parent_digest, verdict, report.evidence_class,
            report.mean_delta, report.valid_pairs, parent.generation + 1,
        )
        self._entries[digest] = entry
        self._objects[digest] = improver
        return entry

    def get(self, digest: str) -> Any:
        return self._objects[digest]

    def entries(self) -> tuple[ImproverEntry, ...]:
        return tuple(self._entries.values())

    def promoted(self) -> tuple[ImproverEntry, ...]:
        return tuple(entry for entry in self._entries.values() if entry.verdict in {"seed", "promoted"})


__all__ = ["ImproverArchive", "ImproverEntry"]
