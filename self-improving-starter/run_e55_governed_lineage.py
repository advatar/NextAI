"""E55: require a real Capsulang receipt in StrategyLab's promotion path."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile

from compare_selection import _atomic_json
from recursive_lab.capsulang_governor import (
    CapsulangGovernor,
    CapsulangPromotionCorroborator,
    PromotionEvidence,
)
from recursive_lab.fixtures import (
    FixtureSequenceProposer,
    FixtureStrategyEvaluator,
    baseline_strategy,
)
from recursive_lab.governance import AcceptancePolicy, BudgetLimits, EvaluationEvidence
from recursive_lab.lab import StrategyLab

ROOT = Path(__file__).parent
CAPSULE = ROOT / "capsulang" / "e53_recursive_governor.caps"
SEMANTIC_HASH = "4438a99af2d0539be06a5128d214741a36d1dd8920205b4787062bfaba65cab3"


def promotion_evidence(evidence: EvaluationEvidence) -> PromotionEvidence:
    return PromotionEvidence(
        benchmark_admitted=all(gate.passed for _, gate in evidence.gate_items()),
        gain_bps=round(evidence.utility_gain * 10_000),
        external_regret_bps=0,
        parity_checked=True,
    )


def limits() -> BudgetLimits:
    return BudgetLimits(
        proposals=2,
        evaluations=8,
        model_calls=4,
        tokens=10_000,
        wall_seconds=60,
    )


def run_lineage(directory: Path, semantic_hash: str) -> tuple[StrategyLab, dict]:
    corroborator = CapsulangPromotionCorroborator(
        CapsulangGovernor(CAPSULE, expected_semantic_hash=semantic_hash),
        promotion_evidence,
    )
    lab = StrategyLab(
        proposer=FixtureSequenceProposer(),
        evaluator=FixtureStrategyEvaluator(),
        policy=AcceptancePolicy(min_gain=0.25),
        limits=limits(),
        ledger_path=directory / "lineage.jsonl",
        run_seed=7,
        promotion_governor=corroborator,
    )
    lab.initialize(baseline_strategy(), seed=7)
    snapshot = lab.run(1)
    attempts = [
        entry.payload
        for entry in lab.ledger.load()
        if entry.payload.get("kind") == "recursive_lab_attempt"
        and entry.payload.get("attempt_index") == 1
    ]
    return lab, {"snapshot": snapshot, "attempt": attempts[0]}


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        accepted_lab, accepted = run_lineage(base / "accepted", SEMANTIC_HASH)
        blocked_lab, blocked = run_lineage(base / "blocked", "0" * 64)
        receipt = accepted["attempt"]["promotion_governor"]["receipt"]
        accepted_with_receipt = (
            accepted["snapshot"].accepted_generations == 1
            and accepted["snapshot"].champion.generation == 1
            and accepted["attempt"]["outcome"] == "accepted"
            and isinstance(receipt, dict)
            and len(receipt["transitions"]) == 3
            and receipt["semantic_hash"] == SEMANTIC_HASH
        )
        drift_failed_closed = (
            blocked["snapshot"].accepted_generations == 0
            and blocked["snapshot"].champion.generation == 0
            and blocked["attempt"]["outcome"] == "rejected"
            and blocked["attempt"]["reason_codes"] == ["promotion_governor_failed"]
            and blocked["attempt"]["promotion_governor"]["receipt"] is None
        )
        resumed = StrategyLab(
            proposer=FixtureSequenceProposer(),
            evaluator=FixtureStrategyEvaluator(),
            policy=AcceptancePolicy(min_gain=0.25),
            limits=limits(),
            ledger_path=base / "accepted" / "lineage.jsonl",
            run_seed=7,
            promotion_governor=CapsulangPromotionCorroborator(
                CapsulangGovernor(CAPSULE, expected_semantic_hash=SEMANTIC_HASH),
                promotion_evidence,
            ),
        ).snapshot()
        resume_verified = (
            resumed.accepted_generations == 1 and resumed.champion.generation == 1
        )
        report = {
            "schema_version": 1,
            "experiment_id": "E55-governed-lineage",
            "claim_boundary": (
                "deterministic StrategyLab fixture proving that a descendant "
                "cannot advance the champion without a pinned Capsulang receipt"
            ),
            "semantic_hash": SEMANTIC_HASH,
            "accepted_with_receipt": accepted_with_receipt,
            "semantic_drift_failed_closed": drift_failed_closed,
            "resume_verified_receipt": resume_verified,
            "accepted": {
                "champion_generation": accepted["snapshot"].champion.generation,
                "reason_codes": accepted["attempt"]["reason_codes"],
                "receipt": receipt,
                "ledger_verified": accepted_lab.ledger.verify().entry_count > 0,
            },
            "blocked": {
                "champion_generation": blocked["snapshot"].champion.generation,
                "reason_codes": blocked["attempt"]["reason_codes"],
                "error_digest_recorded": (
                    len(
                        blocked["attempt"]["promotion_governor"]["error_digest"]
                    )
                    == 64
                ),
                "ledger_verified": blocked_lab.ledger.verify().entry_count > 0,
            },
            "adoption_gate": {
                "passed": (
                    accepted_with_receipt
                    and drift_failed_closed
                    and resume_verified
                    and accepted_lab.ledger.verify().entry_count > 0
                    and blocked_lab.ledger.verify().entry_count > 0
                )
            },
        }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(ROOT / "experiments" / "E55-governed-lineage.json", report)
    print(
        f"accepted_with_receipt={accepted_with_receipt} "
        f"semantic_drift_failed_closed={drift_failed_closed} "
        f"resume_verified={resume_verified} "
        f"adoption_gate={report['adoption_gate']['passed']}"
    )


if __name__ == "__main__":
    main()
