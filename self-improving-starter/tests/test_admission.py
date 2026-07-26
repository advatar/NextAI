from __future__ import annotations

import hashlib
import json
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from recursive_lab.admission import (  # noqa: E402
    AdmissionCriteria,
    AdmissionResult,
    BenchmarkNotAdmittedError,
    CohortObservations,
    admit_cohort,
    evaluate_admission,
    require_admitted,
)


def observations(
    *,
    exploration_target_rate: float = 0.0,
    policy_disagreements: int = 4,
    tasks: int = 8,
) -> CohortObservations:
    return CohortObservations(
        exploration_target_rate=exploration_target_rate,
        policy_disagreements=policy_disagreements,
        tasks=tasks,
    )


class AdmissionCriteriaTests(unittest.TestCase):
    def test_defaults_match_the_preregistered_thresholds(self) -> None:
        criteria = AdmissionCriteria()

        self.assertEqual(criteria.maximum_exploration_target_rate, 0.2)
        self.assertEqual(criteria.minimum_tasks, 5)
        self.assertEqual(criteria.minimum_policy_disagreements, 3)

    def test_criteria_are_frozen_and_round_trip(self) -> None:
        criteria = AdmissionCriteria(
            maximum_exploration_target_rate=0.1,
            minimum_tasks=12,
            minimum_policy_disagreements=4,
        )

        self.assertEqual(AdmissionCriteria.from_dict(criteria.to_dict()), criteria)
        json.dumps(criteria.to_dict(), allow_nan=False)
        with self.assertRaises(FrozenInstanceError):
            criteria.minimum_tasks = 1  # type: ignore[misc]

    def test_rate_outside_unit_interval_is_rejected(self) -> None:
        for bad_rate in (-0.01, 1.5):
            with self.subTest(rate=bad_rate), self.assertRaises(ValueError):
                AdmissionCriteria(maximum_exploration_target_rate=bad_rate)

    def test_non_finite_rate_is_rejected(self) -> None:
        for bad_rate in (float("nan"), float("inf")):
            with self.subTest(rate=bad_rate), self.assertRaises(ValueError):
                AdmissionCriteria(maximum_exploration_target_rate=bad_rate)

    def test_non_numeric_rate_is_a_type_error(self) -> None:
        with self.assertRaises(TypeError):
            AdmissionCriteria(maximum_exploration_target_rate="0.2")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            AdmissionCriteria(maximum_exploration_target_rate=True)  # type: ignore[arg-type]

    def test_non_positive_counts_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            AdmissionCriteria(minimum_tasks=0)
        with self.assertRaises(ValueError):
            AdmissionCriteria(minimum_policy_disagreements=0)
        with self.assertRaises(ValueError):
            AdmissionCriteria(minimum_tasks=-3)

    def test_non_integer_counts_are_a_type_error(self) -> None:
        with self.assertRaises(TypeError):
            AdmissionCriteria(minimum_tasks=5.0)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            AdmissionCriteria(minimum_policy_disagreements=True)  # type: ignore[arg-type]

    def test_unsatisfiable_criteria_are_rejected(self) -> None:
        with self.assertRaises(ValueError) as caught:
            AdmissionCriteria(minimum_tasks=2, minimum_policy_disagreements=3)

        self.assertIn("cannot exceed minimum_tasks", str(caught.exception))

    def test_from_dict_requires_exact_keys(self) -> None:
        payload = AdmissionCriteria().to_dict()
        payload["unexpected"] = 1
        with self.assertRaises(ValueError):
            AdmissionCriteria.from_dict(payload)
        with self.assertRaises(ValueError):
            AdmissionCriteria.from_dict({"minimum_tasks": 5})


class CohortObservationTests(unittest.TestCase):
    def test_observations_round_trip_and_are_frozen(self) -> None:
        observed = observations(exploration_target_rate=0.125)

        self.assertEqual(CohortObservations.from_dict(observed.to_dict()), observed)
        with self.assertRaises(FrozenInstanceError):
            observed.tasks = 99  # type: ignore[misc]

    def test_from_random_baseline_derives_the_rate_from_baseline_hits(self) -> None:
        observed = CohortObservations.from_random_baseline(
            tasks=8, exploration_target_hits=1, policy_disagreements=4
        )

        self.assertEqual(observed.exploration_target_rate, 0.125)
        self.assertEqual(observed.tasks, 8)
        self.assertEqual(observed.policy_disagreements, 4)

    def test_from_random_baseline_rejects_impossible_hit_counts(self) -> None:
        with self.assertRaises(ValueError):
            CohortObservations.from_random_baseline(
                tasks=4, exploration_target_hits=5, policy_disagreements=3
            )
        with self.assertRaises(ValueError):
            CohortObservations.from_random_baseline(
                tasks=0, exploration_target_hits=0, policy_disagreements=0
            )

    def test_disagreements_cannot_exceed_tasks(self) -> None:
        with self.assertRaises(ValueError):
            observations(policy_disagreements=9, tasks=8)

    def test_invalid_observation_values_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            observations(exploration_target_rate=1.4)
        with self.assertRaises(ValueError):
            observations(policy_disagreements=-1)
        with self.assertRaises(ValueError):
            observations(tasks=0)
        with self.assertRaises(TypeError):
            observations(tasks="8")  # type: ignore[arg-type]


class EvaluateAdmissionTests(unittest.TestCase):
    def test_informative_cohort_is_admitted_without_failures(self) -> None:
        result = evaluate_admission(
            observations(exploration_target_rate=0.1, policy_disagreements=4, tasks=8)
        )

        self.assertTrue(result.admitted)
        self.assertFalse(result.rejected)
        self.assertEqual(result.failures, ())
        self.assertEqual(result.decision, "admit")

    def test_thresholds_are_inclusive_at_the_boundary(self) -> None:
        result = evaluate_admission(
            observations(exploration_target_rate=0.2, policy_disagreements=3, tasks=5)
        )

        self.assertTrue(result.admitted)

    def test_saturated_exploration_alone_rejects_the_cohort(self) -> None:
        result = evaluate_admission(
            observations(exploration_target_rate=0.6, policy_disagreements=4, tasks=8)
        )

        self.assertFalse(result.admitted)
        self.assertEqual(
            result.failures, ("exploration_target_rate 0.60 exceeds maximum 0.20",)
        )

    def test_missing_policy_disagreements_alone_rejects_the_cohort(self) -> None:
        result = evaluate_admission(
            observations(exploration_target_rate=0.1, policy_disagreements=2, tasks=8)
        )

        self.assertFalse(result.admitted)
        self.assertEqual(
            result.failures, ("policy_disagreements 2 is below minimum 3",)
        )

    def test_undersized_cohort_alone_rejects_the_cohort(self) -> None:
        result = evaluate_admission(
            observations(exploration_target_rate=0.1, policy_disagreements=4, tasks=4)
        )

        self.assertFalse(result.admitted)
        self.assertEqual(result.failures, ("tasks 4 is below minimum 5",))

    def test_every_simultaneous_failure_is_reported(self) -> None:
        result = evaluate_admission(
            observations(exploration_target_rate=0.75, policy_disagreements=0, tasks=4)
        )

        self.assertFalse(result.admitted)
        self.assertEqual(
            result.failures,
            (
                "exploration_target_rate 0.75 exceeds maximum 0.20",
                "policy_disagreements 0 is below minimum 3",
                "policy_disagreement_rate 0.000 is below minimum 0.200",
                "tasks 4 is below minimum 5",
            ),
        )
        self.assertEqual(result.decision, "reject and redesign cohort")

    def test_custom_criteria_are_honoured_and_recorded(self) -> None:
        criteria = AdmissionCriteria(
            maximum_exploration_target_rate=0.5,
            minimum_tasks=5,
            minimum_policy_disagreements=1,
        )
        result = evaluate_admission(
            observations(exploration_target_rate=0.4, policy_disagreements=1, tasks=5),
            criteria,
        )

        self.assertTrue(result.admitted)
        self.assertEqual(result.criteria, criteria)

    def test_evaluate_admission_rejects_wrong_argument_types(self) -> None:
        with self.assertRaises(TypeError):
            evaluate_admission(observations().to_dict())  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            evaluate_admission(observations(), criteria={"minimum_tasks": 5})  # type: ignore[arg-type]


class AdmissionResultTests(unittest.TestCase):
    def test_result_is_frozen_and_round_trips(self) -> None:
        result = evaluate_admission(
            observations(exploration_target_rate=0.9, policy_disagreements=0, tasks=5)
        )

        self.assertEqual(AdmissionResult.from_dict(result.to_dict()), result)
        with self.assertRaises(FrozenInstanceError):
            result.admitted = True  # type: ignore[misc]

    def test_inconsistent_results_cannot_be_constructed(self) -> None:
        observed = observations()
        criteria = AdmissionCriteria()
        with self.assertRaises(ValueError):
            AdmissionResult(criteria, observed, True, ("some failure",))
        with self.assertRaises(ValueError):
            AdmissionResult(criteria, observed, False, ())
        with self.assertRaises(ValueError):
            AdmissionResult(criteria, observed, False, ("  ",))
        with self.assertRaises(TypeError):
            AdmissionResult(criteria, observed, "yes")  # type: ignore[arg-type]

    def test_from_dict_rejects_a_forged_decision(self) -> None:
        result = evaluate_admission(
            observations(exploration_target_rate=0.9, policy_disagreements=0, tasks=5)
        )
        payload = result.to_dict()
        payload["decision"] = "admit"

        with self.assertRaises(ValueError):
            AdmissionResult.from_dict(payload)

    def test_canonical_json_is_sorted_and_compact(self) -> None:
        result = evaluate_admission(observations())
        canonical = result.canonical_json()

        self.assertNotIn(", ", canonical)
        self.assertNotIn(": ", canonical)
        self.assertEqual(json.loads(canonical), result.to_dict())
        self.assertEqual(
            canonical, json.dumps(json.loads(canonical), sort_keys=True, separators=(",", ":"))
        )

    def test_digest_is_deterministic_and_sensitive_to_the_verdict(self) -> None:
        admitted = evaluate_admission(observations())
        repeated = evaluate_admission(observations())
        rejected = evaluate_admission(
            observations(exploration_target_rate=0.9, policy_disagreements=0, tasks=5)
        )

        self.assertEqual(admitted.digest(), repeated.digest())
        self.assertEqual(len(admitted.digest()), 64)
        self.assertNotEqual(admitted.digest(), rejected.digest())

    def test_digest_matches_the_repository_report_digest_recipe(self) -> None:

        result = evaluate_admission(observations())
        expected = hashlib.sha256(
            json.dumps(
                result.to_dict(), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()

        self.assertEqual(result.digest(), expected)
        self.assertEqual(result.to_report()["report_digest"], expected)

    def test_to_report_does_not_include_its_own_digest_in_the_digest(self) -> None:
        result = evaluate_admission(observations())
        report = result.to_report()
        report.pop("report_digest")

        self.assertEqual(report, result.to_dict())


class RequireAdmittedTests(unittest.TestCase):
    def test_require_admitted_returns_an_admitted_result(self) -> None:
        result = evaluate_admission(observations())

        self.assertIs(require_admitted(result), result)

    def test_require_admitted_raises_with_every_failure_named(self) -> None:
        result = evaluate_admission(
            observations(exploration_target_rate=0.9, policy_disagreements=0, tasks=4)
        )

        with self.assertRaises(BenchmarkNotAdmittedError) as caught:
            require_admitted(result)

        message = str(caught.exception)
        self.assertIn("exploration_target_rate 0.90 exceeds maximum 0.20", message)
        self.assertIn("policy_disagreements 0 is below minimum 3", message)
        self.assertIn("tasks 4 is below minimum 5", message)
        self.assertIs(caught.exception.result, result)
        self.assertEqual(caught.exception.to_dict()["admission"], result.to_report())

    def test_error_cannot_be_raised_for_an_admitted_result(self) -> None:
        with self.assertRaises(ValueError):
            BenchmarkNotAdmittedError(evaluate_admission(observations()))
        with self.assertRaises(TypeError):
            BenchmarkNotAdmittedError("not a result")  # type: ignore[arg-type]

    def test_admit_cohort_combines_evaluation_and_enforcement(self) -> None:
        admitted = admit_cohort(observations())
        self.assertTrue(admitted.admitted)

        with self.assertRaises(BenchmarkNotAdmittedError):
            admit_cohort(
                observations(exploration_target_rate=0.8, policy_disagreements=0, tasks=5)
            )


class E51RegressionTests(unittest.TestCase):
    """Pin the historical E51 finding: that cohort could not measure anything."""

    def e51_observations(self) -> CohortObservations:
        # E50-real-curved as audited by E51-benchmark-admission: random
        # exploration hit the target on 4 of 5 tasks and the shape router never
        # disagreed with the linear baseline.
        return CohortObservations.from_random_baseline(
            tasks=5, exploration_target_hits=4, policy_disagreements=0
        )

    def test_e51_cohort_numbers_reproduce(self) -> None:
        observed = self.e51_observations()

        self.assertEqual(observed.exploration_target_rate, 0.8)
        self.assertEqual(observed.policy_disagreements, 0)
        self.assertEqual(observed.tasks, 5)

    def test_e51_cohort_is_rejected_before_it_can_produce_evidence(self) -> None:
        result = evaluate_admission(self.e51_observations())

        self.assertFalse(result.admitted)
        self.assertEqual(result.decision, "reject and redesign cohort")
        self.assertEqual(
            result.failures,
            (
                "exploration_target_rate 0.80 exceeds maximum 0.20",
                "policy_disagreements 0 is below minimum 3",
                "policy_disagreement_rate 0.000 is below minimum 0.200",
            ),
        )
        with self.assertRaises(BenchmarkNotAdmittedError):
            require_admitted(result)

    def test_e51_cohort_passes_only_the_task_count_criterion(self) -> None:
        result = evaluate_admission(self.e51_observations())

        self.assertFalse(any("tasks 5" in failure for failure in result.failures))


class E59PlateauRegressionTests(unittest.TestCase):
    """The absolute count was vacuous at scale; the rate criterion fixes it.

    In E59 the ``plateau`` family was admitted with 8 disagreements over 120
    tasks -- clearing a minimum of 3 -- and then measured a paired regret delta
    of exactly 0.0 with a degenerate [0, 0] interval.  A count that is a real
    bar at 5 tasks is no bar at all at 120.
    """

    def plateau_observations(self) -> CohortObservations:
        return CohortObservations(
            exploration_target_rate=0.041666666666666664,
            policy_disagreements=8,
            tasks=120,
        )

    def test_plateau_rate_is_below_the_bar(self) -> None:
        observed = self.plateau_observations()

        self.assertAlmostEqual(observed.policy_disagreement_rate, 8 / 120)
        self.assertLess(observed.policy_disagreement_rate, 0.2)

    def test_plateau_was_admitted_under_the_count_only_criteria(self) -> None:
        """Reproduces the E59 defect: every count-based criterion passed."""
        observed = self.plateau_observations()

        self.assertGreaterEqual(observed.policy_disagreements, 3)
        self.assertGreaterEqual(observed.tasks, 5)
        self.assertLessEqual(observed.exploration_target_rate, 0.2)

    def test_plateau_is_now_rejected(self) -> None:
        result = evaluate_admission(self.plateau_observations())

        self.assertFalse(result.admitted)
        self.assertEqual(
            result.failures,
            ("policy_disagreement_rate 0.067 is below minimum 0.200",),
        )
        with self.assertRaises(BenchmarkNotAdmittedError):
            require_admitted(result)

    def test_the_rate_is_checked_conjunctively_with_the_count(self) -> None:
        """Clearing the rate must not excuse a cohort that fails the count."""
        result = evaluate_admission(
            CohortObservations(
                exploration_target_rate=0.0, policy_disagreements=2, tasks=4
            )
        )

        self.assertFalse(result.admitted)
        self.assertTrue(
            any("policy_disagreements 2" in failure for failure in result.failures)
        )

    def test_a_cohort_clearing_both_is_admitted(self) -> None:
        result = evaluate_admission(
            CohortObservations(
                exploration_target_rate=0.05, policy_disagreements=40, tasks=120
            )
        )

        self.assertTrue(result.admitted)
        self.assertEqual(result.failures, ())

    def test_rate_criterion_is_validated(self) -> None:
        with self.assertRaises(ValueError):
            AdmissionCriteria(minimum_policy_disagreement_rate=1.5)
        with self.assertRaises(ValueError):
            AdmissionCriteria(minimum_policy_disagreement_rate=-0.1)


if __name__ == "__main__":
    unittest.main()
