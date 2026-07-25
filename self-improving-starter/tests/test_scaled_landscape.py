"""The scaled instrument must be a strict widening of the historical 5x5 one."""

from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compare_e37_surrogate_generalization import score as e37_score  # noqa: E402
from compare_e38_adaptive_emitter import fit_linear as e38_fit_linear  # noqa: E402
from compare_e40_unseen_families import score as e40_score  # noqa: E402
from compare_e42_second_audit import score as e42_score  # noqa: E402
from recursive_lab.scaled_landscape import (  # noqa: E402
    ALWAYS_SURROGATE_POLICY,
    E41_GATE_POLICY,
    FAMILIES,
    LEGACY_GRID_SIZE,
    LandscapeError,
    LandscapeSpec,
    RANDOM_POLICY,
    RouterPolicy,
    SearchBudget,
    fit_linear,
    make_spec,
    optimum,
    run_policy,
    score,
    surrogate_choice,
)

E37_FAMILIES = ("monotone", "curved", "spike")
E40_FAMILIES = ("plateau", "checkerboard", "rugged")
E42_FAMILIES = ("ridge", "sinusoidal", "decoy")


class ReductionToLegacyGrid(unittest.TestCase):
    """At grid size 5 every family must equal its original definition."""

    def _targets(self, family):
        extent = LEGACY_GRID_SIZE - 1
        if family == "monotone":
            return [(x, y) for x in (0, extent) for y in (0, extent)]
        return [
            (x, y)
            for x in range(LEGACY_GRID_SIZE)
            for y in range(LEGACY_GRID_SIZE)
        ]

    def test_e37_families_match_cell_for_cell(self):
        for family in E37_FAMILIES:
            for target in self._targets(family):
                spec = LandscapeSpec(family, LEGACY_GRID_SIZE, target)
                for x in range(LEGACY_GRID_SIZE):
                    for y in range(LEGACY_GRID_SIZE):
                        self.assertAlmostEqual(
                            score(spec, (x, y)),
                            e37_score(family, (x, y), target),
                            places=12,
                            msg=f"{family} target={target} point={(x, y)}",
                        )

    def test_e40_families_match_cell_for_cell(self):
        for family in E40_FAMILIES:
            for target in self._targets(family):
                for landscape_seed in (0, 17, 53000):
                    spec = LandscapeSpec(
                        family, LEGACY_GRID_SIZE, target, landscape_seed
                    )
                    for x in range(LEGACY_GRID_SIZE):
                        for y in range(LEGACY_GRID_SIZE):
                            self.assertAlmostEqual(
                                score(spec, (x, y)),
                                e40_score(
                                    family, (x, y), target, landscape_seed
                                ),
                                places=12,
                                msg=f"{family} target={target} point={(x, y)}",
                            )

    def test_e42_families_match_cell_for_cell(self):
        for family in E42_FAMILIES:
            for target in self._targets(family):
                spec = LandscapeSpec(family, LEGACY_GRID_SIZE, target)
                for x in range(LEGACY_GRID_SIZE):
                    for y in range(LEGACY_GRID_SIZE):
                        self.assertAlmostEqual(
                            score(spec, (x, y)),
                            e42_score(family, (x, y), target),
                            places=12,
                            msg=f"{family} target={target} point={(x, y)}",
                        )

    def test_legacy_coverage_reproduces_the_e51_saturation(self):
        """The historical budget really did evaluate 80% of the space."""
        budget = SearchBudget(LEGACY_GRID_SIZE, 3)
        self.assertEqual(budget.evaluations, 20)
        self.assertEqual(budget.search_space, 25)
        self.assertAlmostEqual(budget.coverage, 0.8)


class ScaleInvariants(unittest.TestCase):
    def test_target_is_the_unique_optimum_at_every_scale(self):
        """``regret`` is only meaningful if the target really is the maximum."""
        for grid_size in (5, 16, 64):
            for family in FAMILIES:
                spec = make_spec(family, grid_size, seed=7)
                best_elsewhere = max(
                    score(spec, (x, y))
                    for x in range(grid_size)
                    for y in range(grid_size)
                    if (x, y) != spec.target
                )
                self.assertAlmostEqual(
                    score(spec, spec.target), optimum(spec), places=12
                )
                self.assertLess(
                    best_elsewhere,
                    optimum(spec),
                    msg=f"{family} at grid {grid_size} has a non-unique optimum",
                )

    def test_scores_stay_bounded_on_a_wide_grid(self):
        """Pins the spike/decoy scaling bug: an unnormalised noise floor
        would climb past 1.0 once the modulus grew with the grid."""
        for family in FAMILIES:
            spec = make_spec(family, 128, seed=3)
            for _ in range(400):
                point = (random.randrange(128), random.randrange(128))
                value = score(spec, point)
                self.assertGreaterEqual(value, -1.0)
                self.assertLessEqual(value, 1.0)

    def test_coverage_shrinks_as_the_grid_widens(self):
        self.assertAlmostEqual(SearchBudget(5, 3).coverage, 0.8)
        self.assertAlmostEqual(SearchBudget(64, 3).coverage, 0.0625)
        self.assertAlmostEqual(SearchBudget(256, 3).coverage, 0.015625)

    def test_more_exploration_does_not_buy_coverage(self):
        """Only a wider grid creates headroom; sampling more per column hurts."""
        self.assertGreater(
            SearchBudget(64, 7).coverage, SearchBudget(64, 3).coverage
        )


class Validation(unittest.TestCase):
    def test_rejects_unknown_family(self):
        with self.assertRaises(LandscapeError):
            LandscapeSpec("nonexistent", 8, (0, 0))

    def test_rejects_degenerate_grid(self):
        with self.assertRaises(LandscapeError):
            LandscapeSpec("curved", 1, (0, 0))

    def test_rejects_off_grid_target(self):
        with self.assertRaises(LandscapeError):
            LandscapeSpec("curved", 8, (8, 0))

    def test_rejects_budget_without_room_to_exploit(self):
        with self.assertRaises(LandscapeError):
            SearchBudget(5, 5)

    def test_rejects_budget_too_small_to_fit_a_line(self):
        with self.assertRaises(LandscapeError):
            SearchBudget(32, 1)

    def test_rejects_mismatched_budget_and_landscape(self):
        spec = LandscapeSpec("curved", 16, (3, 3))
        with self.assertRaises(LandscapeError):
            run_policy(spec, SearchBudget(32, 3), RANDOM_POLICY, seed=1)


class SurrogateEquivalence(unittest.TestCase):
    def test_fit_linear_matches_the_historical_implementation(self):
        rng = random.Random(11)
        for _ in range(200):
            observations = [
                (rng.randrange(64), rng.random()) for _ in range(3)
            ]
            self.assertEqual(fit_linear(observations), e38_fit_linear(observations))

    def test_constant_time_choice_matches_a_naive_scan(self):
        """The O(1) endpoint rule must agree with the original O(n) scan."""
        rng = random.Random(23)
        for _ in range(500):
            grid_size = rng.randrange(5, 40)
            explored = set(rng.sample(range(grid_size), 3))
            unseen = [y for y in range(grid_size) if y not in explored]
            slope = rng.uniform(-2, 2) if rng.random() < 0.8 else 0.0
            intercept = rng.uniform(-1, 1)
            naive = max(unseen, key=lambda y: (intercept + slope * y, y))
            fast = surrogate_choice(slope, unseen[0], unseen[-1])
            self.assertEqual(fast, naive, msg=f"slope={slope}")


class PolicyBehaviour(unittest.TestCase):
    def test_random_policy_never_fires_the_surrogate(self):
        spec = make_spec("curved", 32, seed=1)
        run = run_policy(spec, SearchBudget(32, 3), RANDOM_POLICY, seed=5)
        self.assertEqual(run.surrogate_uses, 0)

    def test_always_surrogate_fires_every_column(self):
        spec = make_spec("curved", 32, seed=1)
        run = run_policy(
            spec, SearchBudget(32, 3), ALWAYS_SURROGATE_POLICY, seed=5
        )
        self.assertEqual(run.surrogate_uses, 32)

    def test_run_spends_exactly_its_budget(self):
        budget = SearchBudget(48, 3)
        spec = make_spec("rugged", 48, seed=2)
        run = run_policy(spec, budget, E41_GATE_POLICY, seed=9)
        self.assertEqual(run.evaluations, budget.evaluations)

    def test_regret_is_the_complement_of_best_score(self):
        spec = make_spec("ridge", 24, seed=4)
        run = run_policy(spec, SearchBudget(24, 3), RANDOM_POLICY, seed=6)
        self.assertAlmostEqual(run.regret, 1.0 - run.best_score, places=12)
        self.assertGreaterEqual(run.regret, 0.0)

    def test_runs_are_deterministic_for_a_seed(self):
        spec = make_spec("checkerboard", 32, seed=8)
        budget = SearchBudget(32, 3)
        first = run_policy(spec, budget, E41_GATE_POLICY, seed=99)
        second = run_policy(spec, budget, E41_GATE_POLICY, seed=99)
        self.assertEqual(first, second)

    def test_surrogate_beats_random_on_a_smooth_family_at_scale(self):
        """The headroom check: on a wide smooth landscape the surrogate must
        show a clear advantage.  This is exactly what the 5x5 grid could not
        express, because random already enumerated 80% of it."""
        budget = SearchBudget(96, 3)
        surrogate_regret = []
        random_regret = []
        for seed in range(40):
            spec = make_spec("monotone", 96, seed=seed)
            surrogate_regret.append(
                run_policy(
                    spec, budget, ALWAYS_SURROGATE_POLICY, seed=seed
                ).regret
            )
            random_regret.append(
                run_policy(spec, budget, RANDOM_POLICY, seed=seed).regret
            )
        mean_surrogate = sum(surrogate_regret) / len(surrogate_regret)
        mean_random = sum(random_regret) / len(random_regret)
        self.assertLess(mean_surrogate, mean_random)

    def test_random_leaves_headroom_on_a_wide_grid(self):
        """If random already solved the task there would be nothing to measure."""
        budget = SearchBudget(96, 3)
        hits = 0
        for seed in range(40):
            spec = make_spec("spike", 96, seed=seed)
            if run_policy(spec, budget, RANDOM_POLICY, seed=seed).target_hit:
                hits += 1
        self.assertLessEqual(hits / 40, 0.2)


class PolicyConstruction(unittest.TestCase):
    def test_gate_fires_only_above_both_thresholds(self):
        policy = RouterPolicy("t", 0.5, 0.01)
        self.assertTrue(policy.fires(0.9, 0.02))
        self.assertFalse(policy.fires(0.4, 0.02))
        self.assertFalse(policy.fires(0.9, 0.001))


if __name__ == "__main__":
    unittest.main()
