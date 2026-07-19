"""Immutable experiment identity and durable resume verification.

An experiment manifest anchors every input that must remain fixed across a run.
It is written before the first ledger event and is never updated in place.  On
resume, the caller supplies the configuration it intends to use; every field is
compared with the persisted manifest before work may continue.

The file format is a canonical JSON envelope containing the manifest payload
and the SHA-256 digest of that payload.  Initialization publishes a fully
written and fsynced temporary inode through an atomic hard link, so concurrent
initializers cannot overwrite each other or expose a partial manifest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import threading
from typing import Any, Mapping

from .governance import BudgetLimits


MANIFEST_SCHEMA_VERSION = 1
MAX_MANIFEST_BYTES = 131_072
MAX_RUN_SEED = (1 << 63) - 1

_DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,255}\Z")
_PROCESS_LOCK = threading.RLock()

_PAYLOAD_FIELDS = (
    "schema_version",
    "run_seed",
    "proposer_name",
    "proposer_digest",
    "evaluator_id",
    "evaluator_digest",
    "acceptance_policy",
    "budget_limits",
    "development_task_manifest_digest",
    "private_task_manifest_digest",
    "sealed_task_manifest_digest",
    "mutable_artifact_schema_id",
    "candidate_runtime_policy_digest",
)


class ManifestError(RuntimeError):
    """Base class for manifest failures."""


class ManifestValidationError(ManifestError, ValueError):
    """Raised for malformed in-memory or persisted manifest data."""


class ManifestIntegrityError(ManifestError):
    """Raised when a durable manifest is missing, altered, or non-canonical."""


class ManifestAlreadyExistsError(ManifestError):
    """Raised when new-run initialization targets an existing manifest."""


class ManifestDriftError(ManifestError):
    """Raised when requested resume configuration differs from persisted state."""

    def __init__(
        self,
        *,
        differing_fields: tuple[str, ...],
        differing_paths: tuple[str, ...],
        expected: ExperimentManifest,
        actual: ExperimentManifest,
    ) -> None:
        self.differing_fields = differing_fields
        self.differing_paths = differing_paths
        self.expected = expected
        self.actual = actual
        detail = ", ".join(differing_paths)
        super().__init__(f"experiment manifest drift detected in fields: {detail}")

    def to_dict(self) -> dict[str, object]:
        return {
            "error": type(self).__name__,
            "message": str(self),
            "differing_fields": list(self.differing_fields),
            "differing_paths": list(self.differing_paths),
            "expected_manifest_hash": self.expected.manifest_hash,
            "actual_manifest_hash": self.actual.manifest_hash,
        }


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise ManifestValidationError(f"value is not canonical JSON: {exc}") from exc


def _strict_json_loads(text: str) -> object:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ManifestIntegrityError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ManifestIntegrityError(f"non-finite JSON constant: {value}")

    def parse_float(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ManifestIntegrityError(f"non-finite JSON number: {value}")
        return parsed

    try:
        return json.loads(
            text,
            object_pairs_hook=object_pairs,
            parse_constant=reject_constant,
            parse_float=parse_float,
        )
    except ManifestIntegrityError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError, RecursionError) as exc:
        raise ManifestIntegrityError(f"invalid manifest JSON: {exc}") from exc


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _require_exact_keys(value: object, expected: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ManifestValidationError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        raise ManifestValidationError(
            f"{label} has invalid fields "
            f"(missing={sorted(expected - actual)}, extra={sorted(actual - expected)})"
        )
    return value


def _validate_digest(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        raise ManifestValidationError(
            f"{field_name} must be a lowercase 64-character SHA-256 digest"
        )
    return value


def _validate_identifier(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
        raise ManifestValidationError(
            f"{field_name} must be a 1-256 character stable identifier"
        )
    return value


def _validate_seed(value: object) -> int:
    if type(value) is not int or not 0 <= value <= MAX_RUN_SEED:
        raise ManifestValidationError(
            f"run_seed must be an integer between 0 and {MAX_RUN_SEED}"
        )
    return value


def _validate_json_tree(value: object, *, path: str) -> None:
    """Reject values that JSON would silently coerce or encode ambiguously."""

    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ManifestValidationError(f"{path} contains a non-finite number")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ManifestValidationError(f"{path} object keys must be strings")
            _validate_json_tree(item, path=f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_json_tree(item, path=f"{path}[{index}]")
        return
    raise ManifestValidationError(
        f"{path} contains unsupported value type {type(value).__name__}"
    )


def _freeze_policy_payload(value: object) -> str:
    if not isinstance(value, Mapping):
        raise ManifestValidationError("acceptance_policy must be an object")
    _validate_json_tree(value, path="acceptance_policy")
    canonical = _canonical_json(value)
    if len(canonical.encode("utf-8")) > MAX_MANIFEST_BYTES // 2:
        raise ManifestValidationError("acceptance_policy is too large")
    decoded = _strict_json_loads(canonical)
    if not isinstance(decoded, dict):  # Mapping above makes this unreachable.
        raise ManifestValidationError("acceptance_policy must be an object")
    return canonical


@dataclass(frozen=True, slots=True, init=False)
class ExperimentManifest:
    """Complete immutable identity of one recursive-lab experiment."""

    schema_version: int
    run_seed: int
    proposer_name: str
    proposer_digest: str
    evaluator_id: str
    evaluator_digest: str
    _acceptance_policy_json: str = field(repr=False)
    budget_limits: BudgetLimits
    development_task_manifest_digest: str
    private_task_manifest_digest: str
    sealed_task_manifest_digest: str
    mutable_artifact_schema_id: str
    candidate_runtime_policy_digest: str

    def __init__(
        self,
        *,
        run_seed: int,
        proposer_name: str,
        proposer_digest: str,
        evaluator_id: str,
        evaluator_digest: str,
        acceptance_policy: Mapping[str, object],
        budget_limits: BudgetLimits,
        development_task_manifest_digest: str,
        private_task_manifest_digest: str,
        sealed_task_manifest_digest: str,
        mutable_artifact_schema_id: str,
        candidate_runtime_policy_digest: str,
        schema_version: int = MANIFEST_SCHEMA_VERSION,
    ) -> None:
        if type(schema_version) is not int or schema_version != MANIFEST_SCHEMA_VERSION:
            raise ManifestValidationError(
                f"schema_version must equal supported version {MANIFEST_SCHEMA_VERSION}"
            )
        if not isinstance(budget_limits, BudgetLimits):
            raise ManifestValidationError("budget_limits must be a BudgetLimits instance")

        object.__setattr__(self, "schema_version", schema_version)
        object.__setattr__(self, "run_seed", _validate_seed(run_seed))
        object.__setattr__(
            self,
            "proposer_name",
            _validate_identifier(proposer_name, field_name="proposer_name"),
        )
        object.__setattr__(
            self,
            "proposer_digest",
            _validate_digest(proposer_digest, field_name="proposer_digest"),
        )
        object.__setattr__(
            self,
            "evaluator_id",
            _validate_identifier(evaluator_id, field_name="evaluator_id"),
        )
        object.__setattr__(
            self,
            "evaluator_digest",
            _validate_digest(evaluator_digest, field_name="evaluator_digest"),
        )
        object.__setattr__(
            self,
            "_acceptance_policy_json",
            _freeze_policy_payload(acceptance_policy),
        )
        object.__setattr__(self, "budget_limits", budget_limits)
        for name, value in (
            ("development_task_manifest_digest", development_task_manifest_digest),
            ("private_task_manifest_digest", private_task_manifest_digest),
            ("sealed_task_manifest_digest", sealed_task_manifest_digest),
            ("candidate_runtime_policy_digest", candidate_runtime_policy_digest),
        ):
            object.__setattr__(self, name, _validate_digest(value, field_name=name))
        object.__setattr__(
            self,
            "mutable_artifact_schema_id",
            _validate_identifier(
                mutable_artifact_schema_id,
                field_name="mutable_artifact_schema_id",
            ),
        )

        # Enforce the total persisted-size limit at construction, not after work
        # has begun and the store happens to serialize the object.
        if len(self.canonical_json.encode("utf-8")) > MAX_MANIFEST_BYTES:
            raise ManifestValidationError("experiment manifest is too large")

    @property
    def acceptance_policy(self) -> dict[str, object]:
        """Return a fresh payload, preserving deep immutability of the manifest."""

        decoded = _strict_json_loads(self._acceptance_policy_json)
        if not isinstance(decoded, dict):  # Guaranteed by construction.
            raise ManifestValidationError("stored acceptance_policy is not an object")
        return decoded

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_seed": self.run_seed,
            "proposer_name": self.proposer_name,
            "proposer_digest": self.proposer_digest,
            "evaluator_id": self.evaluator_id,
            "evaluator_digest": self.evaluator_digest,
            "acceptance_policy": self.acceptance_policy,
            "budget_limits": self.budget_limits.to_dict(),
            "development_task_manifest_digest": self.development_task_manifest_digest,
            "private_task_manifest_digest": self.private_task_manifest_digest,
            "sealed_task_manifest_digest": self.sealed_task_manifest_digest,
            "mutable_artifact_schema_id": self.mutable_artifact_schema_id,
            "candidate_runtime_policy_digest": self.candidate_runtime_policy_digest,
        }

    def to_dict(self) -> dict[str, object]:
        return self.to_payload()

    @property
    def canonical_json(self) -> str:
        return _canonical_json(self.to_payload())

    @property
    def manifest_hash(self) -> str:
        return _sha256(self.canonical_json)

    @property
    def digest(self) -> str:
        return self.manifest_hash

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ExperimentManifest:
        checked = _require_exact_keys(payload, set(_PAYLOAD_FIELDS), label="manifest")
        raw_budget = checked["budget_limits"]
        if not isinstance(raw_budget, Mapping):
            raise ManifestValidationError("budget_limits must be an object")
        try:
            budget_limits = BudgetLimits.from_dict(raw_budget)
        except (TypeError, ValueError) as exc:
            raise ManifestValidationError(f"invalid budget_limits: {exc}") from exc

        acceptance_policy = checked["acceptance_policy"]
        if not isinstance(acceptance_policy, Mapping):
            raise ManifestValidationError("acceptance_policy must be an object")
        return cls(
            schema_version=checked["schema_version"],  # type: ignore[arg-type]
            run_seed=checked["run_seed"],  # type: ignore[arg-type]
            proposer_name=checked["proposer_name"],  # type: ignore[arg-type]
            proposer_digest=checked["proposer_digest"],  # type: ignore[arg-type]
            evaluator_id=checked["evaluator_id"],  # type: ignore[arg-type]
            evaluator_digest=checked["evaluator_digest"],  # type: ignore[arg-type]
            acceptance_policy=acceptance_policy,
            budget_limits=budget_limits,
            development_task_manifest_digest=checked[
                "development_task_manifest_digest"
            ],  # type: ignore[arg-type]
            private_task_manifest_digest=checked[
                "private_task_manifest_digest"
            ],  # type: ignore[arg-type]
            sealed_task_manifest_digest=checked[
                "sealed_task_manifest_digest"
            ],  # type: ignore[arg-type]
            mutable_artifact_schema_id=checked[
                "mutable_artifact_schema_id"
            ],  # type: ignore[arg-type]
            candidate_runtime_policy_digest=checked[
                "candidate_runtime_policy_digest"
            ],  # type: ignore[arg-type]
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> ExperimentManifest:
        return cls.from_payload(payload)


def _differing_paths(expected: object, actual: object, *, prefix: str = "") -> tuple[str, ...]:
    if isinstance(expected, Mapping) and isinstance(actual, Mapping):
        paths: list[str] = []
        for key in sorted(set(expected) | set(actual)):
            path = f"{prefix}.{key}" if prefix else str(key)
            if key not in expected or key not in actual:
                paths.append(path)
            else:
                paths.extend(_differing_paths(expected[key], actual[key], prefix=path))
        return tuple(paths)
    if expected != actual:
        return (prefix,)
    return ()


class ManifestStore:
    """Durable, create-once storage for an :class:`ExperimentManifest`."""

    __slots__ = ("path",)

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)

    def _missing_error(self, *, ledger_nonempty: bool) -> ManifestIntegrityError:
        if ledger_nonempty:
            return ManifestIntegrityError(
                "experiment manifest is missing for a nonempty lineage ledger; "
                "refusing to infer or recreate run identity"
            )
        return ManifestIntegrityError("experiment manifest is missing")

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            flags |= os.O_DIRECTORY
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise ManifestIntegrityError(
                f"cannot open manifest directory for fsync: {exc}"
            ) from exc
        try:
            os.fsync(descriptor)
        except OSError as exc:
            raise ManifestIntegrityError(f"cannot fsync manifest directory: {exc}") from exc
        finally:
            os.close(descriptor)

    def _encoded_envelope(self, manifest: ExperimentManifest) -> bytes:
        envelope = {
            "manifest": manifest.to_payload(),
            "manifest_hash": manifest.manifest_hash,
        }
        encoded = (_canonical_json(envelope) + "\n").encode("utf-8")
        if len(encoded) > MAX_MANIFEST_BYTES:
            raise ManifestValidationError("persisted experiment manifest is too large")
        return encoded

    def _atomic_create(self, encoded: bytes) -> None:
        parent = self.path.parent
        parent.mkdir(parents=True, exist_ok=True)
        descriptor, raw_temp_path = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=parent,
        )
        temp_path = Path(raw_temp_path)
        published = False
        try:
            try:
                os.fchmod(descriptor, 0o600)
                with os.fdopen(descriptor, "wb", closefd=True) as handle:
                    descriptor = -1
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
            except OSError as exc:
                raise ManifestIntegrityError(f"cannot write experiment manifest: {exc}") from exc

            try:
                # A hard link atomically publishes the already-fsynced inode and
                # fails with FileExistsError instead of replacing another run.
                os.link(temp_path, self.path)
                published = True
            except FileExistsError as exc:
                raise ManifestAlreadyExistsError(
                    f"experiment manifest already exists: {self.path}"
                ) from exc
            except OSError as exc:
                raise ManifestIntegrityError(
                    f"cannot atomically publish experiment manifest: {exc}"
                ) from exc
            finally:
                try:
                    temp_path.unlink()
                except FileNotFoundError:
                    pass

            self._fsync_directory(parent)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass
            # If directory fsync failed, the file may still be visible but its
            # rename/link durability is uncertain.  Never delete it here: doing
            # so could erase the only durable identity after a partial failure.
            _ = published

    def initialize(
        self,
        manifest: ExperimentManifest,
        *,
        ledger_nonempty: bool = False,
    ) -> ExperimentManifest:
        """Create a new run manifest exactly once and durably publish it."""

        if not isinstance(manifest, ExperimentManifest):
            raise TypeError("manifest must be an ExperimentManifest instance")
        if type(ledger_nonempty) is not bool:
            raise TypeError("ledger_nonempty must be a bool")
        with _PROCESS_LOCK:
            if self.path.exists() or self.path.is_symlink():
                raise ManifestAlreadyExistsError(
                    f"experiment manifest already exists: {self.path}"
                )
            if ledger_nonempty:
                raise self._missing_error(ledger_nonempty=True)
            self._atomic_create(self._encoded_envelope(manifest))
            return manifest

    def _read_bytes(self, *, ledger_nonempty: bool) -> bytes:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(self.path, flags)
        except FileNotFoundError as exc:
            raise self._missing_error(ledger_nonempty=ledger_nonempty) from exc
        except OSError as exc:
            raise ManifestIntegrityError(f"cannot open experiment manifest: {exc}") from exc

        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise ManifestIntegrityError("experiment manifest must be a regular file")
            if metadata.st_size <= 0:
                raise ManifestIntegrityError("experiment manifest is empty")
            if metadata.st_size > MAX_MANIFEST_BYTES:
                raise ManifestIntegrityError("experiment manifest exceeds its size limit")
            chunks: list[bytes] = []
            remaining = metadata.st_size + 1
            while remaining > 0:
                chunk = os.read(descriptor, min(65_536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            encoded = b"".join(chunks)
            if len(encoded) != metadata.st_size:
                raise ManifestIntegrityError("experiment manifest changed while being read")
            return encoded
        except OSError as exc:
            raise ManifestIntegrityError(f"cannot read experiment manifest: {exc}") from exc
        finally:
            os.close(descriptor)

    def load(self, *, ledger_nonempty: bool = False) -> ExperimentManifest:
        """Load and independently validate persisted canonical bytes and hash."""

        if type(ledger_nonempty) is not bool:
            raise TypeError("ledger_nonempty must be a bool")
        encoded = self._read_bytes(ledger_nonempty=ledger_nonempty)
        try:
            text = encoded.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ManifestIntegrityError("experiment manifest is not UTF-8") from exc
        if not text.endswith("\n") or "\n" in text[:-1]:
            raise ManifestIntegrityError(
                "experiment manifest must contain one newline-terminated JSON object"
            )
        value = _strict_json_loads(text[:-1])
        if not isinstance(value, Mapping):
            raise ManifestIntegrityError("experiment manifest envelope must be an object")
        try:
            envelope = _require_exact_keys(
                value,
                {"manifest", "manifest_hash"},
                label="manifest envelope",
            )
        except ManifestValidationError as exc:
            raise ManifestIntegrityError(str(exc)) from exc
        canonical_file = (_canonical_json(envelope) + "\n").encode("utf-8")
        if encoded != canonical_file:
            raise ManifestIntegrityError("experiment manifest is not canonically encoded")

        raw_hash = envelope["manifest_hash"]
        try:
            stored_hash = _validate_digest(raw_hash, field_name="manifest_hash")
        except ManifestValidationError as exc:
            raise ManifestIntegrityError(str(exc)) from exc
        raw_manifest = envelope["manifest"]
        if not isinstance(raw_manifest, Mapping):
            raise ManifestIntegrityError("manifest payload must be an object")
        computed_hash = _sha256(_canonical_json(raw_manifest))
        if stored_hash != computed_hash:
            raise ManifestIntegrityError(
                "experiment manifest hash mismatch; persisted content was altered"
            )
        try:
            manifest = ExperimentManifest.from_payload(raw_manifest)
        except ManifestValidationError as exc:
            raise ManifestIntegrityError(f"invalid persisted manifest: {exc}") from exc
        if manifest.manifest_hash != stored_hash:
            raise ManifestIntegrityError("typed experiment manifest hash mismatch")
        return manifest

    def verify_resume(
        self,
        expected: ExperimentManifest,
        *,
        ledger_nonempty: bool = False,
    ) -> ExperimentManifest:
        """Refuse resume unless every expected field matches persisted identity."""

        if not isinstance(expected, ExperimentManifest):
            raise TypeError("expected must be an ExperimentManifest instance")
        actual = self.load(ledger_nonempty=ledger_nonempty)
        expected_payload = expected.to_payload()
        actual_payload = actual.to_payload()
        paths = _differing_paths(expected_payload, actual_payload)
        if paths:
            fields = tuple(sorted({path.split(".", 1)[0] for path in paths}))
            raise ManifestDriftError(
                differing_fields=fields,
                differing_paths=paths,
                expected=expected,
                actual=actual,
            )
        return actual

    def resume(
        self,
        expected: ExperimentManifest,
        *,
        ledger_nonempty: bool = False,
    ) -> ExperimentManifest:
        return self.verify_resume(expected, ledger_nonempty=ledger_nonempty)


__all__ = [
    "ExperimentManifest",
    "MANIFEST_SCHEMA_VERSION",
    "MAX_MANIFEST_BYTES",
    "ManifestAlreadyExistsError",
    "ManifestDriftError",
    "ManifestError",
    "ManifestIntegrityError",
    "ManifestStore",
    "ManifestValidationError",
]
