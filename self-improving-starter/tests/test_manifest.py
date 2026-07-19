from __future__ import annotations

from dataclasses import FrozenInstanceError
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from recursive_lab.governance import BudgetLimits
from recursive_lab.manifest import (
    ExperimentManifest,
    MANIFEST_SCHEMA_VERSION,
    ManifestAlreadyExistsError,
    ManifestDriftError,
    ManifestIntegrityError,
    ManifestStore,
    ManifestValidationError,
)


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def make_manifest(**overrides: object) -> ExperimentManifest:
    values: dict[str, object] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_seed": 42,
        "proposer_name": "fixture-proposer/v1",
        "proposer_digest": digest("proposer"),
        "evaluator_id": "private-suite/v3",
        "evaluator_digest": digest("evaluator"),
        "acceptance_policy": {"min_gain": 0.05, "mode": "conjunctive"},
        "budget_limits": BudgetLimits(10, 8, 12, 50_000, 300.0),
        "development_task_manifest_digest": digest("development tasks"),
        "private_task_manifest_digest": digest("private tasks"),
        "sealed_task_manifest_digest": digest("sealed tasks"),
        "mutable_artifact_schema_id": "strategy/v1",
        "candidate_runtime_policy_digest": digest("runtime policy"),
    }
    values.update(overrides)
    return ExperimentManifest(**values)  # type: ignore[arg-type]


class ExperimentManifestTests(unittest.TestCase):
    def test_is_immutable_canonical_content_addressed_and_round_trips(self) -> None:
        manifest = make_manifest()
        payload = manifest.to_payload()
        expected_json = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )

        self.assertEqual(manifest.canonical_json, expected_json)
        self.assertEqual(
            manifest.manifest_hash,
            hashlib.sha256(expected_json.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(manifest.digest, manifest.manifest_hash)
        self.assertEqual(ExperimentManifest.from_payload(payload), manifest)
        self.assertEqual(ExperimentManifest.from_dict(manifest.to_dict()), manifest)
        with self.assertRaises(FrozenInstanceError):
            manifest.run_seed = 99  # type: ignore[misc]

    def test_acceptance_policy_is_deeply_immutable(self) -> None:
        source = {"min_gain": 0.1, "nested": {"checks": ["safety", "integrity"]}}
        manifest = make_manifest(acceptance_policy=source)
        source["min_gain"] = 999
        returned = manifest.acceptance_policy
        returned["min_gain"] = -1
        returned_nested = returned["nested"]
        self.assertIsInstance(returned_nested, dict)
        returned_nested["checks"].append("resource")  # type: ignore[union-attr]

        self.assertEqual(manifest.acceptance_policy["min_gain"], 0.1)
        self.assertEqual(
            manifest.acceptance_policy["nested"],
            {"checks": ["safety", "integrity"]},
        )

    def test_each_required_field_is_present_and_exact(self) -> None:
        payload = make_manifest().to_payload()
        for field in tuple(payload):
            with self.subTest(missing=field):
                malformed = dict(payload)
                malformed.pop(field)
                with self.assertRaisesRegex(ManifestValidationError, "missing"):
                    ExperimentManifest.from_payload(malformed)
        payload["unreviewed_override"] = True
        with self.assertRaisesRegex(ManifestValidationError, "extra"):
            ExperimentManifest.from_payload(payload)

    def test_rejects_invalid_schema_seed_identifiers_and_digests(self) -> None:
        invalid_cases = (
            {"schema_version": 2},
            {"schema_version": True},
            {"run_seed": -1},
            {"run_seed": True},
            {"proposer_name": " proposer"},
            {"evaluator_id": ""},
            {"mutable_artifact_schema_id": "has whitespace"},
            {"proposer_digest": "A" * 64},
            {"evaluator_digest": "short"},
            {"development_task_manifest_digest": "x" * 64},
            {"private_task_manifest_digest": "f" * 63},
            {"sealed_task_manifest_digest": "f" * 65},
            {"candidate_runtime_policy_digest": None},
        )
        for overrides in invalid_cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ManifestValidationError):
                    make_manifest(**overrides)

    def test_rejects_mutable_or_noncanonical_policy_payloads(self) -> None:
        for policy in ([], {"gain": math.nan}, {"gain": math.inf}, {1: "bad key"}):
            with self.subTest(policy=policy):
                with self.assertRaises(ManifestValidationError):
                    make_manifest(acceptance_policy=policy)

    def test_budget_must_be_valid_budget_limits(self) -> None:
        with self.assertRaisesRegex(ManifestValidationError, "BudgetLimits"):
            make_manifest(budget_limits={"proposals": 1})


class ManifestStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tempdir.name) / "run" / "manifest.json"
        self.store = ManifestStore(self.path)
        self.manifest = make_manifest()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_initialize_atomically_writes_fsyncs_and_loads(self) -> None:
        with mock.patch("recursive_lab.manifest.os.fsync", wraps=os.fsync) as fsync:
            initialized = self.store.initialize(self.manifest)

        self.assertEqual(initialized, self.manifest)
        self.assertGreaterEqual(fsync.call_count, 2)
        self.assertEqual(self.store.load(), self.manifest)
        raw = self.path.read_bytes()
        self.assertTrue(raw.endswith(b"\n"))
        self.assertEqual(len(raw.splitlines()), 1)
        envelope = json.loads(raw)
        self.assertEqual(envelope["manifest_hash"], self.manifest.manifest_hash)
        expected = json.dumps(
            envelope,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        self.assertEqual(raw, expected)
        if os.name == "posix":
            self.assertEqual(self.path.stat().st_mode & 0o077, 0)
        self.assertEqual(list(self.path.parent.glob(".*.tmp")), [])

    def test_initialize_never_overwrites_even_identical_manifest(self) -> None:
        self.store.initialize(self.manifest)
        before = self.path.read_bytes()
        with self.assertRaises(ManifestAlreadyExistsError):
            self.store.initialize(self.manifest)
        self.assertEqual(self.path.read_bytes(), before)

    def test_missing_manifest_with_nonempty_ledger_fails_closed(self) -> None:
        with self.assertRaisesRegex(ManifestIntegrityError, "nonempty lineage ledger"):
            self.store.initialize(self.manifest, ledger_nonempty=True)
        self.assertFalse(self.path.exists())
        with self.assertRaisesRegex(ManifestIntegrityError, "nonempty lineage ledger"):
            self.store.load(ledger_nonempty=True)
        with self.assertRaisesRegex(ManifestIntegrityError, "nonempty lineage ledger"):
            self.store.verify_resume(self.manifest, ledger_nonempty=True)

    def test_missing_manifest_for_resume_is_rejected_even_with_empty_ledger(self) -> None:
        with self.assertRaisesRegex(ManifestIntegrityError, "missing"):
            self.store.verify_resume(self.manifest, ledger_nonempty=False)

    def test_exact_resume_succeeds_and_alias_matches(self) -> None:
        self.store.initialize(self.manifest)
        self.assertEqual(self.store.verify_resume(self.manifest), self.manifest)
        self.assertEqual(self.store.resume(self.manifest), self.manifest)

    def test_resume_reports_every_top_level_drift_and_nested_path(self) -> None:
        self.store.initialize(self.manifest)
        changed = make_manifest(
            run_seed=43,
            proposer_digest=digest("different proposer"),
            acceptance_policy={"min_gain": 0.5, "mode": "conjunctive"},
            budget_limits=BudgetLimits(10, 8, 12, 49_999, 300.0),
            sealed_task_manifest_digest=digest("different sealed tasks"),
        )

        with self.assertRaises(ManifestDriftError) as caught:
            self.store.verify_resume(changed, ledger_nonempty=True)

        error = caught.exception
        self.assertEqual(
            error.differing_fields,
            (
                "acceptance_policy",
                "budget_limits",
                "proposer_digest",
                "run_seed",
                "sealed_task_manifest_digest",
            ),
        )
        self.assertIn("acceptance_policy.min_gain", error.differing_paths)
        self.assertIn("budget_limits.tokens", error.differing_paths)
        self.assertIn("proposer_digest", str(error))
        json.dumps(error.to_dict(), allow_nan=False)

    def test_each_manifest_identity_field_is_verified_on_resume(self) -> None:
        self.store.initialize(self.manifest)
        changes = {
            "run_seed": 99,
            "proposer_name": "fixture-proposer/v2",
            "proposer_digest": digest("new proposer"),
            "evaluator_id": "private-suite/v4",
            "evaluator_digest": digest("new evaluator"),
            "acceptance_policy": {"min_gain": 0.06, "mode": "conjunctive"},
            "budget_limits": BudgetLimits(9, 8, 12, 50_000, 300.0),
            "development_task_manifest_digest": digest("new development"),
            "private_task_manifest_digest": digest("new private"),
            "sealed_task_manifest_digest": digest("new sealed"),
            "mutable_artifact_schema_id": "strategy/v2",
            "candidate_runtime_policy_digest": digest("new runtime"),
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                with self.assertRaises(ManifestDriftError) as caught:
                    self.store.verify_resume(make_manifest(**{field: value}))
                self.assertEqual(caught.exception.differing_fields, (field,))

    def test_hash_tampering_is_detected_before_resume_comparison(self) -> None:
        self.store.initialize(self.manifest)
        envelope = json.loads(self.path.read_text(encoding="utf-8"))
        envelope["manifest"]["run_seed"] = 1000
        self.path.write_text(
            json.dumps(envelope, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ManifestIntegrityError, "hash mismatch"):
            self.store.load()

    def test_noncanonical_duplicate_extra_and_truncated_files_are_rejected(self) -> None:
        self.store.initialize(self.manifest)
        original = self.path.read_bytes()

        envelope = json.loads(original)
        self.path.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ManifestIntegrityError, "newline-terminated|canonical"):
            self.store.load()

        self.path.write_bytes(original.replace(b'{"manifest":', b'{"extra":0,"manifest":'))
        with self.assertRaisesRegex(ManifestIntegrityError, "invalid fields"):
            self.store.load()

        duplicate = original.replace(
            b'{"manifest":',
            b'{"manifest_hash":"' + self.manifest.manifest_hash.encode() + b'","manifest":',
        )
        self.path.write_bytes(duplicate)
        with self.assertRaisesRegex(ManifestIntegrityError, "duplicate JSON key"):
            self.store.load()

        self.path.write_bytes(original[:-4])
        with self.assertRaises(ManifestIntegrityError):
            self.store.load()

    def test_symlink_manifest_is_refused(self) -> None:
        if not hasattr(os, "O_NOFOLLOW"):
            self.skipTest("platform does not expose O_NOFOLLOW")
        target = Path(self.tempdir.name) / "target.json"
        target.write_text("{}\n", encoding="utf-8")
        self.path.parent.mkdir(parents=True)
        self.path.symlink_to(target)
        with self.assertRaises(ManifestIntegrityError):
            self.store.load()


if __name__ == "__main__":
    unittest.main()
