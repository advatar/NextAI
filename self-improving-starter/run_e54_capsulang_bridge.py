"""E54: exercise the pinned Python-to-Capsulang governance bridge."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from compare_selection import _atomic_json
from recursive_lab.capsulang_governor import (
    CapsulangGovernor,
    CapsulangGovernorError,
    PromotionEvidence,
)

ROOT = Path(__file__).parent
CAPSULE = ROOT / "capsulang" / "e53_recursive_governor.caps"
SEMANTIC_HASH = "4438a99af2d0539be06a5128d214741a36d1dd8920205b4787062bfaba65cab3"


def fails_closed(governor: CapsulangGovernor, evidence: PromotionEvidence) -> bool:
    try:
        governor.decide(evidence)
    except CapsulangGovernorError:
        return True
    return False


def main() -> None:
    governor = CapsulangGovernor(CAPSULE, expected_semantic_hash=SEMANTIC_HASH)
    fixtures = {
        "e45_supported_gain": PromotionEvidence(True, 302, 0, True),
        "e51_uninformative_benchmark": PromotionEvidence(False, 0, 0, True),
        "external_regret": PromotionEvidence(True, 500, -100, True),
        "unchecked_parity": PromotionEvidence(True, 302, 0, False),
    }
    receipts = {name: governor.decide(evidence) for name, evidence in fixtures.items()}
    expected = {
        "e45_supported_gain": "promote",
        "e51_uninformative_benchmark": "reject",
        "external_regret": "reject",
        "unchecked_parity": "reject",
    }
    decision_parity = all(
        receipts[name].decision == decision for name, decision in expected.items()
    )
    semantic_drift_blocked = fails_closed(
        CapsulangGovernor(CAPSULE, expected_semantic_hash="0" * 64),
        fixtures["e45_supported_gain"],
    )
    missing_runtime_blocked = fails_closed(
        CapsulangGovernor(
            CAPSULE,
            expected_semantic_hash=SEMANTIC_HASH,
            executable="definitely-not-a-capsulang-command",
        ),
        fixtures["e45_supported_gain"],
    )
    report = {
        "schema_version": 1,
        "experiment_id": "E54-capsulang-host-bridge",
        "claim_boundary": (
            "local host-bridge integration test; Capsulang validates transitions "
            "and returns effect intents, while Python retains execution authority"
        ),
        "semantic_hash": SEMANTIC_HASH,
        "decision_parity": decision_parity,
        "receipts": {name: receipt.to_dict() for name, receipt in receipts.items()},
        "semantic_drift_blocked": semantic_drift_blocked,
        "missing_runtime_blocked": missing_runtime_blocked,
        "effect_intents_executed": False,
        "adoption_gate": {
            "passed": (
                decision_parity
                and semantic_drift_blocked
                and missing_runtime_blocked
                and all(len(receipt.transitions) == 3 for receipt in receipts.values())
            )
        },
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(ROOT / "experiments" / "E54-capsulang-host-bridge.json", report)
    print(
        f"decision_parity={decision_parity} "
        f"semantic_drift_blocked={semantic_drift_blocked} "
        f"missing_runtime_blocked={missing_runtime_blocked} "
        f"adoption_gate={report['adoption_gate']['passed']}"
    )


if __name__ == "__main__":
    main()
