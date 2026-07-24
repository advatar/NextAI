import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recursive_lab.alphaevolve import EvolutionBudget, evolve_programs, text_fingerprint
from recursive_lab.quality_diversity import CandidateEvaluation


class Incrementer:
    name = "incrementer"

    def propose(self, sample, rng):
        return min(10, sample.parent.candidate + 1)


def evaluate(x):
    return CandidateEvaluation(x / 10, (x / 10,), {"score": x / 10})


class AlphaEvolveTests(unittest.TestCase):
    def test_full_loop_is_seeded_and_budgeted(self):
        kwargs = dict(
            initial=0,
            proposers=(Incrementer(),),
            evaluate=evaluate,
            fingerprint=text_fingerprint,
            budget=EvolutionBudget(5, 3),
            seed=4,
            bins=(5,),
        )
        first = evolve_programs(**kwargs)
        second = evolve_programs(**kwargs)
        self.assertEqual(first, second)
        self.assertEqual(first.model_calls, 5)
        self.assertEqual(first.task_evaluations, 15)
        self.assertGreater(first.best.evaluation.objective, 0)

    def test_requires_proposer(self):
        with self.assertRaises(ValueError):
            evolve_programs(
                initial=0,
                proposers=(),
                evaluate=evaluate,
                fingerprint=text_fingerprint,
                budget=EvolutionBudget(1, 1),
                seed=0,
                bins=(2,),
            )


if __name__ == "__main__":
    unittest.main()
