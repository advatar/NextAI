"""Scale-parameterized synthetic landscapes with measurable search headroom.

Why this module exists
----------------------

Experiments E30-E50 searched nine synthetic families defined on a fixed 5x5
score table.  The search budget was three exploration samples per column plus
one exploitation choice per column, so a run evaluated ``5 * 4 == 20`` of the
grid's ``5 * 5 == 25`` cells.  Every policy therefore enumerated 80% of the
search space, and the reported metric was a *binary* ``target_hit``.

That instrument cannot measure what the project wants to measure.  E43's paired
promoted-minus-random advantage was ``0.0038``; E40 recorded ``1.0`` for every
policy on every held-out family, a ceiling tie.  E51 finally audited the cohort
and rejected it (``admitted: false``) precisely because random exploration alone
already reached the target 80% of the time.  No search policy can demonstrate an
advantage over random when random samples four fifths of the universe.

This module fixes the instrument along the two axes that were broken:

1. **Coverage.**  The grid size is a parameter, so the fraction of the space a
   run may evaluate is a knob rather than a constant.  Coverage is
   ``(exploration_per_column + 1) / grid_size`` -- it depends only on the grid
   size, so widening the grid is what buys headroom.  At ``grid_size=5`` this
   reproduces the historical 0.8; at ``grid_size=256`` it is about 0.016.

2. **Metric.**  ``target_hit`` is binary and saturates: it sits at the ceiling
   on a small grid and collapses to the floor on a large one, so it is
   uninformative at both ends.  Every family here scores exactly ``1.0`` at its
   target, so ``regret = 1.0 - best_score`` is well defined, continuous, and
   retains resolution at any scale.  Regret is the primary metric; target hit
   rate is retained only as a secondary diagnostic.

Strict generalization
---------------------

Each family below reduces *exactly* to its historical 5x5 definition when
``grid_size == 5``.  The historical magic numbers were all expressions of the
grid extent: ``/4`` is ``/(grid_size - 1)``, ``/32`` is
``/(2 * (grid_size - 1) ** 2)``, ``/8`` is ``/(2 * (grid_size - 1))``, ``% 5``
is ``% grid_size``, and the decoy corner ``(4 - tx, 4 - ty)`` is
``(grid_size - 1 - tx, grid_size - 1 - ty)``.  ``tests/test_scaled_landscape.py``
asserts cell-for-cell equality against the original implementations in
``compare_e37_surrogate_generalization.py``, ``compare_e40_unseen_families.py``
and ``compare_e42_second_audit.py``, so this is a widening of the old benchmark
rather than a different one.  Existing experiment evidence stays valid at the
scale it was collected; it simply has no headroom at that scale.

Nothing in this module reads or writes experiment evidence, and no function here
consults the policy under test when deciding whether a cohort is informative.
That decision belongs to :mod:`recursive_lab.admission`, which judges a cohort
by what a *random baseline* achieves on it.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from typing import Iterable, Sequence

FAMILIES: tuple[str, ...] = (
    "monotone",
    "curved",
    "spike",
    "plateau",
    "checkerboard",
    "rugged",
    "ridge",
    "sinusoidal",
    "decoy",
)

#: Families whose score surface is smooth enough that a linear surrogate fitted
#: down a column carries real signal.  Kept as documentation of intent: the
#: router is expected to discriminate these from the rest, and a benchmark on
#: which it cannot is not informative.
SMOOTH_FAMILIES: tuple[str, ...] = ("monotone", "curved", "ridge")

#: The historical grid size used by E30-E50.  Retained so tests can pin the
#: reduction, not because it is a useful scale to experiment at.
LEGACY_GRID_SIZE = 5


class LandscapeError(ValueError):
    """Raised when a landscape or budget is not well formed."""


def _require_grid_size(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LandscapeError(
            f"grid_size must be an integer, not {type(value).__name__}"
        )
    if value < 2:
        raise LandscapeError("grid_size must be at least 2")
    return value


@dataclass(frozen=True)
class LandscapeSpec:
    """One concrete scoring surface: a family, a scale, a target, a seed."""

    family: str
    grid_size: int
    target: tuple[int, int]
    landscape_seed: int = 0

    def __post_init__(self) -> None:
        if self.family not in FAMILIES:
            raise LandscapeError(f"unknown family {self.family!r}")
        _require_grid_size(self.grid_size)
        if len(self.target) != 2:
            raise LandscapeError("target must be an (x, y) pair")
        for coordinate in self.target:
            if isinstance(coordinate, bool) or not isinstance(coordinate, int):
                raise LandscapeError("target coordinates must be integers")
            if not 0 <= coordinate < self.grid_size:
                raise LandscapeError(
                    f"target coordinate {coordinate} is outside the grid"
                )

    @property
    def extent(self) -> int:
        """The largest valid coordinate; the historical ``4`` at grid size 5."""
        return self.grid_size - 1

    @property
    def cells(self) -> int:
        return self.grid_size * self.grid_size


def optimum(spec: LandscapeSpec) -> float:
    """Every family scores exactly ``1.0`` at its target.

    This is what makes ``regret`` well defined without an O(n^2) sweep of the
    grid, and it is asserted for every family in the tests rather than assumed.
    """
    return 1.0


def score(spec: LandscapeSpec, point: tuple[int, int]) -> float:
    """Score ``point`` on ``spec``, reducing exactly to the 5x5 definitions."""
    x, y = point
    target_x, target_y = spec.target
    extent = spec.extent

    if spec.family == "monotone":
        x_term = x / extent if target_x == extent else (extent - x) / extent
        y_term = y / extent if target_y == extent else (extent - y) / extent
        return (x_term + y_term) / 2

    if spec.family == "curved":
        spread = 2 * extent * extent
        return 1.0 - ((x - target_x) ** 2 + (y - target_y) ** 2) / spread

    if point == (target_x, target_y):
        return 1.0

    if spec.family == "spike":
        # The historical form was ``0.2 + 0.02 * ((x + y) % 5)``, spanning
        # [0.2, 0.28].  Scaling the modulus alone would let the noise floor
        # exceed the target's 1.0 on a wide grid, so the *range* is held fixed
        # and the pattern is normalised by the extent.  Identical at size 5.
        return 0.2 + 0.08 * ((x + y) % spec.grid_size) / extent

    if spec.family == "plateau":
        return 0.4

    if spec.family == "checkerboard":
        return 0.55 if (x + y) % 2 == 0 else 0.25

    if spec.family == "rugged":
        digest = hashlib.sha256(
            f"{spec.landscape_seed}:{x}:{y}".encode()
        ).digest()
        return 0.1 + 0.7 * int.from_bytes(digest[:2], "big") / 65535

    if spec.family == "ridge":
        span = 2 * extent
        offset = abs((x - y) - (target_x - target_y))
        return 0.2 + 0.6 * (1 - offset / span)

    if spec.family == "sinusoidal":
        return 0.5 + 0.3 * math.sin((x + 1) * (y + 1))

    # decoy
    decoy = (extent - target_x, extent - target_y)
    if point == decoy:
        return 0.9
    # Historically ``0.1 + 0.1 * ((x + 2 * y) % 5)``, spanning [0.1, 0.5].  As
    # with ``spike``, the range is pinned and the pattern normalised so the
    # floor cannot overtake the target.  Identical at size 5.
    return 0.1 + 0.4 * ((x + 2 * y) % spec.grid_size) / extent


@dataclass(frozen=True)
class SearchBudget:
    """A per-column exploration/exploitation budget over a square grid."""

    grid_size: int
    exploration_per_column: int = 3

    def __post_init__(self) -> None:
        _require_grid_size(self.grid_size)
        if (
            isinstance(self.exploration_per_column, bool)
            or not isinstance(self.exploration_per_column, int)
        ):
            raise LandscapeError("exploration_per_column must be an integer")
        if self.exploration_per_column < 2:
            raise LandscapeError(
                "exploration_per_column must be at least 2 to fit a line"
            )
        if self.exploration_per_column >= self.grid_size:
            raise LandscapeError(
                "exploration_per_column must leave at least one unseen cell "
                "per column for exploitation"
            )

    @property
    def evaluations(self) -> int:
        return self.grid_size * (self.exploration_per_column + 1)

    @property
    def search_space(self) -> int:
        return self.grid_size * self.grid_size

    @property
    def coverage(self) -> float:
        """Fraction of the space a single run may evaluate.

        Note this reduces to ``(exploration_per_column + 1) / grid_size``: the
        column count cancels, so only a wider grid buys headroom.  Adding
        exploration samples per column makes coverage *worse*.
        """
        return self.evaluations / self.search_space


@dataclass(frozen=True)
class RouterPolicy:
    """A confidence-gated exploitation rule.

    The historical policies are all points in this space:
    ``random`` is ``(1.01, 0.0)`` -- an R^2 threshold above the attainable
    maximum, so the surrogate never fires -- and ``always_surrogate`` is
    ``(0.0, 0.0)``.  E41's promoted gate is ``(0.5, 0.01)``.
    """

    name: str
    r_squared_threshold: float
    variance_threshold: float

    def fires(self, r_squared: float, variance: float) -> bool:
        return (
            r_squared >= self.r_squared_threshold
            and variance >= self.variance_threshold
        )


RANDOM_POLICY = RouterPolicy("random", 1.01, 0.0)
ALWAYS_SURROGATE_POLICY = RouterPolicy("always_surrogate", 0.0, 0.0)
E41_GATE_POLICY = RouterPolicy("e41_gate", 0.5, 0.01)


def fit_linear(
    observations: Sequence[tuple[int, float]]
) -> tuple[float, float, float]:
    """Least-squares fit down a column; identical to ``compare_e38``'s."""
    mean_y = math.fsum(y for y, _ in observations) / len(observations)
    mean_score = math.fsum(value for _, value in observations) / len(observations)
    denominator = math.fsum((y - mean_y) ** 2 for y, _ in observations)
    slope = (
        0.0
        if denominator == 0
        else math.fsum(
            (y - mean_y) * (value - mean_score) for y, value in observations
        )
        / denominator
    )
    intercept = mean_score - slope * mean_y
    residual = math.fsum(
        (value - (intercept + slope * y)) ** 2 for y, value in observations
    )
    total = math.fsum((value - mean_score) ** 2 for _, value in observations)
    r_squared = 1.0 if total == 0 and residual == 0 else 1.0 - residual / total
    return slope, intercept, r_squared


def surrogate_choice(
    slope: float, unseen_low: int, unseen_high: int
) -> int:
    """Argmax of a line over the unseen cells, in constant time.

    The historical implementation scanned every unseen cell with
    ``max(unseen, key=lambda y: (intercept + slope * y, y))``.  For a linear
    predictor the maximiser is always an endpoint of the unseen range, and the
    ``(value, y)`` tie-break selects the larger index when the slope is flat.
    Scanning is O(grid_size) per column, which is what made the historical
    runners too slow to widen; this is O(1) and the tests assert it agrees with
    a naive scan on random inputs.
    """
    return unseen_high if slope >= 0 else unseen_low


@dataclass(frozen=True)
class PolicyRun:
    """The outcome of one policy on one landscape under one budget."""

    family: str
    policy: str
    grid_size: int
    evaluations: int
    best_score: float
    regret: float
    target_hit: bool
    surrogate_uses: int


def run_policy(
    spec: LandscapeSpec,
    budget: SearchBudget,
    policy: RouterPolicy,
    seed: int,
) -> PolicyRun:
    """Run one column-wise explore/exploit pass and report continuous regret."""
    if budget.grid_size != spec.grid_size:
        raise LandscapeError("budget and landscape grid sizes must agree")

    rng = random.Random(seed)
    grid_size = spec.grid_size
    best = -math.inf
    target_hit = False
    surrogate_uses = 0
    evaluations = 0

    for x in range(grid_size):
        explored = sorted(
            rng.sample(range(grid_size), budget.exploration_per_column)
        )
        observations = [(y, score(spec, (x, y))) for y in explored]
        evaluations += len(observations)
        for y, value in observations:
            if value > best:
                best = value
            if (x, y) == spec.target:
                target_hit = True

        explored_set = set(explored)
        unseen_low = next(y for y in range(grid_size) if y not in explored_set)
        unseen_high = next(
            y for y in reversed(range(grid_size)) if y not in explored_set
        )

        slope, _intercept, r_squared = fit_linear(observations)
        mean = math.fsum(value for _, value in observations) / len(observations)
        variance = math.fsum(
            (value - mean) ** 2 for _, value in observations
        ) / len(observations)

        if policy.fires(r_squared, variance):
            chosen = surrogate_choice(slope, unseen_low, unseen_high)
            surrogate_uses += 1
        else:
            chosen = rng.randrange(grid_size)
            while chosen in explored_set:
                chosen = rng.randrange(grid_size)

        value = score(spec, (x, chosen))
        evaluations += 1
        if value > best:
            best = value
        if (x, chosen) == spec.target:
            target_hit = True

    return PolicyRun(
        family=spec.family,
        policy=policy.name,
        grid_size=grid_size,
        evaluations=evaluations,
        best_score=best,
        regret=optimum(spec) - best,
        target_hit=target_hit,
        surrogate_uses=surrogate_uses,
    )


def make_spec(
    family: str, grid_size: int, seed: int, *, salt: int = 0
) -> LandscapeSpec:
    """Deterministically place a target for ``(family, grid_size, seed)``.

    ``monotone`` targets a corner, matching the historical construction: an
    interior target would make its two separable ramps unsatisfiable.
    """
    index = FAMILIES.index(family)
    rng = random.Random(salt + seed * len(FAMILIES) * 4 + index)
    extent = grid_size - 1
    if family == "monotone":
        target = (rng.choice((0, extent)), rng.choice((0, extent)))
    else:
        target = (rng.randrange(grid_size), rng.randrange(grid_size))
    return LandscapeSpec(
        family=family,
        grid_size=grid_size,
        target=target,
        landscape_seed=salt + 53000 + seed * len(FAMILIES) + index,
    )


def mean(values: Iterable[float]) -> float:
    collected = list(values)
    if not collected:
        raise LandscapeError("cannot take the mean of an empty sequence")
    return math.fsum(collected) / len(collected)


def bootstrap_ci(
    values: Sequence[float], seed: int, samples: int = 5000
) -> list[float]:
    """Percentile bootstrap interval; matches the existing runners' method."""
    if not values:
        raise LandscapeError("cannot bootstrap an empty sequence")
    rng = random.Random(seed)
    size = len(values)
    estimates = sorted(
        math.fsum(values[rng.randrange(size)] for _ in range(size)) / size
        for _ in range(samples)
    )
    return [estimates[int(samples * 0.025)], estimates[int(samples * 0.975)]]
