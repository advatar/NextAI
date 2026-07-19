from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
import math
import unittest

from recursive_lab.governance import (
    AcceptancePolicy,
    BudgetAccount,
    BudgetExceeded,
    BudgetLimits,
    BudgetUsage,
    EvaluationEvidence,
    GateResult,
    PromotionDecision,
)


def passing_evidence(*, utility_gain: float = 1.0, **overrides: GateResult) -> EvaluationEvidence:
    gates = {
        "artifact_valid": GateResult.success(),
        "correct": GateResult.success(),
        "safety_preserved": GateResult.success(),
        "evaluator_integrity": GateResult.success(),
        "resource_compliance": GateResult.success(),
    }
    gates.update(overrides)
    return EvaluationEvidence(**gates, utility_gain=utility_gain)


class BudgetValueTests(unittest.TestCase):
    def test_limits_and_usage_are_immutable_and_round_trip(self) -> None:
        limits = BudgetLimits(3, 4, 5, 600, 7.5)
        usage = BudgetUsage(1, 2, 3, 400, 5.25)

        self.assertEqual(BudgetLimits.from_dict(limits.to_dict()), limits)
        self.assertEqual(BudgetUsage.from_dict(usage.to_dict()), usage)
        json.dumps(limits.to_dict(), allow_nan=False)
        json.dumps(usage.to_dict(), allow_nan=False)
        with self.assertRaises(FrozenInstanceError):
            limits.proposals = 10  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            usage.tokens = 10  # type: ignore[misc]

    def test_count_fields_reject_negative_non_integer_and_boolean_values(self) -> None:
        valid = dict(proposals=1, evaluations=1, model_calls=1, tokens=1, wall_seconds=1.0)
        for field in ("proposals", "evaluations", "model_calls", "tokens"):
            for invalid in (-1, 1.5, True, "1"):
                with self.subTest(field=field, invalid=invalid):
                    values = dict(valid)
                    values[field] = invalid
                    with self.assertRaises((TypeError, ValueError)):
                        BudgetLimits(**values)
                    with self.assertRaises((TypeError, ValueError)):
                        BudgetUsage(**values)

    def test_wall_budget_rejects_negative_and_non_finite_values(self) -> None:
        for invalid in (-0.1, math.nan, math.inf, -math.inf, True, "1"):
            with self.subTest(invalid=invalid):
                with self.assertRaises((TypeError, ValueError)):
                    BudgetLimits(1, 1, 1, 1, invalid)  # type: ignore[arg-type]
                with self.assertRaises((TypeError, ValueError)):
                    BudgetUsage(wall_seconds=invalid)  # type: ignore[arg-type]

    def test_deserialization_rejects_missing_and_extra_fields(self) -> None:
        with self.assertRaises(ValueError):
            BudgetUsage.from_dict({})
        payload = BudgetLimits(1, 1, 1, 1, 1).to_dict()
        payload["money"] = 1
        with self.assertRaises(ValueError):
            BudgetLimits.from_dict(payload)


class BudgetAccountTests(unittest.TestCase):
    def setUp(self) -> None:
        self.limits = BudgetLimits(
            proposals=2,
            evaluations=3,
            model_calls=4,
            tokens=100,
            wall_seconds=10.0,
        )

    def test_records_all_dimensions_and_allows_exact_boundary(self) -> None:
        account = BudgetAccount(self.limits)
        result = account.charge(
            proposals=2,
            evaluations=3,
            model_calls=4,
            tokens=100,
            wall_seconds=10.0,
        )

        self.assertEqual(result, BudgetUsage(2, 3, 4, 100, 10.0))
        self.assertEqual(account.usage, result)
        self.assertTrue(account.compliant)
        self.assertFalse(account.breached)
        self.assertTrue(account.exhausted)
        self.assertEqual(account.remaining(), BudgetUsage())
        self.assertTrue(account.compliance_gate().passed)

    def test_convenience_methods_count_failed_or_successful_work(self) -> None:
        account = BudgetAccount(self.limits)
        account.record_proposal(wall_seconds=1.0)
        account.record_evaluation(wall_seconds=2.0)
        account.record_model_call(tokens=17, wall_seconds=3.0)

        self.assertEqual(account.usage, BudgetUsage(1, 1, 1, 17, 6.0))

    def test_each_independent_dimension_fails_closed_on_overrun(self) -> None:
        cases = {
            "proposals": dict(proposals=3),
            "evaluations": dict(evaluations=4),
            "model_calls": dict(model_calls=5),
            "tokens": dict(tokens=101),
            "wall_seconds": dict(wall_seconds=10.01),
        }
        for dimension, charge in cases.items():
            with self.subTest(dimension=dimension):
                account = BudgetAccount(self.limits)
                with self.assertRaises(BudgetExceeded) as caught:
                    account.charge(**charge)
                self.assertTrue(caught.exception.committed)
                self.assertEqual(caught.exception.dimensions, (dimension,))
                self.assertEqual(getattr(account.usage, dimension), charge[dimension])
                self.assertTrue(account.breached)
                gate = account.compliance_gate()
                self.assertFalse(gate.passed)
                self.assertIn(dimension, gate.reason)

    def test_multi_dimension_overrun_reports_every_failure_without_averaging(self) -> None:
        account = BudgetAccount(self.limits)
        with self.assertRaises(BudgetExceeded) as caught:
            account.charge(proposals=9, tokens=999, wall_seconds=99)
        self.assertEqual(
            caught.exception.dimensions,
            ("proposals", "tokens", "wall_seconds"),
        )
        json.dumps(caught.exception.to_dict(), allow_nan=False)

    def test_preflight_overrun_does_not_mutate_but_charge_overrun_does(self) -> None:
        account = BudgetAccount(self.limits)
        before = account.snapshot()
        with self.assertRaises(BudgetExceeded) as projected:
            account.ensure_available(tokens=101)
        self.assertFalse(projected.exception.committed)
        self.assertEqual(account.snapshot(), before)

        with self.assertRaises(BudgetExceeded) as recorded:
            account.charge(tokens=101)
        self.assertTrue(recorded.exception.committed)
        self.assertEqual(account.usage.tokens, 101)

    def test_breached_account_stays_closed_and_continues_accounting(self) -> None:
        account = BudgetAccount(self.limits)
        with self.assertRaises(BudgetExceeded):
            account.charge(proposals=3)
        with self.assertRaises(BudgetExceeded):
            account.charge(evaluations=1)
        self.assertEqual(account.usage, BudgetUsage(proposals=3, evaluations=1))
        self.assertFalse(account.can_charge())

    def test_invalid_charge_never_mutates_usage(self) -> None:
        account = BudgetAccount(self.limits)
        for invalid in (-1.0, math.nan, math.inf):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    account.charge(wall_seconds=invalid)
                self.assertEqual(account.usage, BudgetUsage())
        with self.assertRaises(ValueError):
            account.charge(BudgetUsage(tokens=1), tokens=1)
        self.assertEqual(account.usage, BudgetUsage())

    def test_zero_limit_is_compliant_but_exhausted_until_usage_occurs(self) -> None:
        account = BudgetAccount(BudgetLimits(0, 0, 0, 0, 0))
        self.assertTrue(account.compliant)
        self.assertTrue(account.exhausted)
        self.assertTrue(account.can_charge())
        with self.assertRaises(BudgetExceeded):
            account.record_proposal()
        self.assertFalse(account.compliant)

    def test_initial_overrun_restores_as_closed_account(self) -> None:
        account = BudgetAccount(self.limits, BudgetUsage(tokens=101))
        self.assertTrue(account.breached)
        with self.assertRaises(BudgetExceeded):
            account.charge()


class GateAndEvidenceTests(unittest.TestCase):
    def test_failed_gate_requires_an_explicit_reason(self) -> None:
        with self.assertRaises(ValueError):
            GateResult(False)
        with self.assertRaises(ValueError):
            GateResult.failure("   ")

    def test_gate_and_evidence_round_trip(self) -> None:
        evidence = passing_evidence(
            utility_gain=0.25,
            correct=GateResult.failure("hidden test failed"),
        )
        restored = EvaluationEvidence.from_dict(evidence.to_dict())
        self.assertEqual(restored, evidence)
        json.dumps(evidence.to_dict(), allow_nan=False)

    def test_non_finite_evidence_is_strict_json_serializable(self) -> None:
        for gain, marker in (
            (math.nan, "NaN"),
            (math.inf, "Infinity"),
            (-math.inf, "-Infinity"),
        ):
            with self.subTest(gain=gain):
                evidence = passing_evidence(utility_gain=gain)
                payload = evidence.to_dict()
                self.assertEqual(payload["utility_gain"], marker)
                json.dumps(payload, allow_nan=False)
                restored = EvaluationEvidence.from_dict(payload)
                if math.isnan(gain):
                    self.assertTrue(math.isnan(restored.utility_gain))
                else:
                    self.assertEqual(restored.utility_gain, gain)


class AcceptancePolicyTests(unittest.TestCase):
    def test_all_gates_and_exact_minimum_gain_promote(self) -> None:
        policy = AcceptancePolicy(min_gain=0.25)
        decision = policy.decide(passing_evidence(utility_gain=0.25))

        self.assertTrue(decision.promoted)
        self.assertTrue(decision.accepted)
        self.assertFalse(decision.rejected)
        self.assertEqual(decision.reasons, ())
        self.assertEqual(
            decision.to_dict(),
            {
                "promoted": True,
                "utility_gain": 0.25,
                "min_gain": 0.25,
                "reasons": [],
            },
        )
        self.assertEqual(AcceptancePolicy.from_dict(policy.to_dict()), policy)
        self.assertEqual(PromotionDecision.from_dict(decision.to_dict()), decision)

    def test_gain_below_boundary_is_rejected_explicitly(self) -> None:
        decision = AcceptancePolicy(min_gain=0.25).decide(
            passing_evidence(utility_gain=0.249999)
        )
        self.assertFalse(decision.promoted)
        self.assertEqual(len(decision.reasons), 1)
        self.assertIn("below required minimum", decision.reasons[0])

    def test_non_finite_gains_always_fail_closed(self) -> None:
        policy = AcceptancePolicy(min_gain=0.0)
        for gain, marker in (
            (math.nan, "NaN"),
            (math.inf, "Infinity"),
            (-math.inf, "-Infinity"),
        ):
            with self.subTest(gain=gain):
                decision = policy.decide(passing_evidence(utility_gain=gain))
                self.assertFalse(decision.promoted)
                self.assertIn("not finite", decision.reasons[-1])
                self.assertEqual(decision.to_dict()["utility_gain"], marker)
                json.dumps(decision.to_dict(), allow_nan=False)

    def test_every_gate_is_independently_required_even_with_huge_score(self) -> None:
        policy = AcceptancePolicy(min_gain=0.01)
        for gate_name in EvaluationEvidence.GATE_NAMES:
            with self.subTest(gate=gate_name):
                decision = policy.decide(
                    passing_evidence(
                        utility_gain=1e300,
                        **{gate_name: GateResult.failure("deliberate failure")},
                    )
                )
                self.assertFalse(decision.promoted)
                self.assertEqual(len(decision.reasons), 1)
                self.assertTrue(decision.reasons[0].startswith(f"{gate_name} failed:"))

    def test_unsafe_high_score_cannot_compensate_for_safety_regression(self) -> None:
        decision = AcceptancePolicy(min_gain=1.0).decide(
            passing_evidence(
                utility_gain=1e308,
                safety_preserved=GateResult.failure("credential exfiltration detected"),
            )
        )
        self.assertFalse(decision.promoted)
        self.assertEqual(
            decision.reasons,
            ("safety_preserved failed: credential exfiltration detected",),
        )

    def test_multiple_gate_failures_are_all_reported(self) -> None:
        decision = AcceptancePolicy(min_gain=2.0).decide(
            passing_evidence(
                utility_gain=1.0,
                artifact_valid=GateResult.failure("schema mismatch"),
                correct=GateResult.failure("wrong answer"),
                evaluator_integrity=GateResult.failure("private test read"),
            )
        )
        self.assertEqual(len(decision.reasons), 4)
        self.assertIn("artifact_valid failed", decision.reasons[0])
        self.assertIn("correct failed", decision.reasons[1])
        self.assertIn("evaluator_integrity failed", decision.reasons[2])
        self.assertIn("below required minimum", decision.reasons[3])

    def test_policy_rejects_negative_and_non_finite_thresholds(self) -> None:
        for invalid in (-0.01, math.nan, math.inf, -math.inf, True):
            with self.subTest(invalid=invalid):
                with self.assertRaises((TypeError, ValueError)):
                    AcceptancePolicy(invalid)  # type: ignore[arg-type]

    def test_decision_invariants_prevent_ambiguous_records(self) -> None:
        with self.assertRaises(ValueError):
            PromotionDecision(True, 1.0, 0.0, ("contradiction",))
        with self.assertRaises(ValueError):
            PromotionDecision(False, 1.0, 0.0, ())


if __name__ == "__main__":
    unittest.main()
