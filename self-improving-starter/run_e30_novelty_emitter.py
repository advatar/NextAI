"""E30: real-Gemma compact novelty emitter on E29's opaque objective."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

from compare_selection import _atomic_json
from recursive_lab.alphaevolve import ProgramRecord, PromptSample
from recursive_lab.longemma_adapter import LongemmaProposer
from recursive_lab.quality_diversity import QualityDiversityArchive
from run_e29_gemma_deceptive import MODEL, SEED_PROGRAM, evaluate


def point_for(program: str) -> tuple[int, int] | None:
    namespace: dict[str, object] = {}
    try:
        exec(program, namespace)
        point = namespace["solve"]()
        if (
            isinstance(point, tuple)
            and len(point) == 2
            and all(type(value) is int and 0 <= value <= 4 for value in point)
        ):
            return point
    except Exception:
        pass
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generations", type=int, default=5)
    parser.add_argument("--proposals", type=int, default=4)
    parser.add_argument("--base-url", default="http://127.0.0.1:12345/v1")
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E30-novelty-emitter.json")
    )
    args = parser.parse_args()
    from gemma_agent_lab.backends.base import ChatMessage
    from gemma_agent_lab.backends.openai_compatible import OpenAICompatibleBackend

    backend = OpenAICompatibleBackend(
        SimpleNamespace(
            model=MODEL,
            base_url=args.base_url,
            api_key_env=None,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
    )
    seed_evaluation = evaluate(SEED_PROGRAM)
    champion = ProgramRecord(
        "seed", SEED_PROGRAM, seed_evaluation, 0, None, (), "seed"
    )
    archive: QualityDiversityArchive[ProgramRecord[str]] = QualityDiversityArchive(
        bins=(5, 5)
    )
    archive.add(champion, seed_evaluation, 0)
    occupied = {(0, 0)}
    receipts = []
    rows = []
    rng = random.Random(30)

    for generation in range(1, args.generations + 1):
        for proposal_index in range(1, args.proposals + 1):
            parent = archive.select_parent(rng) or champion
            occupied_summary = ", ".join(
                f"({x},{y})" for x, y in sorted(occupied)
            )
            task = (
                "Return a complete Python module defining solve() with no arguments. "
                "solve() must return a tuple of two integer constants from 0 through 4. "
                "The objective is opaque. Explore a point not previously evaluated. "
                f"Occupied points: [{occupied_summary}]. "
                "Do not repeat an occupied point. The objective formula and optimum are hidden."
            )
            proposer = LongemmaProposer(
                backend,
                task,
                name="gemma-novelty",
                message_factory=ChatMessage,
            )
            candidate = proposer.propose(
                PromptSample(
                    parent,
                    (),
                    {
                        "parent_objective": parent.evaluation.objective,
                        "archive_coverage": len(archive.entries) / 25,
                    },
                ),
                rng,
            )
            receipts.extend(proposer.receipts)
            evaluation = evaluate(candidate)
            point = point_for(candidate)
            novel = point is not None and point not in occupied
            record = ProgramRecord(
                hashlib.sha256(
                    f"{generation}:{proposal_index}:{candidate}".encode()
                ).hexdigest(),
                candidate,
                evaluation,
                generation,
                parent.program_id,
                (),
                "gemma-novelty",
            )
            accepted = archive.add(record, evaluation, generation)
            if point is not None:
                occupied.add(point)
            if evaluation.objective > champion.evaluation.objective:
                champion = record
            rows.append(
                {
                    "generation": generation,
                    "proposal": proposal_index,
                    "point": None if point is None else list(point),
                    "novel": novel,
                    "objective": evaluation.objective,
                    "best_objective": champion.evaluation.objective,
                    "accepted": accepted,
                    "occupied_cells": len(archive.entries),
                }
            )

    backend.close()
    report = {
        "schema_version": 1,
        "experiment_id": "E30-novelty-emitter",
        "claim_boundary": (
            "single seeded real-model novelty-emitter run on a synthetic opaque "
            "objective; direct comparison to E29 uses the same 20-call budget"
        ),
        "model": MODEL,
        "generations": args.generations,
        "proposals_per_generation": args.proposals,
        "model_calls": len(receipts),
        "best_objective": champion.evaluation.objective,
        "target_hit": champion.evaluation.objective == 1.0,
        "occupied_cells": len(archive.entries),
        "unique_valid_points": len(occupied),
        "novel_proposals": sum(bool(row["novel"]) for row in rows),
        "rows": rows,
        "receipts": [asdict(receipt) for receipt in receipts],
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)
    print(
        f"best={report['best_objective']:.3f} target={report['target_hit']} "
        f"cells={report['occupied_cells']} novel={report['novel_proposals']}/"
        f"{report['model_calls']}"
    )


if __name__ == "__main__":
    main()
