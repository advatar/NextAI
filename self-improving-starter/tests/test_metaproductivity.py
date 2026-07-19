from __future__ import annotations

import math
import sys
import unittest
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from recursive_lab.metaproductivity import (  # noqa: E402
    CostWeights,
    EvaluatorMetadata,
    ExperimentBudget,
    ExternalEvaluation,
    ExternalEvaluationError,
    ImprovementRun,
    MIN_BOOTSTRAP_SAMPLES,
    MIN_EVIDENCE_PAIRS,
    ResourceUse,
    run_tournament,
)


@dataclass
class AddImprover:
    name: str
    amount: float
    model_calls: int = 1
    log: list[str] | None = None

    def improve(self, seed_artifact, *, trial_seed, budget):
        if self.log is not None:
            self.log.append(self.name)
        return ImprovementRun(
            successor=seed_artifact + self.amount,
            usage=ResourceUse(
                proposals=1,
                model_calls=self.model_calls,
                tokens=10,
                wall_seconds=0.25,
            ),
            detail=f"matched seed {trial_seed}",
        )


@dataclass
class NumericEvaluator:
    evidence_class: str = "fixture"
    bad_gate: str | None = None
    bad_at_or_above: float = math.inf
    evaluation_use: ResourceUse = ResourceUse(
        evaluations=1, model_calls=1, tokens=5, wall_seconds=0.1
    )
    calls: list[tuple[float, str, int]] = field(default_factory=list)

    @property
    def metadata(self):
        return EvaluatorMetadata("fixture.numeric.external.v2", self.evidence_class)

    def evaluate(self, artifact, *, split: str, trial_seed: int):
        value = float(artifact)
        self.calls.append((value, split, trial_seed))
        gates = {
            "artifact_valid": True,
            "correct": True,
            "safety_preserved": True,
            "evaluator_integrity": True,
            "resource_compliance": True,
        }
        if value >= self.bad_at_or_above and self.bad_gate is not None:
            gates[self.bad_gate] = False
        # Seed-dependent noise cancels only because both seed and successor are
        # externally evaluated with the same matched trial seed.
        return ExternalEvaluation(
            utility=value + trial_seed / 10_000,
            usage=self.evaluation_use,
            detail="external deterministic measurement",
            **gates,
        )


class FloatReturningEvaluator:
    metadata = EvaluatorMetadata("dishonest.float-return.v1", "empirical")

    def evaluate(self, artifact, *, split: str, trial_seed: int):
        return float(artifact)


class NonfiniteEvaluator:
    metadata = EvaluatorMetadata("dishonest.nonfinite.v1", "empirical")

    def evaluate(self, artifact, *, split: str, trial_seed: int):
        return ExternalEvaluation(
            utility=math.nan,
            usage=ResourceUse(evaluations=1),
            artifact_valid=True,
            correct=True,
            safety_preserved=True,
            evaluator_integrity=True,
            resource_compliance=True,
        )


class MeteredFailingEvaluator:
    metadata = EvaluatorMetadata("metered.failure.v1", "empirical")

    def evaluate(self, artifact, *, split: str, trial_seed: int):
        raise ExternalEvaluationError(
            "provider failed after work",
            usage=ResourceUse(evaluations=1, model_calls=1, tokens=7),
        )


@dataclass
class PatternImprover:
    name: str
    gains: dict[int, float]

    def improve(self, seed_artifact, *, trial_seed, budget):
        return ImprovementRun(
            successor=seed_artifact + self.gains[trial_seed],
            usage=ResourceUse(proposals=1, model_calls=1, tokens=10),
        )


class MetaproductivityTests(unittest.TestCase):
    def setUp(self):
        self.budget = ExperimentBudget(1, 2, 3, 20, 1.0)
        self.weights = CostWeights(
            proposal=1,
            evaluation=1,
            model_call=1,
            token=0,
            wall_second=0,
        )
        self.seeds = [0, 10, -5, 2, 8]
        self.trial_seeds = [101, 102, 103, 104, 105]

    def tournament(self, **overrides):
        values = {
            "ancestor": AddImprover("ancestor", 1),
            "descendant": AddImprover("descendant", 3),
            "seed_artifacts": self.seeds,
            "trial_seeds": self.trial_seeds,
            "evaluator": NumericEvaluator(),
            "budget": self.budget,
            "cost_weights": self.weights,
            "effect_threshold": 0.1,
            "bootstrap_samples": 1000,
            "bootstrap_seed": 7,
        }
        values.update(overrides)
        return run_tournament(**values)

    def test_descendant_with_larger_equal_cost_uplift_passes(self):
        report = self.tournament()
        self.assertEqual(report.verdict, "passes_threshold")
        self.assertEqual(report.valid_pairs, MIN_EVIDENCE_PAIRS)
        self.assertGreater(report.confidence_low, report.effect_threshold)
        self.assertTrue(report.fixture_only)
        self.assertEqual(report.evidence_class, "fixture")
        self.assertEqual(report.schema, "recursive-lab.metaproductivity-report.v2")
        self.assertEqual(report.bootstrap_samples, 1000)
        self.assertEqual(report.bootstrap_seed, 7)
        self.assertEqual(len({trial.seed_artifact_id for trial in report.trials}), 5)

    def test_evidence_class_and_fixture_flag_come_from_evaluator(self):
        report = self.tournament(evaluator=NumericEvaluator(evidence_class="empirical"))
        self.assertEqual(report.evidence_class, "empirical")
        self.assertFalse(report.fixture_only)
        payload = report.to_dict()
        self.assertEqual(payload["summary"]["evidence_class"], "empirical")
        self.assertFalse(payload["summary"]["fixture_only"])

    def test_raw_improver_and_both_evaluator_costs_are_retained(self):
        report = self.tournament()
        arm = report.trials[0].ancestor
        self.assertEqual(arm.improver_usage.proposals, 1)
        self.assertEqual(arm.seed_evaluation_usage.evaluations, 1)
        self.assertEqual(arm.successor_evaluation_usage.evaluations, 1)
        self.assertEqual(arm.total_usage.evaluations, 2)
        self.assertEqual(arm.total_usage.model_calls, 3)
        self.assertEqual(arm.total_usage.tokens, 20)
        self.assertEqual(arm.cost_units, 6)
        payload = arm.to_dict()["usage"]
        self.assertEqual(payload["total"]["evaluations"], 2)
        self.assertEqual(payload["seed_evaluation"]["model_calls"], 1)

    def test_matched_trial_seed_reaches_every_decisive_evaluation(self):
        evaluator = NumericEvaluator()
        self.tournament(evaluator=evaluator)
        for trial_seed in self.trial_seeds:
            calls = [call for call in evaluator.calls if call[2] == trial_seed]
            self.assertEqual(len(calls), 4)  # seed + successor for both arms
            self.assertTrue(all(call[1] == "sealed_final" for call in calls))

    def test_arm_order_is_counterbalanced(self):
        order: list[str] = []
        report = self.tournament(
            ancestor=AddImprover("ancestor", 1, log=order),
            descendant=AddImprover("descendant", 3, log=order),
        )
        self.assertEqual(
            [trial.evaluation_order for trial in report.trials],
            [
                ("ancestor", "descendant"),
                ("descendant", "ancestor"),
                ("ancestor", "descendant"),
                ("descendant", "ancestor"),
                ("ancestor", "descendant"),
            ],
        )
        self.assertEqual(
            order,
            [
                "ancestor",
                "descendant",
                "descendant",
                "ancestor",
                "ancestor",
                "descendant",
                "descendant",
                "ancestor",
                "ancestor",
                "descendant",
            ],
        )

    def test_each_external_gate_independently_invalidates_the_pair(self):
        for gate in (
            "artifact_valid",
            "correct",
            "safety_preserved",
            "evaluator_integrity",
            "resource_compliance",
        ):
            with self.subTest(gate=gate):
                report = self.tournament(
                    descendant=AddImprover("descendant", 100),
                    evaluator=NumericEvaluator(bad_gate=gate, bad_at_or_above=50),
                )
                self.assertEqual(report.verdict, "invalid")
                self.assertEqual(report.valid_pairs, 0)
                self.assertIn(
                    f"successor_{gate}_failed",
                    report.trials[0].descendant.reasons,
                )

    def test_improver_cannot_self_attest_decisive_gates(self):
        with self.assertRaises(TypeError):
            ImprovementRun(  # type: ignore[call-arg]
                successor=1,
                usage=ResourceUse(proposals=1),
                safety_preserved=True,
            )

    def test_external_evaluator_must_return_typed_measurement(self):
        report = self.tournament(evaluator=FloatReturningEvaluator())
        self.assertEqual(report.verdict, "invalid")
        self.assertEqual(report.valid_pairs, 0)
        self.assertIn("seed_evaluation_error:TypeError", report.trials[0].ancestor.reasons[0])
        self.assertEqual(report.trials[0].ancestor.seed_evaluation_usage.evaluations, 1)

    def test_failed_external_evaluation_retains_reported_resource_use(self):
        report = self.tournament(evaluator=MeteredFailingEvaluator())
        arm = report.trials[0].ancestor
        self.assertEqual(report.verdict, "invalid")
        self.assertEqual(arm.seed_evaluation_usage.evaluations, 1)
        self.assertEqual(arm.seed_evaluation_usage.model_calls, 1)
        self.assertEqual(arm.seed_evaluation_usage.tokens, 7)
        self.assertEqual(arm.total_usage.tokens, 17)

    def test_nonfinite_external_utility_fails_closed(self):
        report = self.tournament(evaluator=NonfiniteEvaluator())
        self.assertEqual(report.verdict, "invalid")
        self.assertIn("utility must be finite", report.trials[0].ancestor.reasons[0])

    def test_external_call_cannot_claim_zero_evaluations(self):
        with self.assertRaises(ValueError):
            ExternalEvaluation(
                utility=1,
                usage=ResourceUse(),
                artifact_valid=True,
                correct=True,
                safety_preserved=True,
                evaluator_integrity=True,
                resource_compliance=True,
            )

    def test_budget_includes_both_external_evaluator_calls(self):
        expensive = NumericEvaluator(
            evaluation_use=ResourceUse(evaluations=1, model_calls=2)
        )
        report = self.tournament(evaluator=expensive)
        self.assertEqual(report.verdict, "invalid")
        self.assertIn("total_budget_exceeded", report.trials[0].ancestor.reasons)
        self.assertEqual(report.trials[0].ancestor.total_usage.model_calls, 5)

    def test_zero_or_single_evaluation_budget_is_rejected_before_work(self):
        for maximum in (0, 1):
            with self.subTest(maximum=maximum), self.assertRaises(ValueError):
                self.tournament(
                    budget=ExperimentBudget(1, maximum, 3, 20, 1.0)
                )

    def test_count_values_are_exact_nonnegative_integers(self):
        for bad in (True, 0.5, "1"):
            with self.subTest(kind="budget", bad=bad), self.assertRaises(TypeError):
                ExperimentBudget(bad, 2, 3, 20, 1.0)  # type: ignore[arg-type]
            with self.subTest(kind="usage", bad=bad), self.assertRaises(TypeError):
                ResourceUse(proposals=bad)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            ResourceUse(tokens=-1)

    def test_at_least_five_pairs_are_required(self):
        with self.assertRaisesRegex(ValueError, "at least 5"):
            self.tournament(
                seed_artifacts=self.seeds[:4],
                trial_seeds=self.trial_seeds[:4],
            )

    def test_duplicate_trial_seeds_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "unique"):
            self.tournament(trial_seeds=[101, 102, 103, 104, 101])

    def test_trial_seed_must_be_an_exact_nonnegative_integer(self):
        with self.assertRaises(TypeError):
            self.tournament(trial_seeds=[101, 102, 103, 104, 1.5])
        with self.assertRaises(ValueError):
            self.tournament(trial_seeds=[101, 102, 103, 104, -1])

    def test_effect_threshold_must_be_strictly_positive(self):
        for threshold in (0, -0.1, math.inf, math.nan):
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                self.tournament(effect_threshold=threshold)

    def test_bootstrap_requires_a_defensible_minimum_sample_count(self):
        for samples in (True, 1, MIN_BOOTSTRAP_SAMPLES - 1):
            with self.subTest(samples=samples), self.assertRaises((TypeError, ValueError)):
                self.tournament(bootstrap_samples=samples)

    def test_pass_requires_observed_mean_to_exceed_threshold(self):
        gains = {
            101: 6.0,
            102: 6.0,
            103: 6.0,
            104: 6.0,
            105: -600.0,
        }
        report = self.tournament(
            ancestor=PatternImprover("ancestor", {seed: 0.0 for seed in gains}),
            descendant=PatternImprover("descendant", gains),
            bootstrap_seed=2,
        )
        self.assertLess(report.mean_delta, 0)
        self.assertNotEqual(report.verdict, "passes_threshold")

    def test_repeated_seed_artifacts_are_not_counted_as_independent_evidence(self):
        with self.assertRaisesRegex(ValueError, "pseudo-replicates"):
            self.tournament(seed_artifacts=[0] * MIN_EVIDENCE_PAIRS)

    def test_evaluator_metadata_is_required_and_validated(self):
        class MissingMetadata:
            def evaluate(self, artifact, *, split, trial_seed):  # pragma: no cover
                raise AssertionError

        with self.assertRaises(TypeError):
            self.tournament(evaluator=MissingMetadata())
        with self.assertRaises(ValueError):
            EvaluatorMetadata("evaluator", "marketing-demo")  # type: ignore[arg-type]

    def test_report_is_inconclusive_when_interval_straddles_threshold(self):
        report = self.tournament(effect_threshold=1.0)
        self.assertEqual(report.verdict, "fails_threshold")
        self.assertLess(report.confidence_high, 1.0)


if __name__ == "__main__":
    unittest.main()
