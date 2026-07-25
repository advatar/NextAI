"""E57: compare legacy transition subprocesses with scenario batching."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import time

from compare_selection import _atomic_json
from recursive_lab.capsulang_governor import (
    CapsulangGovernor,
    CapsulangGovernorError,
    PromotionEvidence,
)

ROOT = Path(__file__).parent
CAPSULE = ROOT / "capsulang" / "e53_recursive_governor.caps"
SEMANTIC_HASH = "4438a99af2d0539be06a5128d214741a36d1dd8920205b4787062bfaba65cab3"
FIXTURES = (
    PromotionEvidence(True, 302, 0, True),
    PromotionEvidence(False, 302, 0, True),
    PromotionEvidence(True, 500, -100, True),
    PromotionEvidence(True, 302, 0, False),
)


def run_mode(mode: str) -> tuple[list[dict], float]:
    governor = CapsulangGovernor(
        CAPSULE,
        expected_semantic_hash=SEMANTIC_HASH,
        decision_mode=mode,
    )
    started = time.perf_counter()
    receipts = [governor.decide(evidence).to_dict() for evidence in FIXTURES]
    return receipts, time.perf_counter() - started


def source_drift_blocked() -> bool:
    with tempfile.TemporaryDirectory() as directory:
        copy = Path(directory) / "governor.caps"
        copy.write_bytes(CAPSULE.read_bytes())
        governor = CapsulangGovernor(copy, expected_semantic_hash=SEMANTIC_HASH)
        copy.write_bytes(copy.read_bytes() + b"\n")
        try:
            governor.decide(FIXTURES[0])
        except CapsulangGovernorError:
            return True
    return False


def main() -> None:
    legacy, legacy_seconds = run_mode("legacy-step")
    batched, batched_seconds = run_mode("scenario")
    exact_receipt_parity = legacy == batched
    speedup = legacy_seconds / batched_seconds
    drift_blocked = source_drift_blocked()
    report = {
        "schema_version": 1,
        "experiment_id": "E57-batched-governor",
        "claim_boundary": (
            "local bridge transport optimization; the Capsulang machine, host "
            "policy, fixtures, and receipt schema are unchanged"
        ),
        "fixtures": len(FIXTURES),
        "legacy": {
            "mode": "one semantic check plus three process launches per receipt",
            "seconds": legacy_seconds,
            "receipts": legacy,
        },
        "batched": {
            "mode": "cached semantic pin plus one checked scenario per receipt",
            "seconds": batched_seconds,
            "receipts": batched,
        },
        "exact_receipt_parity": exact_receipt_parity,
        "speedup": speedup,
        "source_drift_blocked_after_cache": drift_blocked,
        "adoption_gate": {
            "passed": (
                exact_receipt_parity
                and batched_seconds < legacy_seconds
                and speedup > 1.5
                and drift_blocked
            )
        },
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(ROOT / "experiments" / "E57-batched-governor.json", report)
    print(
        f"receipt_parity={exact_receipt_parity} "
        f"legacy={legacy_seconds:.3f}s batched={batched_seconds:.3f}s "
        f"speedup={speedup:.2f}x drift_blocked={drift_blocked} "
        f"adoption_gate={report['adoption_gate']['passed']}"
    )


if __name__ == "__main__":
    main()
