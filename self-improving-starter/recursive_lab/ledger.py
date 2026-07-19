"""Tamper-evident, incrementally durable lineage storage.

Each JSONL row contains an event payload and a SHA-256 hash chaining it to the
previous row.  Internal edits, deletions, insertions, and reordering are detected
when the ledger is loaded.  A tail truncation is indistinguishable from an older
valid ledger without external state, so callers that need rollback detection
must retain the last trusted ``head_hash`` and pass it as ``expected_head``.

Rows are appended through an ``O_APPEND`` descriptor while holding a process and
(where available) advisory file lock, then ``fsync`` is called before success is
reported.  A crash can still leave a partial final row; verification detects and
rejects that state rather than silently discarding it.
"""

from __future__ import annotations

import contextlib
import os
import re
import stat
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping

from .artifacts import (
    ArtifactRecord,
    ArtifactValidationError,
    canonical_json,
    sha256_digest,
    strict_json_loads,
)

try:  # POSIX production path; the process lock remains as a portable fallback.
    import fcntl
except ImportError:  # pragma: no cover - exercised only on non-POSIX platforms
    fcntl = None  # type: ignore[assignment]


LEDGER_SCHEMA_VERSION = 1
GENESIS_HASH = "0" * 64
MAX_EVENT_BYTES = 1_048_576
MAX_ATTEMPT_ID_CHARS = 128
MAX_REASON_CODE_CHARS = 96

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_ATTEMPT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_REASON_CODE_RE = re.compile(r"[a-z][a-z0-9_.-]{0,95}\Z")
_PROCESS_LOCK = threading.RLock()


class LedgerError(RuntimeError):
    """Base class for lineage-ledger failures."""


class LedgerValidationError(LedgerError, ValueError):
    """Raised when a caller supplies an invalid event or anchor."""


class LedgerIntegrityError(LedgerError):
    """Raised when persisted bytes do not form the expected hash chain."""


def _validate_digest(value: str | None, *, field_name: str, optional: bool = False) -> None:
    if optional and value is None:
        return
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise LedgerValidationError(
            f"{field_name} must be a lowercase 64-character SHA-256 digest"
        )


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str], *, label: str
) -> None:
    if not isinstance(value, Mapping):
        raise LedgerValidationError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        raise LedgerValidationError(
            f"{label} has invalid fields "
            f"(missing={sorted(expected - actual)}, extra={sorted(actual - expected)})"
        )


@dataclass(frozen=True, slots=True)
class AttemptEvent:
    """A uniform event shape for both accepted and rejected proposals.

    Rejections at the schema boundary may not have an ``artifact_record``; in
    that case ``candidate_digest`` is the SHA-256 of the rejected raw proposal.
    Valid evaluated candidates include the record for either outcome.  Raw unsafe
    proposal text is deliberately not persisted.
    """

    attempt_id: str
    outcome: Literal["accepted", "rejected"]
    candidate_digest: str
    parent_id: str | None
    generation: int
    reason_code: str
    artifact_record: ArtifactRecord | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.attempt_id, str)
            or _ATTEMPT_ID_RE.fullmatch(self.attempt_id) is None
        ):
            raise LedgerValidationError(
                "attempt_id must use 1-128 letters, digits, '.', '_', ':', or '-'"
            )
        if not isinstance(self.outcome, str) or self.outcome not in {"accepted", "rejected"}:
            raise LedgerValidationError("outcome must be 'accepted' or 'rejected'")
        _validate_digest(self.candidate_digest, field_name="candidate_digest")
        _validate_digest(self.parent_id, field_name="parent_id", optional=True)
        if type(self.generation) is not int or self.generation < 0:
            raise LedgerValidationError("generation must be a non-negative integer")
        if self.generation == 0 and self.parent_id is not None:
            raise LedgerValidationError("generation zero cannot have a parent_id")
        if self.generation > 0 and self.parent_id is None:
            raise LedgerValidationError("non-root generations require a parent_id")
        if (
            not isinstance(self.reason_code, str)
            or _REASON_CODE_RE.fullmatch(self.reason_code) is None
        ):
            raise LedgerValidationError(
                f"reason_code must use 1-{MAX_REASON_CODE_CHARS} lowercase code characters"
            )
        if self.outcome == "accepted" and self.artifact_record is None:
            raise LedgerValidationError("accepted attempts require an artifact_record")
        if self.artifact_record is not None:
            if not isinstance(self.artifact_record, ArtifactRecord):
                raise LedgerValidationError("artifact_record must be an ArtifactRecord")
            if self.candidate_digest != self.artifact_record.artifact_id:
                raise LedgerValidationError(
                    "candidate_digest must match artifact_record.artifact_id"
                )
            if self.parent_id != self.artifact_record.parent_id:
                raise LedgerValidationError(
                    "event parent_id must match artifact_record.parent_id"
                )
            if self.generation != self.artifact_record.generation:
                raise LedgerValidationError(
                    "event generation must match artifact_record.generation"
                )

    @classmethod
    def accepted(
        cls,
        *,
        attempt_id: str,
        artifact_record: ArtifactRecord,
        reason_code: str = "accepted",
    ) -> "AttemptEvent":
        return cls(
            attempt_id=attempt_id,
            outcome="accepted",
            candidate_digest=artifact_record.artifact_id,
            parent_id=artifact_record.parent_id,
            generation=artifact_record.generation,
            reason_code=reason_code,
            artifact_record=artifact_record,
        )

    @classmethod
    def rejected(
        cls,
        *,
        attempt_id: str,
        candidate_digest: str,
        parent_id: str | None,
        generation: int,
        reason_code: str,
        artifact_record: ArtifactRecord | None = None,
    ) -> "AttemptEvent":
        return cls(
            attempt_id=attempt_id,
            outcome="rejected",
            candidate_digest=candidate_digest,
            parent_id=parent_id,
            generation=generation,
            reason_code=reason_code,
            artifact_record=artifact_record,
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "artifact_record": (
                None if self.artifact_record is None else self.artifact_record.to_payload()
            ),
            "attempt_id": self.attempt_id,
            "candidate_digest": self.candidate_digest,
            "generation": self.generation,
            "kind": "attempt",
            "outcome": self.outcome,
            "parent_id": self.parent_id,
            "reason_code": self.reason_code,
            "schema_version": LEDGER_SCHEMA_VERSION,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "AttemptEvent":
        expected = {
            "artifact_record",
            "attempt_id",
            "candidate_digest",
            "generation",
            "kind",
            "outcome",
            "parent_id",
            "reason_code",
            "schema_version",
        }
        _require_exact_keys(payload, expected, label="attempt")
        if payload["kind"] != "attempt":
            raise LedgerValidationError("invalid attempt kind")
        if (
            type(payload["schema_version"]) is not int
            or payload["schema_version"] != LEDGER_SCHEMA_VERSION
        ):
            raise LedgerValidationError("unsupported attempt schema_version")
        record_payload = payload["artifact_record"]
        record: ArtifactRecord | None
        if record_payload is None:
            record = None
        elif isinstance(record_payload, Mapping):
            try:
                record = ArtifactRecord.from_payload(record_payload)
            except ArtifactValidationError as exc:
                raise LedgerValidationError(f"invalid artifact_record: {exc}") from exc
        else:
            raise LedgerValidationError("artifact_record must be an object or null")
        return cls(
            attempt_id=payload["attempt_id"],
            outcome=payload["outcome"],
            candidate_digest=payload["candidate_digest"],
            parent_id=payload["parent_id"],
            generation=payload["generation"],
            reason_code=payload["reason_code"],
            artifact_record=record,
        )


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    sequence: int
    previous_hash: str
    current_hash: str
    payload_json: str

    @property
    def payload(self) -> dict[str, Any]:
        """Return a fresh decoded payload so the frozen entry stays deeply immutable."""

        value = strict_json_loads(self.payload_json)
        if not isinstance(value, dict):  # Constructed entries always satisfy this.
            raise LedgerIntegrityError("ledger payload is not an object")
        return value

    def as_attempt(self) -> AttemptEvent:
        """Decode and validate this entry as an accepted/rejected attempt event."""

        return AttemptEvent.from_payload(self.payload)


@dataclass(frozen=True, slots=True)
class LedgerVerification:
    entry_count: int
    head_hash: str


@contextlib.contextmanager
def _advisory_lock(fd: int, *, exclusive: bool):
    if fcntl is not None:
        operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        fcntl.flock(fd, operation)
    try:
        yield
    finally:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_UN)


def _open_flags(*, write: bool) -> int:
    flags = os.O_CLOEXEC if hasattr(os, "O_CLOEXEC") else 0
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if write:
        return flags | os.O_RDWR | os.O_CREAT | os.O_APPEND
    return flags | os.O_RDONLY


def _ensure_regular_file(fd: int) -> None:
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        raise LedgerValidationError("ledger path must refer to a regular file")


def _canonical_event_payload(event: AttemptEvent | Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    raw_payload: Any = event.to_payload() if isinstance(event, AttemptEvent) else event
    if not isinstance(raw_payload, Mapping):
        raise LedgerValidationError("event payload must be an object")
    try:
        encoded = canonical_json(raw_payload)
    except ArtifactValidationError as exc:
        raise LedgerValidationError(f"event is not canonical JSON: {exc}") from exc
    if len(encoded.encode("utf-8")) > MAX_EVENT_BYTES:
        raise LedgerValidationError(
            f"event exceeds the {MAX_EVENT_BYTES}-byte ledger limit"
        )
    try:
        decoded = strict_json_loads(encoded)
    except ArtifactValidationError as exc:  # Defensive; canonical_json produced it.
        raise LedgerValidationError(f"event cannot be decoded: {exc}") from exc
    if not isinstance(decoded, dict):
        raise LedgerValidationError("event payload must encode a JSON object")
    return decoded, encoded


def _parse_ledger_bytes(data: bytes) -> tuple[LedgerEntry, ...]:
    if not data:
        return ()
    if not data.endswith(b"\n"):
        raise LedgerIntegrityError("ledger has a truncated final row")

    entries: list[LedgerEntry] = []
    expected_previous = GENESIS_HASH
    rows = data[:-1].split(b"\n")
    for expected_sequence, raw_row in enumerate(rows):
        if not raw_row:
            raise LedgerIntegrityError(f"ledger row {expected_sequence} is empty")
        try:
            row_text = raw_row.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise LedgerIntegrityError(
                f"ledger row {expected_sequence} is not UTF-8"
            ) from exc
        try:
            envelope = strict_json_loads(row_text)
        except ArtifactValidationError as exc:
            raise LedgerIntegrityError(
                f"ledger row {expected_sequence} is invalid JSON: {exc}"
            ) from exc
        if not isinstance(envelope, Mapping):
            raise LedgerIntegrityError(
                f"ledger row {expected_sequence} must be an object"
            )
        expected_keys = {"current_hash", "payload", "previous_hash", "sequence"}
        if set(envelope) != expected_keys:
            raise LedgerIntegrityError(
                f"ledger row {expected_sequence} has invalid envelope fields"
            )
        if canonical_json(envelope) != row_text:
            raise LedgerIntegrityError(
                f"ledger row {expected_sequence} is not canonically encoded"
            )

        sequence = envelope["sequence"]
        previous_hash = envelope["previous_hash"]
        current_hash = envelope["current_hash"]
        payload = envelope["payload"]
        if type(sequence) is not int or sequence != expected_sequence:
            raise LedgerIntegrityError(
                f"ledger sequence mismatch at row {expected_sequence}"
            )
        if not isinstance(previous_hash, str) or _SHA256_RE.fullmatch(previous_hash) is None:
            raise LedgerIntegrityError(
                f"ledger row {expected_sequence} has invalid previous_hash"
            )
        if previous_hash != expected_previous:
            raise LedgerIntegrityError(
                f"ledger chain break at row {expected_sequence}"
            )
        if not isinstance(current_hash, str) or _SHA256_RE.fullmatch(current_hash) is None:
            raise LedgerIntegrityError(
                f"ledger row {expected_sequence} has invalid current_hash"
            )
        if not isinstance(payload, Mapping):
            raise LedgerIntegrityError(
                f"ledger row {expected_sequence} payload must be an object"
            )
        core = {
            "payload": payload,
            "previous_hash": previous_hash,
            "sequence": sequence,
        }
        calculated = sha256_digest(canonical_json(core))
        if current_hash != calculated:
            raise LedgerIntegrityError(
                f"ledger hash mismatch at row {expected_sequence}"
            )
        payload_json = canonical_json(payload)
        if len(payload_json.encode("utf-8")) > MAX_EVENT_BYTES:
            raise LedgerIntegrityError(
                f"ledger row {expected_sequence} payload exceeds its size limit"
            )
        entries.append(
            LedgerEntry(
                sequence=sequence,
                previous_hash=previous_hash,
                current_hash=current_hash,
                payload_json=payload_json,
            )
        )
        expected_previous = current_hash
    return tuple(entries)


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:  # pragma: no cover - defensive OS failure path
            raise OSError("ledger append made no progress")
        view = view[written:]


def _fsync_directory(path: Path) -> None:
    if not hasattr(os, "O_DIRECTORY"):
        return
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:  # Some filesystems do not permit directory fsync.
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class LineageLedger:
    """Append-only JSONL ledger with hash-chain and external-head verification."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)

    def _read_unlocked(self) -> tuple[LedgerEntry, ...]:
        if not self.path.exists():
            return ()
        try:
            fd = os.open(self.path, _open_flags(write=False))
        except OSError as exc:
            raise LedgerIntegrityError(f"cannot open ledger: {exc}") from exc
        try:
            _ensure_regular_file(fd)
            with _advisory_lock(fd, exclusive=False):
                with os.fdopen(fd, "rb", closefd=False) as handle:
                    data = handle.read()
        finally:
            os.close(fd)
        return _parse_ledger_bytes(data)

    @staticmethod
    def _check_expected_head(
        entries: tuple[LedgerEntry, ...], expected_head: str | None
    ) -> str:
        actual = entries[-1].current_hash if entries else GENESIS_HASH
        if expected_head is not None:
            _validate_digest(expected_head, field_name="expected_head")
            if actual != expected_head:
                raise LedgerIntegrityError(
                    f"ledger head mismatch: expected {expected_head}, found {actual}"
                )
        return actual

    def load(self, *, expected_head: str | None = None) -> tuple[LedgerEntry, ...]:
        """Load and verify every row, optionally checking a trusted head anchor."""

        with _PROCESS_LOCK:
            entries = self._read_unlocked()
            self._check_expected_head(entries, expected_head)
            return entries

    def verify(self, *, expected_head: str | None = None) -> LedgerVerification:
        entries = self.load(expected_head=expected_head)
        head = entries[-1].current_hash if entries else GENESIS_HASH
        return LedgerVerification(entry_count=len(entries), head_hash=head)

    @property
    def head_hash(self) -> str:
        return self.verify().head_hash

    def append(
        self,
        event: AttemptEvent | Mapping[str, Any],
        *,
        expected_head: str | None = None,
    ) -> LedgerEntry:
        """Durably append one event after verifying the existing ledger.

        ``expected_head`` provides compare-and-append semantics and prevents a
        caller from extending an unexpected or rolled-back lineage.
        """

        payload, payload_json = _canonical_event_payload(event)
        if expected_head is not None:
            _validate_digest(expected_head, field_name="expected_head")

        self.path.parent.mkdir(parents=True, exist_ok=True)
        existed = self.path.exists()
        with _PROCESS_LOCK:
            try:
                fd = os.open(self.path, _open_flags(write=True), 0o600)
            except OSError as exc:
                raise LedgerError(f"cannot open ledger for append: {exc}") from exc
            try:
                _ensure_regular_file(fd)
                with _advisory_lock(fd, exclusive=True):
                    os.lseek(fd, 0, os.SEEK_SET)
                    chunks: list[bytes] = []
                    while True:
                        chunk = os.read(fd, 1 << 20)
                        if not chunk:
                            break
                        chunks.append(chunk)
                    entries = _parse_ledger_bytes(b"".join(chunks))
                    previous_hash = self._check_expected_head(entries, expected_head)
                    sequence = len(entries)
                    core = {
                        "payload": payload,
                        "previous_hash": previous_hash,
                        "sequence": sequence,
                    }
                    current_hash = sha256_digest(canonical_json(core))
                    envelope = {**core, "current_hash": current_hash}
                    row = (canonical_json(envelope) + "\n").encode("utf-8")
                    _write_all(fd, row)
                    os.fsync(fd)
            finally:
                os.close(fd)

        if not existed:
            _fsync_directory(self.path.parent)
        return LedgerEntry(
            sequence=sequence,
            previous_hash=previous_hash,
            current_hash=current_hash,
            payload_json=payload_json,
        )
