from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from recursive_lab.fixtures import FixtureMetaImprover, FixtureSealedUtility, baseline_strategy  # noqa: E402
from recursive_lab.meta_archive import ImproverArchive  # noqa: E402
from recursive_lab.metaproductivity import CostWeights, ExperimentBudget, run_tournament  # noqa: E402


class MetaArchiveTests(unittest.TestCase):
    def report(self):
        ancestor = FixtureMetaImprover("ancestor", ("Reproduce the reported failure before editing.",))
        descendant = FixtureMetaImprover("descendant", ("Reproduce the reported failure before editing.", "Run the public tests after each change.", "Inspect nearby code and call sites."))
        return descendant, run_tournament(
            ancestor=ancestor, descendant=descendant,
            seed_artifacts=[baseline_strategy(str(i)) for i in range(5)],
            trial_seeds=[10, 11, 12, 13, 14], evaluator=FixtureSealedUtility(),
            budget=ExperimentBudget(1, 2, 1, 32, 1),
            cost_weights=CostWeights(), effect_threshold=.1, bootstrap_samples=1000,
        )

    def test_fixture_requires_explicit_opt_in(self):
        descendant, report = self.report()
        archive = ImproverArchive()
        parent = archive.seed(FixtureMetaImprover("ancestor", ("Reproduce the reported failure before editing.",)))
        rejected = archive.consider(descendant, report, parent_digest=parent.digest)
        self.assertEqual(rejected.verdict, "rejected_fixture_evidence")
        promoted = archive.consider(descendant, report, parent_digest=parent.digest, allow_fixture=True)
        self.assertEqual(promoted.verdict, "promoted")
        self.assertEqual(promoted.generation, 1)


if __name__ == "__main__":
    unittest.main()
