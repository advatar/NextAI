"""E56: multi-generation governed lineage with a mid-run outage arm."""
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


def build_evidence(evidence: EvaluationEvidence) -> PromotionEvidence:
    return PromotionEvidence(
        benchmark_admitted=all(gate.passed for _, gate in evidence.gate_items()),
        gain_bps=round(evidence.utility_gain * 10_000),
        external_regret_bps=0,
        parity_checked=True,
    )


def limits() -> BudgetLimits:
    return BudgetLimits(10, 30, 20, 10_000, 120)


class OutageAfterFirstReceipt:
    """Keep a frozen identity while simulating loss of the runtime transport."""

    def __init__(self, inner: CapsulangPromotionCorroborator) -> None:
        self._inner = inner
        self.governor_digest = inner.governor_digest
        self.calls = 0

    def corroborate(self, decision, evidence):
        self.calls += 1
        if self.calls > 1:
            raise RuntimeError("simulated Capsulang transport outage")
        return self._inner.corroborate(decision, evidence)


def make_governor() -> CapsulangPromotionCorroborator:
    return CapsulangPromotionCorroborator(
        CapsulangGovernor(CAPSULE, expected_semantic_hash=SEMANTIC_HASH),
        build_evidence,
    )


def run_arm(directory: Path, governor=None) -> tuple[StrategyLab, dict]:
    lab = StrategyLab(
        proposer=FixtureSequenceProposer(),
        evaluator=FixtureStrategyEvaluator(),
        policy=AcceptancePolicy(min_gain=0.25),
        limits=limits(),
        ledger_path=directory / "lineage.jsonl",
        run_seed=7,
        promotion_governor=governor,
    )
    lab.initialize(baseline_strategy(), seed=7)
    snapshot = lab.run(6)
    attempts = [
        entry.payload
        for entry in lab.ledger.load()
        if entry.payload.get("kind") == "recursive_lab_attempt"
    ]
    return lab, {"snapshot": snapshot, "attempts": attempts}


def core_budget(snapshot) -> dict[str, int]:
    return {
        "proposals": snapshot.usage.proposals,
        "evaluations": snapshot.usage.evaluations,
        "model_calls": snapshot.usage.model_calls,
        "tokens": snapshot.usage.tokens,
    }


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        control_lab, control = run_arm(base / "control")
        governed_lab, governed = run_arm(base / "governed", make_governor())
        outage = OutageAfterFirstReceipt(make_governor())
        outage_lab, degraded = run_arm(base / "outage", outage)

        control_snapshot = control["snapshot"]
        governed_snapshot = governed["snapshot"]
        degraded_snapshot = degraded["snapshot"]
        governed_receipts = [
            attempt["promotion_governor"]["receipt"]
            for attempt in governed["attempts"]
            if attempt["outcome"] == "accepted"
        ]
        outage_failures = [
            attempt
            for attempt in degraded["attempts"]
            if attempt["reason_codes"] == ["promotion_governor_failed"]
        ]
        matched_core_budgets = (
            core_budget(control_snapshot)
            == core_budget(governed_snapshot)
            == core_budget(degraded_snapshot)
        )
        behavior_parity = (
            control_snapshot.accepted_generations == 3
            and governed_snapshot.accepted_generations == 3
            and control_snapshot.champion.artifact_id
            == governed_snapshot.champion.artifact_id
            and len(governed_receipts) == 3
            and all(len(receipt["transitions"]) == 3 for receipt in governed_receipts)
        )
        outage_contained = (
            degraded_snapshot.accepted_generations == 1
            and degraded_snapshot.champion.generation == 1
            and len(outage_failures) == 2
            and all(
                attempt["promotion_governor"]["receipt"] is None
                and len(attempt["promotion_governor"]["error_digest"]) == 64
                for attempt in outage_failures
            )
        )
        ledgers_verified = all(
            lab.ledger.verify().entry_count > 0
            for lab in (control_lab, governed_lab, outage_lab)
        )
        report = {
            "schema_version": 1,
            "experiment_id": "E56-governed-recursive-cycle",
            "claim_boundary": (
                "deterministic multi-generation fixture comparing an unchanged "
                "lineage, a receipt-gated lineage, and a simulated governor outage"
            ),
            "rounds": 6,
            "arms": {
                "control": {
                    "accepted_generations": control_snapshot.accepted_generations,
                    "champion_generation": control_snapshot.champion.generation,
                    "core_budget": core_budget(control_snapshot),
                    "wall_seconds": control_snapshot.usage.wall_seconds,
                },
                "governed": {
                    "accepted_generations": governed_snapshot.accepted_generations,
                    "champion_generation": governed_snapshot.champion.generation,
                    "receipts": len(governed_receipts),
                    "core_budget": core_budget(governed_snapshot),
                    "wall_seconds": governed_snapshot.usage.wall_seconds,
                },
                "outage_after_first": {
                    "accepted_generations": degraded_snapshot.accepted_generations,
                    "champion_generation": degraded_snapshot.champion.generation,
                    "governor_failures": len(outage_failures),
                    "core_budget": core_budget(degraded_snapshot),
                    "wall_seconds": degraded_snapshot.usage.wall_seconds,
                },
            },
            "matched_core_budgets": matched_core_budgets,
            "governed_behavior_parity": behavior_parity,
            "outage_contained": outage_contained,
            "ledgers_verified": ledgers_verified,
            "adoption_gate": {
                "passed": (
                    matched_core_budgets
                    and behavior_parity
                    and outage_contained
                    and ledgers_verified
                )
            },
        }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(
        ROOT / "experiments" / "E56-governed-recursive-cycle.json", report
    )
    print(
        f"matched_core_budgets={matched_core_budgets} "
        f"behavior_parity={behavior_parity} "
        f"outage_contained={outage_contained} "
        f"adoption_gate={report['adoption_gate']['passed']}"
    )


if __name__ == "__main__":
    main()
