from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from recursive_lab.capsulang_governor import (
    CapsulangGovernor,
    CapsulangGovernorError,
    PromotionEvidence,
)


CAPSULE = Path(__file__).parents[1] / "capsulang" / "e53_recursive_governor.caps"
SEMANTIC_HASH = "4438a99af2d0539be06a5128d214741a36d1dd8920205b4787062bfaba65cab3"


class PromotionEvidenceTests(unittest.TestCase):
    def test_host_policy_is_conjunctive(self) -> None:
        self.assertTrue(PromotionEvidence(True, 1, 0, True).host_promotes)
        for evidence in (
            PromotionEvidence(False, 1, 0, True),
            PromotionEvidence(True, 0, 0, True),
            PromotionEvidence(True, 1, -1, True),
            PromotionEvidence(True, 1, 0, False),
        ):
            with self.subTest(evidence=evidence):
                self.assertFalse(evidence.host_promotes)

    def test_evidence_rejects_boolean_integer_fields(self) -> None:
        with self.assertRaises(TypeError):
            PromotionEvidence(True, True, 0, True)  # type: ignore[arg-type]


@unittest.skipUnless(shutil.which("caps"), "Capsulang CLI is optional")
class CapsulangGovernorIntegrationTests(unittest.TestCase):
    def test_promotes_supported_gain_and_records_intents(self) -> None:
        receipt = CapsulangGovernor(
            CAPSULE, expected_semantic_hash=SEMANTIC_HASH
        ).decide(PromotionEvidence(True, 302, 0, True))
        self.assertTrue(receipt.promoted)
        self.assertEqual(receipt.final_state, "promoted")
        self.assertIn("deploy.promote:RecursiveCandidatePolicy", receipt.effect_intents)
        self.assertEqual(len(receipt.transitions), 3)

    def test_quarantines_inadmissible_evidence(self) -> None:
        receipt = CapsulangGovernor(
            CAPSULE, expected_semantic_hash=SEMANTIC_HASH
        ).decide(PromotionEvidence(False, 302, 0, True))
        self.assertFalse(receipt.promoted)
        self.assertEqual(receipt.final_state, "quarantined")
        self.assertIn("deploy.rollback:RecursiveCandidatePolicy", receipt.effect_intents)

    def test_semantic_drift_and_missing_cli_fail_closed(self) -> None:
        evidence = PromotionEvidence(True, 302, 0, True)
        with self.assertRaises(CapsulangGovernorError):
            CapsulangGovernor(CAPSULE, expected_semantic_hash="0" * 64).decide(evidence)
        with self.assertRaises(CapsulangGovernorError):
            CapsulangGovernor(
                CAPSULE,
                expected_semantic_hash=SEMANTIC_HASH,
                executable="definitely-not-a-capsulang-command",
            ).decide(evidence)

    def test_scenario_and_legacy_modes_have_exact_receipt_parity(self) -> None:
        fixtures = (
            PromotionEvidence(True, 302, 0, True),
            PromotionEvidence(False, 302, 0, True),
            PromotionEvidence(True, 500, -1, True),
        )
        scenario = CapsulangGovernor(
            CAPSULE,
            expected_semantic_hash=SEMANTIC_HASH,
            decision_mode="scenario",
        )
        legacy = CapsulangGovernor(
            CAPSULE,
            expected_semantic_hash=SEMANTIC_HASH,
            decision_mode="legacy-step",
        )
        self.assertEqual(
            [scenario.decide(item).to_dict() for item in fixtures],
            [legacy.decide(item).to_dict() for item in fixtures],
        )

    def test_cached_pin_still_rejects_local_source_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory) / "governor.caps"
            shutil.copyfile(CAPSULE, copy)
            governor = CapsulangGovernor(
                copy, expected_semantic_hash=SEMANTIC_HASH
            )
            copy.write_text(copy.read_text() + "\n", encoding="utf-8")
            with self.assertRaisesRegex(
                CapsulangGovernorError, "source changed"
            ):
                governor.decide(PromotionEvidence(True, 302, 0, True))
