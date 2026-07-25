"""E36: replay E35 with two Gemma explorations then surrogate exploitation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from compare_selection import _atomic_json
from run_e32_structured_policy import objective


def recommend(observations: list[tuple[int, float]]) -> tuple[int, float, float]:
    """Fit score = intercept + slope*y and maximize over unseen integer y."""
    if len(observations) != 2:
        raise ValueError("the two-sample surrogate requires exactly two observations")
    (y1, score1), (y2, score2) = observations
    if y1 == y2:
        raise ValueError("observations must use distinct y values")
    slope = (score2 - score1) / (y2 - y1)
    intercept = score1 - slope * y1
    unseen = [y for y in range(5) if y not in {y1, y2}]
    chosen = max(unseen, key=lambda y: (intercept + slope * y, y))
    return chosen, slope, intercept + slope * chosen


def main() -> None:
    source_path = Path("experiments/E35-coarse-niches.json")
    source = json.loads(source_path.read_text())
    rows = []
    best_score = objective((0, 0))
    first_target_evaluation = None
    # E35 round 1 and 2 provide ten real-Gemma exploration evaluations.
    for x in range(5):
        exploration = [
            row
            for row in source["rows"]
            if row["assigned_x"] == x and row["round"] <= 2
        ]
        observations = [
            (int(row["returned_y"]), float(row["objective"])) for row in exploration
        ]
        chosen_y, slope, predicted_score = recommend(observations)
        actual_score = objective((x, chosen_y))
        best_score = max(best_score, actual_score)
        evaluation_index = 10 + x + 1
        if actual_score == 1.0 and first_target_evaluation is None:
            first_target_evaluation = evaluation_index
        rows.append(
            {
                "assigned_x": x,
                "observations": [
                    {"y": y, "score": score} for y, score in observations
                ],
                "estimated_slope": slope,
                "chosen_y": chosen_y,
                "predicted_score": predicted_score,
                "actual_score": actual_score,
                "target": actual_score == 1.0,
            }
        )
    report = {
        "schema_version": 1,
        "experiment_id": "E36-surrogate-hybrid",
        "claim_boundary": (
            "deterministic replay analysis using E35's first ten real-model "
            "evaluations plus five surrogate-selected evaluations; synthetic objective only"
        ),
        "source_experiment": "E35-coarse-niches",
        "gemma_exploration_calls": 10,
        "surrogate_evaluations": 5,
        "total_candidate_evaluations": 15,
        "best_objective": best_score,
        "target_hit": best_score == 1.0,
        "first_target_evaluation": first_target_evaluation,
        "rows": rows,
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(Path("experiments/E36-surrogate-hybrid.json"), report)
    print(
        f"best={best_score:.3f} target={report['target_hit']} "
        f"first_target_evaluation={first_target_evaluation}"
    )
    for row in rows:
        print(
            f"x={row['assigned_x']} slope={row['estimated_slope']:.3f} "
            f"choose_y={row['chosen_y']} actual={row['actual_score']:.3f}"
        )


if __name__ == "__main__":
    main()
