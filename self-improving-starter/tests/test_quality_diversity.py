import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recursive_lab.quality_diversity import CandidateEvaluation, QualityDiversityArchive, strategy_features

class QualityDiversityTests(unittest.TestCase):
    def test_keeps_best_candidate_per_behavior_cell(self):
        archive = QualityDiversityArchive(bins=(2, 2))
        self.assertTrue(archive.add("a", CandidateEvaluation(1.0, (0.1, 0.1), {}), 0))
        self.assertFalse(archive.add("worse", CandidateEvaluation(.5, (.1, .1), {}), 1))
        self.assertTrue(archive.add("b", CandidateEvaluation(.8, (.8, .8), {}), 1))
        self.assertEqual(len(archive.entries), 2)
        self.assertEqual(archive.best.candidate, "a")

    def test_parent_selection_is_seeded(self):
        import random
        archive = QualityDiversityArchive(bins=(2,))
        archive.add("a", CandidateEvaluation(1, (0.1,), {}), 0)
        archive.add("b", CandidateEvaluation(2, (0.9,), {}), 0)
        self.assertEqual(archive.select_parent(random.Random(5)), archive.select_parent(random.Random(5)))

    def test_strategy_features_reward_transfer_and_cost(self):
        features = strategy_features(task_utilities=(1.0, .8), correct=True, tokens=400)
        self.assertEqual(features, (.9, .8, 1.0, .9))

if __name__ == "__main__": unittest.main()
