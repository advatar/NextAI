"""E52: MeTTa lineage/query and promotion-governor parity experiment."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from compare_selection import _atomic_json

FIXTURES = (
    {"id": "supported_gain", "supported": 1, "gain": 0.0302, "regret": 0.0},
    {"id": "unsupported_gain", "supported": 0, "gain": 0.0302, "regret": 0.0},
    {"id": "supported_loss", "supported": 1, "gain": -0.01, "regret": 0.0},
    {"id": "supported_regret", "supported": 1, "gain": 0.05, "regret": -0.01},
    {"id": "zero_gain", "supported": 1, "gain": 0.0, "regret": 0.0},
    {"id": "unsupported_regret", "supported": 0, "gain": 0.05, "regret": -0.01},
)
RULES = ("base", "ignore-support", "ignore-regret")


def python_governor(supported: int, gain: float, regret: float) -> bool:
    return supported == 1 and gain > 0 and regret >= 0


def metta_bool(metta, rule: str, fixture: dict) -> bool:
    expression = (
        f"!(promote-{rule} {fixture['supported']} "
        f"{fixture['gain']} {fixture['regret']})"
    )
    values = [str(atom) for group in metta.run(expression) for atom in group]
    if values not in (["True"], ["False"]):
        raise ValueError(f"unexpected MeTTa result for {expression}: {values}")
    return values == ["True"]


def query(metta, expression: str) -> list[str]:
    return [str(atom) for group in metta.run(expression) for atom in group]


def main() -> None:
    try:
        from hyperon import MeTTa
        import hyperon
    except ImportError as error:
        raise SystemExit(
            "Run with: uv run --python 3.12 --with hyperon python "
            "run_e52_metta_parity.py"
        ) from error
    source_path = Path(__file__).parent / "metta" / "e52_governor.metta"
    metta = MeTTa()
    metta.run(source_path.read_text())
    decisions = []
    for fixture in FIXTURES:
        expected = python_governor(
            fixture["supported"], fixture["gain"], fixture["regret"]
        )
        row = {"fixture": fixture, "python": expected, "metta": {}}
        for rule in RULES:
            row["metta"][rule] = metta_bool(metta, rule, fixture)
        decisions.append(row)
    parity = all(row["python"] == row["metta"]["base"] for row in decisions)
    mutation_scores = {
        rule: sum(row["python"] == row["metta"][rule] for row in decisions)
        for rule in RULES
    }
    lineage_queries = {
        "e45_parent": query(metta, "!(match &self (parent E45 $p) $p)"),
        "all_parents": query(
            metta, "!(match &self (parent $child $parent) ($child $parent))"
        ),
        "e44_revision": query(metta, "!(match &self (revised-by E44 $x) $x)"),
        "e50_rejection": query(metta, "!(match &self (rejected-by E50 $x) $x)"),
    }
    expected_queries = {
        "e45_parent": ["E41"],
        "all_parents": [
            "(E39 E38)",
            "(E41 E39)",
            "(E43 E41)",
            "(E45 E41)",
            "(E49 E41)",
        ],
        "e44_revision": ["E45"],
        "e50_rejection": ["E51"],
    }
    query_parity = lineage_queries == expected_queries
    report = {
        "schema_version": 1,
        "experiment_id": "E52-metta-parity",
        "claim_boundary": (
            "isolated Hyperon/MeTTa feasibility test for symbolic lineage, "
            "promotion-rule parity, and auditable rule-mutation rejection"
        ),
        "hyperon_version": getattr(hyperon, "__version__", "unknown"),
        "metta_source": str(source_path.relative_to(Path(__file__).parent)),
        "decision_fixtures": len(FIXTURES),
        "decision_parity": parity,
        "query_parity": query_parity,
        "decisions": decisions,
        "mutation_scores": mutation_scores,
        "lineage_queries": lineage_queries,
        "expected_queries": expected_queries,
        "adoption_gate": {
            "decision_parity_required": True,
            "query_parity_required": True,
            "weakened_mutations_must_score_below_base": True,
            "passed": (
                parity
                and query_parity
                and mutation_scores["base"] == len(FIXTURES)
                and mutation_scores["ignore-support"] < mutation_scores["base"]
                and mutation_scores["ignore-regret"] < mutation_scores["base"]
            ),
        },
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(Path("experiments/E52-metta-parity.json"), report)
    print(
        f"decision_parity={parity} query_parity={query_parity} "
        f"mutation_scores={mutation_scores} "
        f"adoption_gate={report['adoption_gate']['passed']}"
    )


if __name__ == "__main__":
    main()
