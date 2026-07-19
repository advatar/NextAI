from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from recursive_lab.artifacts import ArtifactRecord, StrategyArtifact, canonical_json, sha256_digest
from recursive_lab.ledger import (
    GENESIS_HASH,
    AttemptEvent,
    LedgerIntegrityError,
    LedgerValidationError,
    LineageLedger,
)


PROPOSER_DIGEST = sha256_digest("ledger-test-proposer")


def root_record() -> ArtifactRecord:
    return ArtifactRecord(
        artifact=StrategyArtifact(
            system_instruction=(
                "Improve the public implementation with a small reproducible change."
            ),
            planning_steps=(
                "Inspect the documented behavior.",
                "Make one bounded change.",
                "Run the approved public tests.",
            ),
            max_attempts=2,
        ),
        parent_id=None,
        generation=0,
        proposer_digest=PROPOSER_DIGEST,
        seed=7,
    )


def accepted_event(attempt_id: str = "attempt-000") -> AttemptEvent:
    return AttemptEvent.accepted(
        attempt_id=attempt_id,
        artifact_record=root_record(),
        reason_code="capability-and-safety-passed",
    )


def rejected_event(attempt_id: str = "attempt-001") -> AttemptEvent:
    return AttemptEvent.rejected(
        attempt_id=attempt_id,
        candidate_digest=sha256_digest("unsafe raw proposal"),
        parent_id=None,
        generation=0,
        reason_code="schema.unsafe-content",
    )


class AttemptEventTests(unittest.TestCase):
    def test_accepted_and_rejected_use_one_explicit_shape(self) -> None:
        accepted = accepted_event()
        rejected = rejected_event()

        self.assertEqual(accepted.outcome, "accepted")
        self.assertIsNotNone(accepted.artifact_record)
        self.assertEqual(rejected.outcome, "rejected")
        self.assertIsNone(rejected.artifact_record)
        self.assertEqual(set(accepted.to_payload()), set(rejected.to_payload()))
        self.assertEqual(AttemptEvent.from_payload(accepted.to_payload()), accepted)
        self.assertEqual(AttemptEvent.from_payload(rejected.to_payload()), rejected)

    def test_accepted_requires_record_and_record_metadata_must_match(self) -> None:
        record = root_record()
        with self.assertRaises(LedgerValidationError):
            AttemptEvent(
                attempt_id="attempt-invalid",
                outcome="accepted",
                candidate_digest=record.artifact_id,
                parent_id=None,
                generation=0,
                reason_code="accepted",
                artifact_record=None,
            )
        with self.assertRaises(LedgerValidationError):
            AttemptEvent(
                attempt_id="attempt-invalid",
                outcome="rejected",
                candidate_digest="f" * 64,
                parent_id=None,
                generation=0,
                reason_code="evaluation.failed",
                artifact_record=record,
            )

    def test_unhashable_outcome_fails_as_validation_error(self) -> None:
        with self.assertRaises(LedgerValidationError):
            AttemptEvent(
                attempt_id="attempt-invalid",
                outcome=[],  # type: ignore[arg-type]
                candidate_digest="a" * 64,
                parent_id=None,
                generation=0,
                reason_code="invalid.outcome",
            )


class LineageLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tempdir.name) / "lineage.jsonl"
        self.ledger = LineageLedger(self.path)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _append_three(self) -> list[str]:
        heads = []
        heads.append(self.ledger.append(accepted_event("attempt-000")).current_hash)
        heads.append(self.ledger.append(rejected_event("attempt-001")).current_hash)
        heads.append(
            self.ledger.append(
                {"kind": "audit", "message": "independent review complete"}
            ).current_hash
        )
        return heads

    def test_empty_ledger_has_genesis_head(self) -> None:
        self.assertEqual(self.ledger.load(), ())
        verification = self.ledger.verify(expected_head=GENESIS_HASH)
        self.assertEqual(verification.entry_count, 0)
        self.assertEqual(verification.head_hash, GENESIS_HASH)

    def test_append_is_incremental_canonical_and_fsynced_before_return(self) -> None:
        first = self.ledger.append(accepted_event())
        first_bytes = self.path.read_bytes()
        self.assertTrue(first_bytes.endswith(b"\n"))
        self.assertEqual(len(first_bytes.splitlines()), 1)

        second = self.ledger.append(
            rejected_event(), expected_head=first.current_hash
        )
        all_bytes = self.path.read_bytes()
        self.assertTrue(all_bytes.startswith(first_bytes))
        self.assertEqual(len(all_bytes.splitlines()), 2)

        for raw_line in all_bytes.decode("utf-8").splitlines():
            self.assertEqual(raw_line, canonical_json(json.loads(raw_line)))

        entries = self.ledger.load(expected_head=second.current_hash)
        self.assertEqual([entry.sequence for entry in entries], [0, 1])
        self.assertEqual(entries[0].previous_hash, GENESIS_HASH)
        self.assertEqual(entries[1].previous_hash, entries[0].current_hash)
        self.assertEqual(entries[0].as_attempt().outcome, "accepted")
        self.assertEqual(entries[1].as_attempt().outcome, "rejected")

        if os.name == "posix":
            self.assertEqual(self.path.stat().st_mode & 0o077, 0)

    def test_payload_edit_is_detected(self) -> None:
        self._append_three()
        rows = self.path.read_text(encoding="utf-8").splitlines()
        envelope = json.loads(rows[1])
        envelope["payload"]["reason_code"] = "forged.reason"
        rows[1] = canonical_json(envelope)
        self.path.write_text("\n".join(rows) + "\n", encoding="utf-8")

        with self.assertRaisesRegex(LedgerIntegrityError, "hash mismatch"):
            self.ledger.verify()

    def test_middle_deletion_is_detected(self) -> None:
        self._append_three()
        rows = self.path.read_bytes().splitlines(keepends=True)
        self.path.write_bytes(rows[0] + rows[2])

        with self.assertRaises(LedgerIntegrityError):
            self.ledger.verify()

    def test_reordering_is_detected(self) -> None:
        self._append_three()
        rows = self.path.read_bytes().splitlines(keepends=True)
        self.path.write_bytes(rows[1] + rows[0] + rows[2])

        with self.assertRaisesRegex(LedgerIntegrityError, "sequence mismatch"):
            self.ledger.verify()

    def test_partial_tail_is_detected(self) -> None:
        self._append_three()
        data = self.path.read_bytes()
        self.path.write_bytes(data[:-10])

        with self.assertRaisesRegex(LedgerIntegrityError, "truncated final row"):
            self.ledger.verify()

    def test_complete_tail_truncation_requires_and_honors_external_anchor(self) -> None:
        heads = self._append_three()
        rows = self.path.read_bytes().splitlines(keepends=True)
        self.path.write_bytes(b"".join(rows[:-1]))

        # The remaining prefix is internally valid; the trusted head detects the
        # rollback that a hash chain alone cannot distinguish from an older file.
        self.assertEqual(self.ledger.verify().head_hash, heads[-2])
        with self.assertRaisesRegex(LedgerIntegrityError, "head mismatch"):
            self.ledger.verify(expected_head=heads[-1])

    def test_noncanonical_serialization_and_blank_rows_are_detected(self) -> None:
        self.ledger.append(accepted_event())
        parsed = json.loads(self.path.read_text(encoding="utf-8"))
        self.path.write_text(json.dumps(parsed) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(LedgerIntegrityError, "not canonically encoded"):
            self.ledger.verify()

        self.path.write_bytes(b"\n")
        with self.assertRaisesRegex(LedgerIntegrityError, "empty"):
            self.ledger.verify()

    def test_compare_and_append_rejects_stale_head_without_writing(self) -> None:
        first = self.ledger.append(accepted_event())
        before = self.path.read_bytes()
        with self.assertRaisesRegex(LedgerIntegrityError, "head mismatch"):
            self.ledger.append(rejected_event(), expected_head="f" * 64)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.ledger.head_hash, first.current_hash)

    def test_append_refuses_to_extend_tampered_ledger(self) -> None:
        self.ledger.append(accepted_event())
        data = bytearray(self.path.read_bytes())
        data[data.index(b"accepted")] = ord("X")
        self.path.write_bytes(data)
        before = self.path.read_bytes()

        with self.assertRaises(LedgerIntegrityError):
            self.ledger.append(rejected_event())
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
