from __future__ import annotations

import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from recursive_lab.fixtures import (  # noqa: E402
    FixtureSequenceProposer,
    FixtureStrategyEvaluator,
    baseline_strategy,
)
from recursive_lab.governance import AcceptancePolicy, BudgetLimits  # noqa: E402
from recursive_lab.governance import GateResult  # noqa: E402
from recursive_lab.lab import (  # noqa: E402
    ArtifactEvaluation,
    MeteredOperationError,
    ProposalResult,
    StrategyLab,
)
from recursive_lab.artifacts import sha256_digest  # noqa: E402
from recursive_lab.manifest import ManifestDriftError, ManifestIntegrityError  # noqa: E402


def limits(*, proposals=10, evaluations=30):
    return BudgetLimits(
        proposals=proposals,
        evaluations=evaluations,
        model_calls=20,
        tokens=10_000,
        wall_seconds=60,
    )


class RecursiveLabTests(unittest.TestCase):
    def test_fixture_run_persists_three_generations_and_all_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "lineage.jsonl"
            proposer = FixtureSequenceProposer()
            lab = StrategyLab(
                proposer=proposer,
                evaluator=FixtureStrategyEvaluator(),
                policy=AcceptancePolicy(min_gain=0.25),
                limits=limits(),
                ledger_path=ledger_path,
                run_seed=7,
            )
            initial = lab.initialize(baseline_strategy(), seed=7)
            final = lab.run(6)

            self.assertEqual(initial.accepted_generations, 0)
            self.assertEqual(final.accepted_generations, 3)
            self.assertEqual(final.champion.generation, 3)
            self.assertEqual(final.attempts, 6)
            self.assertEqual(final.usage.proposals, 6)
            self.assertGreater(lab.ledger.verify().entry_count, 7)
            self.assertTrue(all("Public fixture" in item for item in proposer.feedback_seen))
            self.assertTrue(all("private" not in item.casefold() for item in proposer.feedback_seen))

            attempt_events = [
                entry.payload
                for entry in lab.ledger.load()
                if entry.payload.get("kind") == "recursive_lab_attempt"
            ]
            outcomes = [event["outcome"] for event in attempt_events]
            self.assertEqual(
                outcomes,
                ["seed", "accepted", "rejected", "rejected", "accepted", "rejected", "accepted"],
            )
            reasons = [event["reason_codes"] for event in attempt_events]
            self.assertIn("duplicate", reasons[2])
            self.assertIn("artifact_invalid", reasons[3])
            self.assertIn("proposer_error", reasons[5])

    def test_resume_reconstructs_champion_budget_and_feedback(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "lineage.jsonl"
            first = StrategyLab(
                proposer=FixtureSequenceProposer(),
                evaluator=FixtureStrategyEvaluator(),
                policy=AcceptancePolicy(min_gain=0.25),
                limits=limits(),
                ledger_path=ledger_path,
                run_seed=7,
            )
            first.initialize(baseline_strategy(), seed=7)
            expected = first.run(4)

            resumed = StrategyLab(
                proposer=FixtureSequenceProposer(),
                evaluator=FixtureStrategyEvaluator(),
                policy=AcceptancePolicy(min_gain=0.25),
                limits=limits(),
                ledger_path=ledger_path,
                run_seed=7,
            ).snapshot()
            self.assertEqual(resumed.champion.artifact_id, expected.champion.artifact_id)
            self.assertEqual(resumed.champion_private.utility, expected.champion_private.utility)
            self.assertEqual(resumed.usage, expected.usage)
            self.assertEqual(resumed.public_feedback, expected.public_feedback)
            self.assertEqual(resumed.ledger_head, expected.ledger_head)

    def test_proposal_budget_stops_without_an_unlogged_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = StrategyLab(
                proposer=FixtureSequenceProposer(),
                evaluator=FixtureStrategyEvaluator(),
                policy=AcceptancePolicy(min_gain=0.25),
                limits=limits(proposals=1, evaluations=10),
                ledger_path=Path(directory) / "lineage.jsonl",
            )
            lab.initialize(baseline_strategy())
            result = lab.run(10)
            self.assertEqual(result.attempts, 1)
            self.assertEqual(result.stopped_reason, "proposal_budget_exhausted")
            self.assertGreaterEqual(lab.ledger.verify().entry_count, 2)

    def test_private_evaluation_cannot_expose_feedback(self):
        evaluator = FixtureStrategyEvaluator()
        result = evaluator.evaluate(baseline_strategy(), split="private_selection", seed=0)
        self.assertEqual(result.public_feedback, "")

    def test_failed_evaluation_is_charged_and_logged(self):
        class FailingEvaluator(FixtureStrategyEvaluator):
            evaluator_digest = sha256_digest("test:FailingEvaluator:v1")

            def __init__(self):
                self.calls = 0

            def evaluate(self, artifact, *, split, seed):
                self.calls += 1
                if self.calls > 2:
                    raise MeteredOperationError(
                        "fixture evaluation failure", model_calls=1, tokens=13
                    )
                return super().evaluate(artifact, split=split, seed=seed)

        with tempfile.TemporaryDirectory() as directory:
            lab = StrategyLab(
                proposer=FixtureSequenceProposer(),
                evaluator=FailingEvaluator(),
                policy=AcceptancePolicy(min_gain=0.25),
                limits=limits(),
                ledger_path=Path(directory) / "lineage.jsonl",
            )
            lab.initialize(baseline_strategy())
            result = lab.run(1)
            event = [
                entry.payload
                for entry in lab.ledger.load()
                if entry.payload.get("kind") == "recursive_lab_attempt"
            ][-1]
            self.assertEqual(event["reason_codes"], ["evaluation_failed"])
            self.assertEqual(result.usage.evaluations, 3)
            self.assertEqual(result.usage.model_calls, 2)
            self.assertEqual(result.usage.tokens, 45)
            self.assertEqual(event["resource_usage"]["evaluations"], 1)
            self.assertEqual(event["resource_usage"]["proposals"], 1)

    def test_unmetered_provider_failure_closes_search_and_survives_resume(self):
        class UnmeteredProposer:
            name = "unmetered-proposer"
            proposer_digest = sha256_digest(name)

            def propose(self, parent, *, public_feedback, seed):
                raise RuntimeError("provider failed without a usage receipt")

        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "lineage.jsonl"
            lab = StrategyLab(
                proposer=UnmeteredProposer(),
                evaluator=FixtureStrategyEvaluator(),
                policy=AcceptancePolicy(min_gain=0.25),
                limits=limits(),
                ledger_path=ledger_path,
            )
            lab.initialize(baseline_strategy())
            result = lab.run(3)
            self.assertEqual(result.attempts, 1)
            self.assertEqual(result.stopped_reason, "usage_receipt_missing")
            event = [
                entry.payload
                for entry in lab.ledger.load()
                if entry.payload.get("kind") == "recursive_lab_attempt"
            ][-1]
            self.assertEqual(event["reason_codes"], ["proposer_error_unmetered"])

            resumed = StrategyLab(
                proposer=UnmeteredProposer(),
                evaluator=FixtureStrategyEvaluator(),
                policy=AcceptancePolicy(min_gain=0.25),
                limits=limits(),
                ledger_path=ledger_path,
            )
            with self.assertRaisesRegex(RuntimeError, "usage receipt"):
                resumed.run(1)

    def test_parent_and_candidate_are_paired_on_same_seed(self):
        class NeutralProposer:
            name = "neutral-proposer"
            proposer_digest = sha256_digest(name)

            def propose(self, parent, *, public_feedback, seed):
                artifact = parent.artifact.create(
                    system_instruction=parent.artifact.system_instruction,
                    planning_steps=(
                        *parent.artifact.planning_steps,
                        "Consider the requested behavior twice.",
                    ),
                    max_attempts=parent.artifact.max_attempts,
                    reflection=parent.artifact.reflection,
                )
                return ProposalResult(artifact.to_canonical_json())

        class SeedSensitiveEvaluator(FixtureStrategyEvaluator):
            evaluator_digest = sha256_digest("test:SeedSensitiveEvaluator:v1")

            def evaluate(self, artifact, *, split, seed):
                result = super().evaluate(artifact, split=split, seed=seed)
                return replace(result, utility=result.utility + seed)

        with tempfile.TemporaryDirectory() as directory:
            lab = StrategyLab(
                proposer=NeutralProposer(),
                evaluator=SeedSensitiveEvaluator(),
                policy=AcceptancePolicy(min_gain=0.1),
                limits=limits(),
                ledger_path=Path(directory) / "lineage.jsonl",
            )
            lab.initialize(baseline_strategy(), seed=0)
            result = lab.run(1)
            self.assertEqual(result.accepted_generations, 0)
            attempt = [
                entry.payload
                for entry in lab.ledger.load()
                if entry.payload.get("kind") == "recursive_lab_attempt"
            ][-1]
            self.assertEqual(attempt["reason_codes"], ["policy_rejected"])
            self.assertEqual(attempt["decision"]["utility_gain"], 0.0)
            self.assertEqual(
                attempt["private_evaluation"]["utility"],
                attempt["parent_private_evaluation"]["utility"],
            )

    def test_failed_development_gate_never_queries_private(self):
        class DevelopmentFailureEvaluator(FixtureStrategyEvaluator):
            evaluator_digest = sha256_digest("test:DevelopmentFailureEvaluator:v1")

            def __init__(self):
                self.splits = []

            def evaluate(self, artifact, *, split, seed):
                self.splits.append(split)
                result = super().evaluate(artifact, split=split, seed=seed)
                if len(self.splits) > 2 and split == "development":
                    return replace(result, correct=GateResult.failure("fixture failure"))
                return result

        evaluator = DevelopmentFailureEvaluator()
        with tempfile.TemporaryDirectory() as directory:
            lab = StrategyLab(
                proposer=FixtureSequenceProposer(),
                evaluator=evaluator,
                policy=AcceptancePolicy(min_gain=0.25),
                limits=limits(),
                ledger_path=Path(directory) / "lineage.jsonl",
            )
            lab.initialize(baseline_strategy())
            lab.run(1)
        self.assertEqual(evaluator.splits, ["development", "private_selection", "development"])

    def test_sealed_suite_requires_authorization_is_one_shot_and_closes_search(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = StrategyLab(
                proposer=FixtureSequenceProposer(),
                evaluator=FixtureStrategyEvaluator(),
                policy=AcceptancePolicy(min_gain=0.25),
                limits=limits(),
                ledger_path=Path(directory) / "lineage.jsonl",
            )
            strategy = baseline_strategy()
            lab.initialize(strategy)
            with self.assertRaises(PermissionError):
                lab.evaluate_sealed(strategy, seed=0)
            first = lab.evaluate_sealed(
                strategy, seed=0, authorize_milestone=True
            )
            self.assertIs(lab.sealed_result(strategy.artifact_id), first)
            with self.assertRaisesRegex(RuntimeError, "already consumed"):
                lab.evaluate_sealed(strategy, seed=0, authorize_milestone=True)
            with self.assertRaisesRegex(RuntimeError, "search is closed"):
                lab.run(1)

    def test_failed_sealed_query_is_logged_consumed_and_closes_search(self):
        class FailingSealedEvaluator(FixtureStrategyEvaluator):
            evaluator_digest = sha256_digest("test:FailingSealedEvaluator:v1")

            def evaluate(self, artifact, *, split, seed):
                if split == "sealed_final":
                    raise RuntimeError("fixture sealed outage")
                return super().evaluate(artifact, split=split, seed=seed)

        with tempfile.TemporaryDirectory() as directory:
            strategy = baseline_strategy()
            lab = StrategyLab(
                proposer=FixtureSequenceProposer(),
                evaluator=FailingSealedEvaluator(),
                policy=AcceptancePolicy(min_gain=0.25),
                limits=limits(),
                ledger_path=Path(directory) / "lineage.jsonl",
            )
            lab.initialize(strategy)
            with self.assertRaisesRegex(RuntimeError, "query was consumed"):
                lab.evaluate_sealed(
                    strategy, seed=37, authorize_milestone=True
                )
            with self.assertRaisesRegex(RuntimeError, "already consumed"):
                lab.evaluate_sealed(
                    strategy, seed=37, authorize_milestone=True
                )
            with self.assertRaisesRegex(RuntimeError, "search is closed"):
                lab.run(1)

            audit = [
                entry.payload
                for entry in lab.ledger.load()
                if entry.payload.get("kind") == "recursive_lab_audit"
            ][-1]
            self.assertEqual(audit["outcome"], "failed")
            self.assertEqual(audit["seed"], 37)
            self.assertIsNone(audit["evaluation"])
            self.assertEqual(audit["failure"]["error_type"], "RuntimeError")

    def test_artifact_evaluation_rejects_string_and_boolean_utility(self):
        base = FixtureStrategyEvaluator().evaluate(
            baseline_strategy(), split="development", seed=0
        )
        payload = base.to_payload()
        for invalid in ("1.0", True):
            with self.subTest(invalid=invalid):
                payload["utility"] = invalid
                with self.assertRaises(TypeError):
                    ArtifactEvaluation.from_payload(payload)

    def test_correct_gate_cannot_contradict_failed_task_results(self):
        evaluation = FixtureStrategyEvaluator().evaluate(
            baseline_strategy(), split="development", seed=0
        )
        with self.assertRaisesRegex(ValueError, "per-task"):
            replace(
                evaluation,
                per_task_results=(False,) * evaluation.task_count,
            )

    def test_resume_refuses_frozen_configuration_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "lineage.jsonl"
            lab = StrategyLab(
                proposer=FixtureSequenceProposer(),
                evaluator=FixtureStrategyEvaluator(),
                policy=AcceptancePolicy(min_gain=0.25),
                limits=limits(),
                ledger_path=ledger_path,
                run_seed=9,
            )
            lab.initialize(baseline_strategy(), seed=9)

            with self.assertRaises(ManifestDriftError) as raised:
                StrategyLab(
                    proposer=FixtureSequenceProposer(),
                    evaluator=FixtureStrategyEvaluator(),
                    policy=AcceptancePolicy(min_gain=0.5),
                    limits=limits(),
                    ledger_path=ledger_path,
                    run_seed=9,
                )
            self.assertIn("acceptance_policy", raised.exception.differing_fields)

    def test_nonempty_ledger_cannot_resume_without_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "lineage.jsonl"
            lab = StrategyLab(
                proposer=FixtureSequenceProposer(),
                evaluator=FixtureStrategyEvaluator(),
                policy=AcceptancePolicy(min_gain=0.25),
                limits=limits(),
                ledger_path=ledger_path,
            )
            lab.initialize(baseline_strategy())
            Path(f"{ledger_path}.manifest.json").unlink()

            with self.assertRaises(ManifestIntegrityError):
                StrategyLab(
                    proposer=FixtureSequenceProposer(),
                    evaluator=FixtureStrategyEvaluator(),
                    policy=AcceptancePolicy(min_gain=0.25),
                    limits=limits(),
                    ledger_path=ledger_path,
                )

    def test_failed_paired_parent_control_blocks_promotion(self):
        class ParentControlFailure(FixtureStrategyEvaluator):
            evaluator_digest = sha256_digest("test:ParentControlFailure:v1")

            def evaluate(self, artifact, *, split, seed):
                result = super().evaluate(artifact, split=split, seed=seed)
                text = " ".join(artifact.planning_steps).casefold()
                if split == "private_selection" and seed > 0 and "reproduce" not in text:
                    return replace(
                        result,
                        evaluator_integrity=GateResult.failure(
                            "paired fixture control failure"
                        ),
                    )
                return result

        with tempfile.TemporaryDirectory() as directory:
            lab = StrategyLab(
                proposer=FixtureSequenceProposer(),
                evaluator=ParentControlFailure(),
                policy=AcceptancePolicy(min_gain=0.25),
                limits=limits(),
                ledger_path=Path(directory) / "lineage.jsonl",
            )
            result = lab.initialize(baseline_strategy())
            self.assertEqual(result.accepted_generations, 0)
            result = lab.run(1)
            self.assertEqual(result.accepted_generations, 0)
            attempt = [
                entry.payload
                for entry in lab.ledger.load()
                if entry.payload.get("kind") == "recursive_lab_attempt"
            ][-1]
            reasons = attempt["decision"]["reasons"]
            self.assertTrue(any("paired parent control" in reason for reason in reasons))

    def test_resume_preserves_canonical_provenance_after_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "lineage.jsonl"
            first = StrategyLab(
                proposer=FixtureSequenceProposer(),
                evaluator=FixtureStrategyEvaluator(),
                policy=AcceptancePolicy(min_gain=0.25),
                limits=limits(),
                ledger_path=ledger_path,
            )
            first.initialize(baseline_strategy())
            champion = first.run(2).champion

            resumed = StrategyLab(
                proposer=FixtureSequenceProposer(),
                evaluator=FixtureStrategyEvaluator(),
                policy=AcceptancePolicy(min_gain=0.25),
                limits=limits(),
                ledger_path=ledger_path,
            )
            resumed.evaluate_sealed(
                champion.artifact, seed=23, authorize_milestone=True
            )
            audit = [
                entry.payload
                for entry in resumed.ledger.load()
                if entry.payload.get("kind") == "recursive_lab_audit"
            ][-1]
            audited_record = audit["artifact_record"]
            self.assertEqual(audited_record["generation"], champion.generation)
            self.assertEqual(audited_record["parent_id"], champion.parent_id)
            self.assertNotEqual(audited_record["parent_id"], champion.artifact_id)

    def test_frozen_policy_cannot_be_reassigned_or_silently_mutated(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = StrategyLab(
                proposer=FixtureSequenceProposer(),
                evaluator=FixtureStrategyEvaluator(),
                policy=AcceptancePolicy(min_gain=0.25),
                limits=limits(),
                ledger_path=Path(directory) / "lineage.jsonl",
            )
            lab.initialize(baseline_strategy())
            with self.assertRaises(AttributeError):
                lab.policy = AcceptancePolicy(min_gain=0.0)
            lab._policy = AcceptancePolicy(min_gain=0.0)
            with self.assertRaisesRegex(RuntimeError, "policy drifted"):
                lab.run(1)


if __name__ == "__main__":
    unittest.main()
