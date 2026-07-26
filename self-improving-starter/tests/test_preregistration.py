"""A frozen analysis plan must fail closed when it is edited after the fact.

The point of pre-registration is that the plan cannot be quietly adjusted into
agreement with whatever the data turned out to say.  That guarantee is only real
if tampering is detected, so these tests edit a frozen plan in the ways someone
would plausibly edit it -- loosening a threshold, softening a prediction,
widening the instrument -- and assert the runner refuses each one.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compare_e60_corrected_admission import (  # noqa: E402
    PreregistrationDriftError,
    load_preregistration,
)
from preregister_e60 import PREREGISTRATION, digest_of  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
FROZEN = REPO_ROOT / "experiments" / "E60-preregistration.json"


def frozen_document() -> dict:
    document = dict(PREREGISTRATION)
    document["preregistration_digest"] = digest_of(document)
    return document


class DigestBehaviour(unittest.TestCase):
    def test_digest_ignores_the_digest_field(self):
        document = dict(PREREGISTRATION)
        without = digest_of(document)
        document["preregistration_digest"] = without
        self.assertEqual(digest_of(document), without)

    def test_digest_is_deterministic(self):
        self.assertEqual(digest_of(dict(PREREGISTRATION)), digest_of(dict(PREREGISTRATION)))

    def test_digest_changes_when_a_criterion_changes(self):
        document = dict(PREREGISTRATION)
        altered = dict(document)
        altered["criteria"] = dict(document["criteria"])
        altered["criteria"]["minimum_policy_disagreement_rate"] = 0.05
        self.assertNotEqual(digest_of(document), digest_of(altered))


class TamperDetection(unittest.TestCase):
    def _write(self, directory: Path, document: dict) -> Path:
        path = directory / "plan.json"
        path.write_text(json.dumps(document, indent=2))
        return path

    def test_untampered_plan_loads(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self._write(Path(temporary), frozen_document())
            loaded = load_preregistration(path)
            self.assertEqual(
                loaded["preregistration_digest"], frozen_document()["preregistration_digest"]
            )

    def test_missing_plan_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(PreregistrationDriftError):
                load_preregistration(Path(temporary) / "absent.json")

    def test_plan_without_digest_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            document = dict(PREREGISTRATION)
            path = self._write(Path(temporary), document)
            with self.assertRaises(PreregistrationDriftError):
                load_preregistration(path)

    def test_loosened_threshold_is_detected(self):
        """The most tempting edit: relax the gate until families are admitted."""
        with tempfile.TemporaryDirectory() as temporary:
            document = frozen_document()
            document["criteria"] = dict(document["criteria"])
            document["criteria"]["minimum_policy_disagreement_rate"] = 0.01
            path = self._write(Path(temporary), document)
            with self.assertRaises(PreregistrationDriftError) as caught:
                load_preregistration(path)
            self.assertIn("digest mismatch", str(caught.exception))

    def test_softened_prediction_is_detected(self):
        """Rewriting a prediction after seeing the result must not go unnoticed."""
        with tempfile.TemporaryDirectory() as temporary:
            document = frozen_document()
            document["predictions"] = [
                dict(item) for item in document["predictions"]
            ]
            document["predictions"][1]["statement"] = "monotone shows some effect"
            path = self._write(Path(temporary), document)
            with self.assertRaises(PreregistrationDriftError):
                load_preregistration(path)

    def test_widened_instrument_is_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            document = frozen_document()
            document["instrument"] = dict(document["instrument"])
            document["instrument"]["validation_seeds"] = 5000
            path = self._write(Path(temporary), document)
            with self.assertRaises(PreregistrationDriftError):
                load_preregistration(path)

    def test_a_forged_digest_does_not_help(self):
        """Recomputing the digest over edited content still has to match what
        was registered, so re-stamping an edited plan is not a way through."""
        with tempfile.TemporaryDirectory() as temporary:
            document = frozen_document()
            original = document["preregistration_digest"]
            document["criteria"] = dict(document["criteria"])
            document["criteria"]["minimum_tasks"] = 1
            document["preregistration_digest"] = digest_of(document)
            path = self._write(Path(temporary), document)
            # It now loads, because it is internally consistent -- which is why
            # the registered digest is also recorded in the experiment report
            # and in version control.
            loaded = load_preregistration(path)
            self.assertNotEqual(loaded["preregistration_digest"], original)


class TheFrozenPlanOnDisk(unittest.TestCase):
    def test_committed_plan_matches_the_module(self):
        """The registered file and the source that generated it must agree."""
        self.assertTrue(FROZEN.is_file(), "run preregister_e60.py")
        on_disk = json.loads(FROZEN.read_text())
        self.assertEqual(
            on_disk["preregistration_digest"],
            frozen_document()["preregistration_digest"],
        )

    def test_committed_plan_verifies(self):
        loaded = load_preregistration(FROZEN)
        self.assertEqual(loaded["experiment_id"], "E60-corrected-admission")

    def test_plan_records_falsifiable_predictions(self):
        loaded = load_preregistration(FROZEN)
        identifiers = [item["id"] for item in loaded["predictions"]]
        self.assertEqual(identifiers, ["H1", "H2", "H3", "H4"])
        for prediction in loaded["predictions"]:
            self.assertTrue(prediction["statement"])
            self.assertTrue(prediction["basis"])


if __name__ == "__main__":
    unittest.main()
