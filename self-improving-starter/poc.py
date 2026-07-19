"""CLI for the auditable recursive-scaffold proof-of-concept.

The default demo is deterministic and uses synthetic fixtures.  It validates
the laboratory, not an RSI capability claim, and requires no model SDK/API key.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from recursive_lab.fixtures import (
    FixtureSealedUtility,
    FixtureSequenceProposer,
    FixtureStrategyEvaluator,
    baseline_strategy,
    fixture_meta_arms,
)
from recursive_lab.governance import AcceptancePolicy, BudgetLimits
from recursive_lab.lab import SEALED_SPLIT, StrategyLab
from recursive_lab.ledger import GENESIS_HASH, LineageLedger
from recursive_lab.metaproductivity import (
    CostWeights,
    ExperimentBudget,
    run_tournament,
)


class _DeterministicClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        self.value += 0.001
        return self.value


_DEMO_LIMITS = BudgetLimits(
    proposals=32,
    evaluations=128,
    model_calls=64,
    tokens=8_192,
    wall_seconds=60.0,
)


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="ascii") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _default_output() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path("runs") / f"poc-demo-{stamp}"


def _metaproductivity_fixture() -> dict[str, Any]:
    ancestor, descendant = fixture_meta_arms()
    seeds = [baseline_strategy(f"fixture seed {index}") for index in range(5)]
    report = run_tournament(
        ancestor=ancestor,
        descendant=descendant,
        seed_artifacts=seeds,
        trial_seeds=[100, 101, 102, 103, 104],
        evaluator=FixtureSealedUtility(),
        budget=ExperimentBudget(
            max_proposals=1,
            max_evaluations=2,
            max_model_calls=1,
            max_tokens=32,
            max_wall_seconds=1.0,
        ),
        cost_weights=CostWeights(
            proposal=1.0,
            evaluation=1.0,
            model_call=1.0,
            token=0.0,
            wall_second=0.0,
        ),
        split=SEALED_SPLIT,
        effect_threshold=0.1,
        bootstrap_samples=2000,
        bootstrap_seed=7,
    )
    return report.to_dict()


def _run_demo(args: argparse.Namespace) -> int:
    output = args.out or _default_output()
    ledger_path = output / "lineage.jsonl"
    anchor_path = output / "ledger.head"
    if args.resume:
        if not anchor_path.is_file():
            raise SystemExit("cannot resume a nonempty ledger without its trusted head anchor")
        trusted_head = anchor_path.read_text(encoding="ascii").strip()
        entries = LineageLedger(ledger_path).load()
        actual_head = entries[-1].current_hash if entries else GENESIS_HASH
        known_heads = {GENESIS_HASH, *(entry.current_hash for entry in entries)}
        if trusted_head != actual_head and not args.recover_unanchored_tail:
            raise SystemExit(
                "cannot resume: trusted head does not match the ledger head; "
                "inspect the tail before using --recover-unanchored-tail"
            )
        if trusted_head not in known_heads:
            raise SystemExit(
                "cannot resume: the trusted head is not a prefix of the verified ledger"
            )
    elif output.exists() and any(output.iterdir()):
        raise SystemExit(f"output directory is not empty: {output}")

    output.mkdir(parents=True, exist_ok=True)
    if not args.resume:
        _atomic_text(anchor_path, GENESIS_HASH + "\n")
    proposer = FixtureSequenceProposer()
    evaluator = FixtureStrategyEvaluator()
    lab = StrategyLab(
        proposer=proposer,
        evaluator=evaluator,
        policy=AcceptancePolicy(min_gain=0.25),
        limits=_DEMO_LIMITS,
        ledger_path=ledger_path,
        run_seed=args.seed,
        manifest_path=output / "experiment-manifest.json",
        clock=_DeterministicClock(),
        head_observer=lambda head: _atomic_text(anchor_path, head + "\n"),
    )
    if lab.initialized:
        proposer.calls = lab.snapshot().attempts
    else:
        lab.initialize(baseline_strategy(), seed=args.seed)
    baseline = baseline_strategy()
    prior_baseline_audit = lab.sealed_result(baseline.artifact_id)
    if prior_baseline_audit is None:
        remaining_rounds = max(0, args.rounds - lab.snapshot().attempts)
        snapshot = lab.run(remaining_rounds)
    else:
        snapshot = lab.snapshot(stopped_reason="sealed_suite_already_consumed")

    # The sealed fixture is used only after search, once per comparison arm.
    baseline_audit = prior_baseline_audit or lab.evaluate_sealed(
        baseline, seed=args.seed, authorize_milestone=True
    )
    if snapshot.champion.artifact_id == baseline.artifact_id:
        champion_audit = baseline_audit
    else:
        champion_audit = lab.sealed_result(snapshot.champion.artifact_id)
        if champion_audit is None:
            champion_audit = lab.evaluate_sealed(
                snapshot.champion.artifact,
                seed=args.seed,
                authorize_milestone=True,
            )
    final_snapshot = lab.snapshot(stopped_reason=snapshot.stopped_reason)
    meta_report = _metaproductivity_fixture()
    summary = {
        "claim_boundary": (
            "deterministic plumbing validation only; synthetic fixture scores are "
            "not evidence of model self-improvement or RSI"
        ),
        "lab": final_snapshot.to_payload(),
        "sealed_fixture_comparison": {
            "baseline_utility": baseline_audit.utility,
            "champion_utility": champion_audit.utility,
            "utility_delta": champion_audit.utility - baseline_audit.utility,
            "split": SEALED_SPLIT,
        },
        "metaproductivity_fixture_verdict": meta_report["summary"]["verdict"],
        "outputs": {
            "experiment_manifest": str(output / "experiment-manifest.json"),
            "ledger": str(ledger_path),
            "ledger_head_anchor": str(anchor_path),
            "metaproductivity_report": str(output / "metaproductivity.json"),
        },
        "experiment_manifest_hash": final_snapshot.manifest_hash,
    }
    _atomic_json(output / "metaproductivity.json", meta_report)
    _atomic_json(output / "summary.json", summary)
    _atomic_text(anchor_path, final_snapshot.ledger_head + "\n")

    print("Deterministic POC plumbing validation complete.")
    print(f"Accepted generations: {final_snapshot.accepted_generations}")
    print(f"Attempts logged: {final_snapshot.attempts}")
    print(f"Fixture sealed utility: {baseline_audit.utility:.2f} -> {champion_audit.utility:.2f}")
    print(
        "Fixture metaproductivity verdict: "
        f"{meta_report['summary']['verdict']} (not empirical RSI evidence)"
    )
    print(f"Artifacts: {output}")
    return 0


def _verify_ledger(args: argparse.Namespace) -> int:
    expected = args.expected_head
    if expected is None and args.anchor is not None:
        expected = args.anchor.read_text(encoding="ascii").strip()
    result = LineageLedger(args.ledger).verify(expected_head=expected)
    print(f"ledger OK: {result.entry_count} entries; head={result.head_hash}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("demo", help="run the no-key deterministic fixture lab")
    demo.add_argument("--out", type=Path, default=None)
    demo.add_argument(
        "--rounds",
        type=int,
        default=6,
        help="target total proposal attempts for this lineage (default: 6)",
    )
    demo.add_argument("--seed", type=int, default=0)
    demo.add_argument("--resume", action="store_true")
    demo.add_argument(
        "--recover-unanchored-tail",
        action="store_true",
        help="explicitly trust a verified ledger suffix after inspecting a stale anchor",
    )
    demo.set_defaults(handler=_run_demo)

    verify = subparsers.add_parser("verify-ledger", help="verify a lineage hash chain")
    verify.add_argument("--ledger", type=Path, required=True)
    verify.add_argument("--anchor", type=Path, default=None)
    verify.add_argument("--expected-head", default=None)
    verify.set_defaults(handler=_verify_ledger)

    args = parser.parse_args()
    if getattr(args, "rounds", 0) < 0:
        parser.error("--rounds must be non-negative")
    if getattr(args, "recover_unanchored_tail", False) and not getattr(
        args, "resume", False
    ):
        parser.error("--recover-unanchored-tail requires --resume")
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
