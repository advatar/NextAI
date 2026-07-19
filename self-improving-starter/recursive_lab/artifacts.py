"""Immutable, content-addressed artifacts for the recursive-improvement lab.

The mutable agent is allowed to propose a deliberately small strategy object.  It
is *not* allowed to encode changes to the governor, evaluator, permissions,
networking, shell execution, or dependencies in that object.  This module is a
schema boundary, so it intentionally rejects ambiguous input rather than trying
to infer whether a suspicious instruction was benign.

Only Python's standard library is used.  Artifact identity is the SHA-256 digest
of a deterministic JSON representation of the strategy; lineage metadata is
kept separately in :class:`ArtifactRecord` so that the same strategy has the same
identity wherever it appears in the lineage graph.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = 1
MAX_SYSTEM_INSTRUCTION_CHARS = 4_096
MAX_PLANNING_STEPS = 24
MAX_PLANNING_STEP_CHARS = 1_024
MAX_TOTAL_PLANNING_CHARS = 12_288
MAX_ATTEMPTS = 16
MAX_REFLECTION_CHARS = 2_048
MAX_SEED = (1 << 63) - 1

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")

# These are intentionally conservative.  A strategy has no legitimate need to
# discuss the immutable governance plane or acquire additional capabilities.  In
# particular, even a negated phrase such as "do not read hidden tests" is
# rejected: interpreting natural-language negation at this trust boundary would
# make the validator vulnerable to prompt-injection word games.
_UNSAFE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "evaluator",
        re.compile(
            r"\b(?:evaluator|grader|scorer|verifier|reward[ _-]?function|"
            r"acceptance[ _-]?gate|governance[ _-]?plane|governor)\b|"
            r"\b(?:modify|edit|change|patch|replace|delete|disable|bypass|inspect|"
            r"read|reveal|leak|copy|infer)\s+(?:the\s+)?(?:evaluation|scoring|"
            r"benchmark|test)[a-z _-]*\b"
        ),
    ),
    (
        "hidden-test",
        re.compile(
            r"\b(?:hidden|private|held[ _-]?out|secret)\s+(?:test|tests|"
            r"evaluation|evaluations|benchmark|benchmarks)\b"
        ),
    ),
    (
        "permission",
        re.compile(
            r"\b(?:permission|permissions|privilege|privileges|credential|"
            r"credentials|secret|secrets|api[ _-]?key|access[ _-]?token|sudo|"
            r"chmod|chown|setuid|sandbox[ _-]?escape|environment[ _-]?variable|"
            r"environment[ _-]?variables|escalate[ _-]?access)\b"
        ),
    ),
    (
        "network",
        re.compile(
            r"(?:https?://|\b(?:network|internet|socket|sockets|curl|wget|ssh|"
            r"scp|webhook|dns|upload|download|outbound|exfiltrate|"
            r"external[ _-]?endpoint|remote[ _-]?service)\b)"
        ),
    ),
    (
        "shell",
        re.compile(
            r"(?:\$\(|\b(?:shell|subprocess|os\.system|popen|powershell|bash|"
            r"zsh|cmd\.exe|/bin/(?:sh|bash))\b|\b(?:eval|exec)\s*\()"
        ),
    ),
    (
        "dependency",
        re.compile(
            r"\b(?:dependency|dependencies|package[ _-]?manager|pip|pipx|"
            r"conda|poetry|uv|npm|pnpm|yarn|brew|apt|requirements\.txt|"
            r"pyproject\.toml|third[ _-]?party)\b|"
            r"\b(?:install|add|upgrade|replace)\s+(?:a\s+|the\s+)?"
            r"(?:package|library|module)\b"
        ),
    ),
    (
        "prompt-injection",
        re.compile(
            r"\b(?:ignore|override|bypass|disable)\s+(?:the\s+)?(?:previous|"
            r"prior|system|safety|policy|policies|restriction|restrictions|"
            r"instruction|instructions)\b"
        ),
    ),
)


class ArtifactValidationError(ValueError):
    """Raised when an artifact is not safe and canonical enough to persist."""


def canonical_json(value: Any) -> str:
    """Return deterministic JSON suitable for hashing and durable storage.

    ``allow_nan=False`` is important: NaN and infinities are not JSON and would
    otherwise create surprising identities across runtimes.
    """

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ArtifactValidationError(f"value is not canonical JSON: {exc}") from exc


def sha256_digest(data: str | bytes) -> str:
    """Return a lowercase SHA-256 hex digest for UTF-8 text or raw bytes."""

    encoded = data.encode("utf-8") if isinstance(data, str) else data
    if not isinstance(encoded, bytes):
        raise TypeError("sha256_digest expects str or bytes")
    return hashlib.sha256(encoded).hexdigest()


def strict_json_loads(text: str) -> Any:
    """Parse JSON while rejecting duplicate keys and non-finite constants."""

    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ArtifactValidationError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ArtifactValidationError(f"non-finite JSON constant: {value}")

    def parse_float(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ArtifactValidationError(f"non-finite JSON number: {value}")
        return parsed

    if not isinstance(text, str):
        raise ArtifactValidationError("JSON input must be text")
    try:
        return json.loads(
            text,
            object_pairs_hook=object_pairs,
            parse_constant=reject_constant,
            parse_float=parse_float,
        )
    except ArtifactValidationError:
        raise
    except (json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
        raise ArtifactValidationError(f"invalid JSON: {exc}") from exc


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str], *, label: str
) -> None:
    if not isinstance(value, Mapping):
        raise ArtifactValidationError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ArtifactValidationError(
            f"{label} has invalid fields (missing={missing}, extra={extra})"
        )


def _validate_digest(value: str, *, field_name: str, optional: bool = False) -> None:
    if optional and value is None:
        return
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ArtifactValidationError(
            f"{field_name} must be a lowercase 64-character SHA-256 digest"
        )


def _validate_text(
    value: str,
    *,
    field_name: str,
    max_chars: int,
    multiline: bool,
) -> None:
    if not isinstance(value, str):
        raise ArtifactValidationError(f"{field_name} must be text")
    if not value or value.strip() != value:
        raise ArtifactValidationError(
            f"{field_name} must be non-empty with no outer whitespace"
        )
    if len(value) > max_chars:
        raise ArtifactValidationError(
            f"{field_name} exceeds the {max_chars}-character limit"
        )
    if len(value.encode("utf-8")) > max_chars * 4:
        raise ArtifactValidationError(f"{field_name} exceeds its byte limit")
    if unicodedata.normalize("NFC", value) != value:
        raise ArtifactValidationError(f"{field_name} must use NFC Unicode")
    if not multiline and ("\n" in value or "\r" in value):
        raise ArtifactValidationError(f"{field_name} must be one line")
    for character in value:
        if character in "\n\t" and multiline:
            continue
        category = unicodedata.category(character)
        if category in {"Cc", "Cf", "Cs", "Co", "Cn"}:
            raise ArtifactValidationError(
                f"{field_name} contains a disallowed control or format character"
            )


def _validate_safe_content(parts: Iterable[str]) -> None:
    # NFKC catches common full-width compatibility spellings used to evade simple
    # pattern matching.  Joining all fields also catches a phrase split across
    # adjacent planning steps.
    searchable = unicodedata.normalize("NFKC", " \n ".join(parts)).casefold()
    for category, pattern in _UNSAFE_PATTERNS:
        if pattern.search(searchable):
            raise ArtifactValidationError(
                f"strategy contains prohibited {category} content"
            )


@dataclass(frozen=True, slots=True)
class StrategyArtifact:
    """The complete, intentionally narrow mutable strategy surface."""

    system_instruction: str
    planning_steps: tuple[str, ...]
    max_attempts: int
    reflection: str | None = None

    def __post_init__(self) -> None:
        _validate_text(
            self.system_instruction,
            field_name="system_instruction",
            max_chars=MAX_SYSTEM_INSTRUCTION_CHARS,
            multiline=True,
        )
        if type(self.planning_steps) is not tuple:
            raise ArtifactValidationError("planning_steps must be an immutable tuple")
        if not self.planning_steps or len(self.planning_steps) > MAX_PLANNING_STEPS:
            raise ArtifactValidationError(
                f"planning_steps must contain 1 to {MAX_PLANNING_STEPS} steps"
            )
        for index, step in enumerate(self.planning_steps):
            _validate_text(
                step,
                field_name=f"planning_steps[{index}]",
                max_chars=MAX_PLANNING_STEP_CHARS,
                multiline=False,
            )
        if sum(len(step) for step in self.planning_steps) > MAX_TOTAL_PLANNING_CHARS:
            raise ArtifactValidationError("planning_steps exceed the total size limit")
        if type(self.max_attempts) is not int or not 1 <= self.max_attempts <= MAX_ATTEMPTS:
            raise ArtifactValidationError(
                f"max_attempts must be an integer from 1 to {MAX_ATTEMPTS}"
            )
        if self.reflection is not None:
            _validate_text(
                self.reflection,
                field_name="reflection",
                max_chars=MAX_REFLECTION_CHARS,
                multiline=True,
            )

        content = [self.system_instruction, *self.planning_steps]
        if self.reflection is not None:
            content.append(self.reflection)
        _validate_safe_content(content)

    @classmethod
    def create(
        cls,
        *,
        system_instruction: str,
        planning_steps: Iterable[str],
        max_attempts: int,
        reflection: str | None = None,
    ) -> "StrategyArtifact":
        """Construct an artifact while safely freezing an iterable of steps."""

        return cls(
            system_instruction=system_instruction,
            planning_steps=tuple(planning_steps),
            max_attempts=max_attempts,
            reflection=reflection,
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": "strategy",
            "max_attempts": self.max_attempts,
            "planning_steps": list(self.planning_steps),
            "reflection": self.reflection,
            "schema_version": SCHEMA_VERSION,
            "system_instruction": self.system_instruction,
        }

    def to_canonical_json(self) -> str:
        return canonical_json(self.to_payload())

    @property
    def artifact_id(self) -> str:
        return sha256_digest(self.to_canonical_json())

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "StrategyArtifact":
        expected = {
            "kind",
            "max_attempts",
            "planning_steps",
            "reflection",
            "schema_version",
            "system_instruction",
        }
        _require_exact_keys(payload, expected, label="strategy")
        if payload["kind"] != "strategy":
            raise ArtifactValidationError("invalid strategy kind")
        if (
            type(payload["schema_version"]) is not int
            or payload["schema_version"] != SCHEMA_VERSION
        ):
            raise ArtifactValidationError("unsupported strategy schema_version")
        steps = payload["planning_steps"]
        if not isinstance(steps, list):
            raise ArtifactValidationError("planning_steps JSON value must be an array")
        return cls.create(
            system_instruction=payload["system_instruction"],
            planning_steps=steps,
            max_attempts=payload["max_attempts"],
            reflection=payload["reflection"],
        )

    @classmethod
    def from_json(cls, text: str) -> "StrategyArtifact":
        payload = strict_json_loads(text)
        if not isinstance(payload, Mapping):
            raise ArtifactValidationError("strategy JSON must be an object")
        return cls.from_payload(payload)


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    """A strategy plus immutable lineage and proposal-reproducibility metadata."""

    artifact: StrategyArtifact
    parent_id: str | None
    generation: int
    proposer_digest: str
    seed: int

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, StrategyArtifact):
            raise ArtifactValidationError("artifact must be a StrategyArtifact")
        _validate_digest(self.parent_id, field_name="parent_id", optional=True)
        if type(self.generation) is not int or self.generation < 0:
            raise ArtifactValidationError("generation must be a non-negative integer")
        if self.generation == 0 and self.parent_id is not None:
            raise ArtifactValidationError("generation zero cannot have a parent_id")
        if self.generation > 0 and self.parent_id is None:
            raise ArtifactValidationError("non-root generations require a parent_id")
        _validate_digest(self.proposer_digest, field_name="proposer_digest")
        if type(self.seed) is not int or not 0 <= self.seed <= MAX_SEED:
            raise ArtifactValidationError(
                f"seed must be an integer from 0 to {MAX_SEED}"
            )

    @property
    def artifact_id(self) -> str:
        return self.artifact.artifact_id

    def to_payload(self) -> dict[str, Any]:
        return {
            "artifact": self.artifact.to_payload(),
            "artifact_id": self.artifact_id,
            "generation": self.generation,
            "kind": "artifact_record",
            "parent_id": self.parent_id,
            "proposer_digest": self.proposer_digest,
            "schema_version": SCHEMA_VERSION,
            "seed": self.seed,
        }

    def to_canonical_json(self) -> str:
        return canonical_json(self.to_payload())

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ArtifactRecord":
        expected = {
            "artifact",
            "artifact_id",
            "generation",
            "kind",
            "parent_id",
            "proposer_digest",
            "schema_version",
            "seed",
        }
        _require_exact_keys(payload, expected, label="artifact_record")
        if payload["kind"] != "artifact_record":
            raise ArtifactValidationError("invalid artifact_record kind")
        if (
            type(payload["schema_version"]) is not int
            or payload["schema_version"] != SCHEMA_VERSION
        ):
            raise ArtifactValidationError("unsupported artifact_record schema_version")
        artifact_payload = payload["artifact"]
        if not isinstance(artifact_payload, Mapping):
            raise ArtifactValidationError("artifact_record.artifact must be an object")
        artifact = StrategyArtifact.from_payload(artifact_payload)
        record = cls(
            artifact=artifact,
            parent_id=payload["parent_id"],
            generation=payload["generation"],
            proposer_digest=payload["proposer_digest"],
            seed=payload["seed"],
        )
        _validate_digest(payload["artifact_id"], field_name="artifact_id")
        if payload["artifact_id"] != record.artifact_id:
            raise ArtifactValidationError("artifact_id does not match artifact contents")
        return record

    @classmethod
    def from_json(cls, text: str) -> "ArtifactRecord":
        payload = strict_json_loads(text)
        if not isinstance(payload, Mapping):
            raise ArtifactValidationError("artifact_record JSON must be an object")
        return cls.from_payload(payload)
