"""Run NExtAI against BetaEvolve's exact shared E10 conformance fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from compare_selection import _atomic_json
from recursive_lab.quality_diversity import (
    CandidateEvaluation,
    MechanismValidationError,
    QualityDiversityArchive,
    SeededGenerator,
)


def verify(fixture_path: Path) -> dict:
    fixture = json.loads(fixture_path.read_text())
    dims = fixture["dimensions"]
    archive = QualityDiversityArchive(
        bins=tuple(d["bins"] for d in dims),
        bounds=tuple((d["lowerBound"], d["upperBound"]) for d in dims),
    )
    cells = []
    accepted = []
    for item in fixture["candidates"]:
        evaluation = CandidateEvaluation(item["objective"], tuple(item["features"]), {})
        cells.append(list(archive._cell(evaluation.features)))
        accepted.append(
            archive.add(
                item["label"],
                evaluation,
                item["generation"],
                item["parentID"],
                item["id"],
            )
        )
    expected = fixture["expected"]
    rng = SeededGenerator(expected["selectionSeed"])
    selected = [
        archive.select_entry_stable(rng).candidate
        for _ in range(expected["selectionCount"])
    ]
    elites = {
        ":".join(map(str, cell)): archive.entry_in_cell(cell).candidate
        for cell in sorted(archive._entries)
    }
    lineage = archive.entry_in_cell((0, 0))
    stats = archive.stats()
    checks = {
        "cells": cells == expected["cells"],
        "accepted": accepted == expected["accepted"],
        "elites": elites == expected["elitesByCell"],
        "selection": selected == expected["selectedLabels"],
        "statistics": stats["evaluations"] == expected["evaluations"]
        and stats["improvements"] == expected["improvements"]
        and stats["occupied_cells"] == expected["occupiedCells"]
        and stats["total_cells"] == expected["totalCells"]
        and stats["coverage"] == expected["coverage"],
        "lineage": lineage.candidate == expected["lineageLabel"]
        and lineage.parent_id == expected["lineageParentID"],
    }
    invalid_codes = []
    for kind in ("feature", "objective", "metric", "bound"):
        try:
            if kind == "feature":
                archive._cell((float("nan"), 0))
            elif kind == "objective":
                archive.add("bad", CandidateEvaluation(float("nan"), (0, 0), {}), 0)
            elif kind == "metric":
                archive.add(
                    "bad", CandidateEvaluation(0, (0, 0), {"x": float("inf")}), 0
                )
            else:
                QualityDiversityArchive(bins=(2,), bounds=((0, float("inf")),))
        except MechanismValidationError as error:
            invalid_codes.append(error.code)
    checks["invalid_codes"] = invalid_codes == [
        item["code"] for item in fixture["invalid"]
    ]
    return {
        "schema_version": 1,
        "experiment_id": "E10-three-way-archive-conformance",
        "fixture": "BetaEvolve@d8bb940:Packages/BetaEvolveMechanisms/Tests/Fixtures/e10_archive_conformance.json",
        "fixture_digest": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
        "checks": checks,
        "passed": all(checks.values()),
        "selected_labels": selected,
    }


def main():
    default = (
        Path(__file__).resolve().parents[2]
        / "BetaEvolve/Packages/BetaEvolveMechanisms/Tests/Fixtures/e10_archive_conformance.json"
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=default)
    parser.add_argument("--out", type=Path, default=Path("runs/E10-conformance.json"))
    args = parser.parse_args()
    report = verify(args.fixture)
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)
    print(f"E10 NExtAI conformance: {'PASS' if report['passed'] else 'FAIL'}")
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
