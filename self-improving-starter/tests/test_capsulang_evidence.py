"""Governance scenarios must agree with the evidence chain they cite.

The defect these tests pin: ``capsulang/e53_recursive_governor.caps`` declares
``(constraint benchmark_admitted == 1)`` and the showcase scenario
``e45_promote.json`` fed the machine ``benchmark_admitted: true``, while
``experiments/E51-benchmark-admission.json`` records ``admitted: false`` with
``"reject and redesign cohort"``.  The governor's demonstration path asserted a
fact the project's own audit refuted.

The contradiction is documented here as a test rather than quietly edited away,
so that if anyone later changes the scenario, the experiment, or the checker,
the disagreement has to be confronted explicitly.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from verify_capsulang_evidence import (  # noqa: E402
    ASSUMPTION,
    CONTRADICTION,
    EvidenceConsistencyError,
    Finding,
    VerificationReport,
    main,
    verify,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = REPO_ROOT / "capsulang" / "scenarios"
EXPERIMENTS = REPO_ROOT / "experiments"


class RealRepositoryState(unittest.TestCase):
    """What the checker reports about the repository as it actually stands."""

    @classmethod
    def setUpClass(cls):
        cls.report = verify()

    def test_no_contradictions_remain(self):
        self.assertEqual(
            [item.describe() for item in self.report.contradictions], []
        )

    def test_every_scenario_on_disk_is_checked(self):
        on_disk = sorted(path.name for path in SCENARIOS.glob("*.json"))
        self.assertEqual(sorted(self.report.scenarios_checked), on_disk)

    def test_the_e51_disagreement_is_reported_as_an_assumption(self):
        """The known defect, pinned.  e45_promote asserts an admitted benchmark
        that E51 refutes; it must surface on every run, not sit silent."""
        assumptions = [
            item
            for item in self.report.assumptions
            if item.scenario == "e45_promote.json"
            and item.field_name == "benchmark_admitted"
        ]
        self.assertEqual(len(assumptions), 1)
        finding = assumptions[0]
        self.assertIs(finding.scenario_value, True)
        self.assertIs(finding.evidence_value, False)
        self.assertIn("E51-benchmark-admission.json", finding.source)

    def test_e51_evidence_really_does_say_not_admitted(self):
        """Guards the premise of the test above against a silent edit."""
        payload = json.loads(
            (EXPERIMENTS / "E51-benchmark-admission.json").read_text()
        )
        self.assertIs(payload["admitted"], False)
        self.assertEqual(payload["decision"], "reject and redesign cohort")

    def test_a_scenario_refuses_promotion_on_measured_evidence(self):
        """A governor that only ever promotes demonstrates nothing.  At least
        one scenario must reach a non-promoted state from real evidence."""
        self.assertTrue(self.report.measured_refusals)

    def test_report_is_ok_but_not_under_strict(self):
        self.assertTrue(self.report.ok())
        self.assertFalse(self.report.ok(strict=True))

    def test_report_serializes(self):
        payload = self.report.to_dict()
        self.assertIn("findings", payload)
        self.assertIn("scenarios_checked", payload)
        self.assertIs(payload["ok"], True)

    def test_cli_exits_zero_by_default(self):
        self.assertEqual(main([]), 0)

    def test_cli_exits_nonzero_under_strict(self):
        """Strict mode treats an unproven assumption as a failure, which is what
        a release gate should do."""
        self.assertNotEqual(main(["--strict"]), 0)


class SyntheticFixtures(unittest.TestCase):
    """Behaviour on controlled inputs, independent of repository state."""

    def _write(self, directory: Path, name: str, payload: dict) -> None:
        (directory / name).write_text(json.dumps(payload, indent=2))

    def test_missing_scenario_directory_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "absent"
            with self.assertRaises(EvidenceConsistencyError):
                verify(scenario_directory=missing, experiment_directory=missing)

    def test_unregistered_scenario_is_a_contradiction(self):
        """A new scenario must declare which experiments justify it, otherwise
        governance fixtures can be added with no evidence at all."""
        with tempfile.TemporaryDirectory() as temporary:
            scenarios = Path(temporary) / "scenarios"
            experiments = Path(temporary) / "experiments"
            scenarios.mkdir()
            experiments.mkdir()
            self._write(scenarios, "unregistered.json", {"machine": "X"})
            report = verify(
                scenario_directory=scenarios,
                experiment_directory=experiments,
                bindings={},
            )
            unbound = [
                item
                for item in report.contradictions
                if item.scenario == "unregistered.json"
            ]
            self.assertEqual(len(unbound), 1)
            self.assertIn("no registered evidence binding", unbound[0].message)
            self.assertFalse(report.ok())

    def test_a_suite_that_only_promotes_is_a_contradiction(self):
        """A governor suite with no refusal path proves nothing about refusal.
        The synthetic directory above has no measured-evidence quarantine, and
        the checker must say so rather than pass quietly."""
        with tempfile.TemporaryDirectory() as temporary:
            scenarios = Path(temporary) / "scenarios"
            experiments = Path(temporary) / "experiments"
            scenarios.mkdir()
            experiments.mkdir()
            report = verify(
                scenario_directory=scenarios,
                experiment_directory=experiments,
                bindings={},
            )
            self.assertTrue(
                any(
                    "refuses promotion" in item.message
                    for item in report.contradictions
                )
            )

    def test_registered_scenario_missing_from_disk_is_a_contradiction(self):
        real = verify()
        binding = next(iter(_bindings().items()))
        with tempfile.TemporaryDirectory() as temporary:
            scenarios = Path(temporary) / "scenarios"
            scenarios.mkdir()
            report = verify(
                scenario_directory=scenarios,
                experiment_directory=EXPERIMENTS,
                bindings={binding[0]: binding[1]},
            )
            self.assertTrue(report.contradictions)
            self.assertFalse(report.ok())
        # The real repository is unaffected by the temporary run.
        self.assertEqual(real.contradictions, verify().contradictions)


class FindingAndReportTypes(unittest.TestCase):
    def test_describe_includes_scenario_and_field(self):
        finding = Finding(
            ASSUMPTION, "s.json", "message text", field_name="flag"
        )
        self.assertEqual(finding.describe(), "[assumption] s.json::flag: message text")

    def test_describe_without_field(self):
        finding = Finding(CONTRADICTION, "s.json", "message text")
        self.assertEqual(finding.describe(), "[contradiction] s.json: message text")

    def test_empty_report_is_ok_in_both_modes(self):
        report = VerificationReport()
        self.assertTrue(report.ok())
        self.assertTrue(report.ok(strict=True))

    def test_contradiction_beats_strictness(self):
        report = VerificationReport(
            findings=(Finding(CONTRADICTION, "s.json", "bad"),)
        )
        self.assertFalse(report.ok())
        self.assertFalse(report.ok(strict=True))

    def test_assumption_only_fails_under_strict(self):
        report = VerificationReport(
            findings=(Finding(ASSUMPTION, "s.json", "assumed"),)
        )
        self.assertTrue(report.ok())
        self.assertFalse(report.ok(strict=True))


def _bindings():
    from verify_capsulang_evidence import SCENARIO_BINDINGS

    return SCENARIO_BINDINGS


if __name__ == "__main__":
    unittest.main()
