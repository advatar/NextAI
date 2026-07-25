from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from recursive_lab.candidate_diversity import (  # noqa: E402
    DEFAULT_DIVERSITY_REQUIREMENT,
    RUN_STATUS_ADMISSIBLE,
    RUN_STATUS_VOID,
    DegenerateCandidateStreamError,
    DiversityReport,
    DiversityRequirement,
    assess_candidate_diversity,
    enforce_candidate_diversity,
    extract_candidate_digests,
    report_digest,
    require_diversity,
    void_run_payload,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
E58_REPORT_PATH = REPO_ROOT / "experiments" / "E58-gemma-governed-program.json"


def digest(label: str) -> str:
    return f"{label:0>64}".replace(" ", "0")


def receipt(label: str, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "candidate_digest": digest(label),
        "proposer": "fixture",
        "parse_ok": True,
    }
    payload.update(extra)
    return payload


class DiversityRequirementTests(unittest.TestCase):
    def test_defaults_are_the_weakest_bound_that_voids_a_collapsed_stream(self):
        requirement = DEFAULT_DIVERSITY_REQUIREMENT
        self.assertEqual(requirement.minimum_unique_candidates, 2)
        self.assertEqual(requirement.minimum_total_candidates, 2)
        self.assertEqual(requirement.minimum_unique_ratio, 0.5)
        self.assertEqual(requirement.maximum_repeat_ratio, 1.0)

    def test_requirement_round_trips_through_a_mapping(self):
        requirement = DiversityRequirement(
            minimum_unique_candidates=3,
            minimum_unique_ratio=0.75,
            minimum_total_candidates=4,
            maximum_repeat_ratio=0.5,
        )
        self.assertEqual(DiversityRequirement.from_dict(requirement.to_dict()), requirement)

    def test_requirement_rejects_non_integer_minimum_unique_candidates(self):
        with self.assertRaises(TypeError):
            DiversityRequirement(minimum_unique_candidates=2.0)
        with self.assertRaises(TypeError):
            DiversityRequirement(minimum_unique_candidates=True)

    def test_requirement_rejects_a_minimum_of_one_unique_candidate(self):
        # A minimum of one would accept the exact E58 collapse.
        with self.assertRaises(ValueError):
            DiversityRequirement(minimum_unique_candidates=0)

    def test_requirement_rejects_out_of_range_ratios(self):
        with self.assertRaises(ValueError):
            DiversityRequirement(minimum_unique_ratio=1.5)
        with self.assertRaises(ValueError):
            DiversityRequirement(minimum_unique_ratio=-0.1)
        with self.assertRaises(ValueError):
            DiversityRequirement(maximum_repeat_ratio=0.0)
        with self.assertRaises(TypeError):
            DiversityRequirement(minimum_unique_ratio="0.5")

    def test_requirement_rejects_non_finite_ratios(self):
        with self.assertRaises(ValueError):
            DiversityRequirement(minimum_unique_ratio=float("nan"))
        with self.assertRaises(ValueError):
            DiversityRequirement(minimum_unique_ratio=float("inf"))

    def test_requirement_rejects_incoherent_unique_and_total_minimums(self):
        with self.assertRaises(ValueError):
            DiversityRequirement(minimum_unique_candidates=5, minimum_total_candidates=3)

    def test_requirement_from_dict_rejects_unknown_or_missing_keys(self):
        payload = DEFAULT_DIVERSITY_REQUIREMENT.to_dict()
        payload["surprise"] = 1
        with self.assertRaises(ValueError):
            DiversityRequirement.from_dict(payload)
        with self.assertRaises(ValueError):
            DiversityRequirement.from_dict({"minimum_unique_ratio": 0.5})

    def test_requirement_is_frozen(self):
        with self.assertRaises(Exception):
            DEFAULT_DIVERSITY_REQUIREMENT.minimum_unique_candidates = 9


class InputShapeTests(unittest.TestCase):
    def test_bare_digests_and_receipt_mappings_produce_the_same_report(self):
        labels = ["a", "b", "c", "a"]
        from_digests = assess_candidate_diversity([digest(label) for label in labels])
        from_receipts = assess_candidate_diversity([receipt(label) for label in labels])
        self.assertEqual(from_digests, from_receipts)
        self.assertEqual(from_digests.total_candidates, 4)
        self.assertEqual(from_digests.unique_candidates, 3)

    def test_extract_handles_a_mixed_stream_and_strips_whitespace(self):
        digests = extract_candidate_digests([digest("a"), receipt("b"), f"  {digest('c')} "])
        self.assertEqual(digests, (digest("a"), digest("b"), digest("c")))

    def test_alternate_digest_key_is_supported(self):
        stream = [{"program_digest": digest("a")}, {"program_digest": digest("b")}]
        report = assess_candidate_diversity(stream, digest_key="program_digest")
        self.assertEqual(report.unique_candidates, 2)
        self.assertTrue(report.satisfied)

    def test_mapping_without_the_digest_key_fails_closed(self):
        with self.assertRaises(ValueError):
            assess_candidate_diversity([{"response_digest": digest("a")}])

    def test_null_digest_fails_closed_rather_than_counting_as_unique(self):
        stream = [receipt("a"), {"candidate_digest": None, "parse_ok": False}]
        with self.assertRaises(ValueError):
            assess_candidate_diversity(stream)

    def test_empty_and_non_string_digests_fail_closed(self):
        with self.assertRaises(ValueError):
            assess_candidate_diversity([digest("a"), "   "])
        with self.assertRaises(TypeError):
            assess_candidate_diversity([digest("a"), 17])

    def test_a_bare_string_or_mapping_is_not_a_candidate_stream(self):
        with self.assertRaises(TypeError):
            extract_candidate_digests(digest("a"))
        with self.assertRaises(TypeError):
            extract_candidate_digests(receipt("a"))

    def test_generators_are_accepted(self):
        report = assess_candidate_diversity(digest(label) for label in "abcd")
        self.assertEqual(report.total_candidates, 4)
        self.assertTrue(report.satisfied)


class DiversityAssessmentTests(unittest.TestCase):
    def test_healthy_diverse_stream_is_admissible(self):
        report = assess_candidate_diversity([digest(label) for label in "abcdef"])
        self.assertTrue(report.satisfied)
        self.assertTrue(report.admissible)
        self.assertFalse(report.void)
        self.assertFalse(report.collapsed)
        self.assertEqual(report.run_status, RUN_STATUS_ADMISSIBLE)
        self.assertEqual(report.failures, ())
        self.assertEqual(report.unique_candidates, 6)
        self.assertEqual(report.unique_ratio, 1.0)
        self.assertEqual(report.most_repeated_count, 1)

    def test_fully_collapsed_stream_is_void(self):
        report = assess_candidate_diversity([digest("a")] * 6)
        self.assertFalse(report.satisfied)
        self.assertTrue(report.void)
        self.assertTrue(report.collapsed)
        self.assertEqual(report.run_status, RUN_STATUS_VOID)
        self.assertEqual(report.total_candidates, 6)
        self.assertEqual(report.unique_candidates, 1)
        self.assertAlmostEqual(report.unique_ratio, 1 / 6)
        self.assertEqual(report.most_repeated_digest, digest("a"))
        self.assertEqual(report.most_repeated_count, 6)
        self.assertEqual(report.repeat_ratio, 1.0)
        self.assertTrue(any("unique candidate" in reason for reason in report.failures))

    def test_partially_collapsed_stream_below_the_ratio_is_void(self):
        # 5 identical + 1 distinct: two unique candidates clears the count bound
        # but the ratio bound still voids the run.
        stream = [digest("a")] * 5 + [digest("b")]
        report = assess_candidate_diversity(stream)
        self.assertFalse(report.satisfied)
        self.assertTrue(report.void)
        self.assertFalse(report.collapsed)
        self.assertEqual(report.unique_candidates, 2)
        self.assertAlmostEqual(report.unique_ratio, 2 / 6)
        self.assertEqual(report.most_repeated_digest, digest("a"))
        self.assertEqual(report.most_repeated_count, 5)
        self.assertEqual(len(report.failures), 1)
        self.assertIn("unique ratio", report.failures[0])

    def test_repeat_ratio_bound_catches_a_stuck_proposer_with_stray_variants(self):
        requirement = DiversityRequirement(
            minimum_unique_candidates=2,
            minimum_unique_ratio=0.2,
            minimum_total_candidates=2,
            maximum_repeat_ratio=0.5,
        )
        stream = [digest("a")] * 7 + [digest("b"), digest("c")]
        report = assess_candidate_diversity(stream, requirement)
        self.assertTrue(report.void)
        self.assertEqual(report.most_repeated_count, 7)
        self.assertTrue(any("repeat ratio" in reason for reason in report.failures))

    def test_empty_stream_fails_closed(self):
        report = assess_candidate_diversity([])
        self.assertFalse(report.satisfied)
        self.assertTrue(report.void)
        self.assertFalse(report.collapsed)
        self.assertEqual(report.total_candidates, 0)
        self.assertEqual(report.unique_candidates, 0)
        self.assertEqual(report.unique_ratio, 0.0)
        self.assertEqual(report.repeat_ratio, 0.0)
        self.assertIsNone(report.most_repeated_digest)
        self.assertTrue(report.failures)

    def test_single_candidate_stream_is_void(self):
        report = assess_candidate_diversity([digest("a")])
        self.assertTrue(report.void)
        self.assertEqual(report.total_candidates, 1)
        self.assertEqual(report.unique_candidates, 1)

    def test_most_repeated_digest_ties_resolve_deterministically(self):
        stream = [digest("b"), digest("a"), digest("b"), digest("a")]
        report = assess_candidate_diversity(stream)
        self.assertEqual(report.most_repeated_digest, digest("a"))
        self.assertEqual(report.most_repeated_count, 2)

    def test_assessment_rejects_a_non_requirement(self):
        with self.assertRaises(TypeError):
            assess_candidate_diversity([digest("a")], {"minimum_unique_candidates": 2})

    def test_requirement_assess_helper_matches_the_function(self):
        requirement = DiversityRequirement(minimum_unique_ratio=0.9)
        stream = [receipt(label) for label in "abc"]
        self.assertEqual(
            requirement.assess(stream),
            assess_candidate_diversity(stream, requirement),
        )


class EnforcementTests(unittest.TestCase):
    def test_require_diversity_returns_an_admissible_report_unchanged(self):
        report = assess_candidate_diversity([digest(label) for label in "abc"])
        self.assertIs(require_diversity(report), report)
        self.assertIs(report.require(), report)

    def test_require_diversity_raises_and_carries_the_report(self):
        report = assess_candidate_diversity([digest("a")] * 6)
        with self.assertRaises(DegenerateCandidateStreamError) as caught:
            require_diversity(report)
        self.assertIs(caught.exception.report, report)
        self.assertIn(RUN_STATUS_VOID, str(caught.exception))
        self.assertIn("1/6 unique", str(caught.exception))

    def test_degenerate_error_serializes_the_void_verdict(self):
        report = assess_candidate_diversity([digest("a")] * 3)
        payload = DegenerateCandidateStreamError(report).to_dict()
        self.assertEqual(payload["error"], "DegenerateCandidateStreamError")
        self.assertEqual(payload["run_status"], RUN_STATUS_VOID)
        self.assertEqual(payload["diversity"]["unique_candidates"], 1)

    def test_enforce_candidate_diversity_is_assess_plus_require(self):
        stream = [receipt(label) for label in "abcd"]
        self.assertEqual(
            enforce_candidate_diversity(stream), assess_candidate_diversity(stream)
        )
        with self.assertRaises(DegenerateCandidateStreamError):
            enforce_candidate_diversity([receipt("a") for _ in range(4)])

    def test_require_diversity_rejects_a_non_report(self):
        with self.assertRaises(TypeError):
            require_diversity({"satisfied": True})

    def test_void_run_payload_carries_no_scores(self):
        report = assess_candidate_diversity([digest("a")] * 6)
        payload = void_run_payload(report, experiment_id="E58-gemma-governed-program")
        self.assertEqual(payload["run_status"], RUN_STATUS_VOID)
        self.assertEqual(payload["experiment_id"], "E58-gemma-governed-program")
        self.assertIn("void", payload["claim_boundary"])
        self.assertEqual(payload["diversity"]["total_candidates"], 6)
        self.assertNotIn("promotion_parity", payload)
        self.assertNotIn("adoption_gate", payload)
        self.assertEqual(len(payload["report_digest"]), 64)

    def test_void_run_payload_requires_an_experiment_id(self):
        report = assess_candidate_diversity([digest("a")] * 6)
        with self.assertRaises(ValueError):
            void_run_payload(report, experiment_id="  ")


class ReportConstructionTests(unittest.TestCase):
    def test_report_rejects_inconsistent_counts(self):
        with self.assertRaises(ValueError):
            DiversityReport(
                requirement=DEFAULT_DIVERSITY_REQUIREMENT,
                total_candidates=2,
                unique_candidates=3,
                unique_ratio=1.0,
                satisfied=True,
            )

    def test_report_rejects_a_satisfied_verdict_carrying_failures(self):
        with self.assertRaises(ValueError):
            DiversityReport(
                requirement=DEFAULT_DIVERSITY_REQUIREMENT,
                total_candidates=2,
                unique_candidates=2,
                unique_ratio=1.0,
                satisfied=True,
                failures=("nope",),
            )

    def test_report_rejects_an_unsatisfied_verdict_without_a_reason(self):
        with self.assertRaises(ValueError):
            DiversityReport(
                requirement=DEFAULT_DIVERSITY_REQUIREMENT,
                total_candidates=2,
                unique_candidates=1,
                unique_ratio=0.5,
                satisfied=False,
            )

    def test_report_rejects_a_non_requirement_and_non_bool_verdict(self):
        with self.assertRaises(TypeError):
            DiversityReport(
                requirement={"minimum_unique_candidates": 2},
                total_candidates=2,
                unique_candidates=2,
                unique_ratio=1.0,
                satisfied=True,
            )
        with self.assertRaises(TypeError):
            DiversityReport(
                requirement=DEFAULT_DIVERSITY_REQUIREMENT,
                total_candidates=2,
                unique_candidates=2,
                unique_ratio=1.0,
                satisfied=1,
            )


class DigestTests(unittest.TestCase):
    def test_report_digest_is_deterministic_across_equivalent_streams(self):
        first = assess_candidate_diversity([digest(label) for label in "aabc"])
        second = assess_candidate_diversity([receipt(label) for label in "acab"])
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(len(first.digest), 64)

    def test_report_digest_field_matches_the_digest_property(self):
        report = assess_candidate_diversity([digest(label) for label in "abc"])
        self.assertEqual(report.to_dict()["report_digest"], report.digest)

    def test_report_digest_changes_when_the_verdict_changes(self):
        admissible = assess_candidate_diversity([digest(label) for label in "abc"])
        void = assess_candidate_diversity([digest("a")] * 3)
        self.assertNotEqual(admissible.digest, void.digest)

    def test_report_digest_changes_when_the_requirement_changes(self):
        stream = [digest(label) for label in "abcd"]
        strict = DiversityRequirement(minimum_unique_ratio=0.9)
        self.assertNotEqual(
            assess_candidate_diversity(stream).digest,
            assess_candidate_diversity(stream, strict).digest,
        )

    def test_report_digest_matches_the_repo_canonical_json_convention(self):
        report = assess_candidate_diversity([digest(label) for label in "abc"])
        payload = report.to_dict()
        payload.pop("report_digest")

        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        self.assertEqual(
            hashlib.sha256(canonical.encode("utf-8")).hexdigest(), report.digest
        )

    def test_report_digest_rejects_a_non_mapping_payload(self):
        with self.assertRaises(TypeError):
            report_digest(["not", "a", "mapping"])


class E58RegressionTests(unittest.TestCase):
    """Pin the historical defect this module exists to prevent.

    E58 spent six live Gemma calls and received the same program every time,
    yet reported valid_candidates: 6, promotion_parity: true and a passing
    adoption gate.  Under any reasonable diversity requirement that run is
    void, not passed.
    """

    def setUp(self):
        self.assertTrue(E58_REPORT_PATH.is_file(), f"missing evidence: {E58_REPORT_PATH}")
        self.experiment = json.loads(E58_REPORT_PATH.read_text(encoding="utf-8"))
        self.receipts = self.experiment["model_receipts"]

    def test_the_historical_report_still_advertises_the_misleading_pass(self):
        self.assertEqual(len(self.receipts), 6)
        self.assertEqual(self.experiment["valid_candidates"], 6)
        self.assertIs(self.experiment["promotion_parity"], True)
        self.assertIs(self.experiment["adoption_gate"]["passed"], True)

    def test_e58_receipts_are_six_calls_carrying_one_candidate(self):
        report = assess_candidate_diversity(self.receipts)
        self.assertEqual(report.total_candidates, 6)
        self.assertEqual(report.unique_candidates, 1)
        self.assertAlmostEqual(report.unique_ratio, 1 / 6)
        self.assertEqual(report.most_repeated_count, 6)
        self.assertEqual(report.repeat_ratio, 1.0)
        self.assertEqual(
            report.most_repeated_digest,
            "2f5a0b295354a47f27a3b102807010dc5d52168820489e379613130ea46ad8db",
        )

    def test_e58_is_void_under_the_default_requirement(self):
        report = assess_candidate_diversity(self.receipts)
        self.assertFalse(report.satisfied)
        self.assertTrue(report.void)
        self.assertTrue(report.collapsed)
        self.assertEqual(report.run_status, RUN_STATUS_VOID)
        self.assertEqual(len(report.failures), 2)

    def test_e58_would_have_raised_before_a_passing_report_was_written(self):
        with self.assertRaises(DegenerateCandidateStreamError) as caught:
            enforce_candidate_diversity(self.receipts)
        self.assertIs(caught.exception.report.total_candidates, 6)
        self.assertEqual(caught.exception.report.unique_candidates, 1)

    def test_e58_is_void_under_every_constructible_requirement(self):
        # One unique candidate cannot clear a minimum of two, and the minimum
        # is validated to be at least two, so no requirement admits E58.
        for minimum in (2, 3, 6):
            with self.subTest(minimum_unique_candidates=minimum):
                requirement = DiversityRequirement(
                    minimum_unique_candidates=minimum,
                    minimum_unique_ratio=0.0,
                    minimum_total_candidates=minimum,
                    maximum_repeat_ratio=1.0,
                )
                self.assertTrue(requirement.assess(self.receipts).void)

    def test_e58_response_digests_are_also_collapsed(self):
        report = assess_candidate_diversity(self.receipts, digest_key="response_digest")
        self.assertEqual(report.total_candidates, 6)
        self.assertEqual(report.unique_candidates, 1)
        self.assertTrue(report.void)

    def test_e58_evidence_file_is_not_mutated_by_assessment(self):
        before = E58_REPORT_PATH.read_bytes()
        assess_candidate_diversity(self.receipts)
        self.assertEqual(E58_REPORT_PATH.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
