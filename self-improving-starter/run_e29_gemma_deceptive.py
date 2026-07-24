"""E29: real-Gemma greedy versus QD search on an opaque deceptive objective."""

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
from recursive_lab.local_execution import (
    add_unsafe_local_demo_argument,
    require_unsafe_local_demo,
)
from recursive_lab.longemma_adapter import LongemmaProposer
from recursive_lab.quality_diversity import CandidateEvaluation, QualityDiversityArchive

MODEL = "/Users/johansellstrom/dev/advatar/Broom/diskspace-gemma/models/gemma-4-e2b-it-4bit-mlx"
SEED_PROGRAM = "def solve():\n    return (0, 0)\n"


def evaluate(program: str) -> CandidateEvaluation:
    namespace: dict[str, object] = {}
    try:
        exec(program, namespace)
        point = namespace["solve"]()
        if (
            not isinstance(point, tuple)
            or len(point) != 2
            or any(type(value) is not int or not 0 <= value <= 4 for value in point)
        ):
            raise ValueError("solve() must return two integers in [0,4]")
        x, y = point
        if point == (0, 0):
            objective = 0.8
        elif point == (4, 4):
            objective = 1.0
        else:
            objective = 0.1 + 0.6 * ((x + y) / 8)
        return CandidateEvaluation(objective, (x / 4, y / 4), {"x": x / 4, "y": y / 4})
    except Exception:
        return CandidateEvaluation(0.0, (0.0, 0.0), {"x": 0.0, "y": 0.0})


def run_policy(
    policy: str,
    proposer: LongemmaProposer,
    generations: int,
    proposals_per_generation: int,
    seed: int,
) -> dict:
    rng = random.Random(seed)
    seed_evaluation = evaluate(SEED_PROGRAM)
    champion = ProgramRecord(
        f"{policy}-seed",
        SEED_PROGRAM,
        seed_evaluation,
        0,
        None,
        (),
        "seed",
    )
    archive: QualityDiversityArchive[ProgramRecord[str]] = QualityDiversityArchive(
        bins=(5, 5)
    )
    archive.add(champion, seed_evaluation, 0)
    rows = []

    for generation in range(1, generations + 1):
        for proposal_index in range(1, proposals_per_generation + 1):
            if policy == "greedy":
                parent = champion
                inspirations: tuple[ProgramRecord[str], ...] = ()
            else:
                selected = archive.select_parent(rng)
                parent = selected if selected is not None else champion
                pool = [
                    entry.candidate
                    for entry in archive.entries
                    if entry.candidate.program_id != parent.program_id
                ]
                inspirations = tuple(rng.sample(pool, min(2, len(pool))))
            feedback = {
                "objective": parent.evaluation.objective,
                "x_feature": parent.evaluation.metrics["x"],
                "y_feature": parent.evaluation.metrics["y"],
                "archive_coverage": len(archive.entries) / 25,
            }
            candidate = proposer.propose(
                PromptSample(parent, inspirations, feedback), rng
            )
            evaluation = evaluate(candidate)
            record = ProgramRecord(
                hashlib.sha256(
                    f"{policy}:{generation}:{proposal_index}:{candidate}".encode()
                ).hexdigest(),
                candidate,
                evaluation,
                generation,
                parent.program_id,
                tuple(item.program_id for item in inspirations),
                "gemma",
            )
            accepted = (
                evaluation.objective > champion.evaluation.objective
                if policy == "greedy"
                else archive.add(record, evaluation, generation)
            )
            if evaluation.objective > champion.evaluation.objective:
                champion = record
            rows.append(
                {
                    "generation": generation,
                    "proposal": proposal_index,
                    "objective": evaluation.objective,
                    "features": list(evaluation.features),
                    "accepted": accepted,
                    "best_objective": champion.evaluation.objective,
                    "occupied_cells": len(archive.entries),
                    "candidate": candidate,
                }
            )
    return {
        "policy": policy,
        "best_objective": champion.evaluation.objective,
        "target_hit": champion.evaluation.objective == 1.0,
        "occupied_cells": len(archive.entries),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generations", type=int, default=5)
    parser.add_argument("--proposals", type=int, default=4)
    parser.add_argument("--base-url", default="http://127.0.0.1:12345/v1")
    add_unsafe_local_demo_argument(parser)
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E29-gemma-deceptive.json")
    )
    args = parser.parse_args()
    require_unsafe_local_demo(parser, args.unsafe_local_demo)
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
    task = (
        "Return a complete Python module defining solve() with no arguments. "
        "It must return a tuple of two integer constants, each from 0 through 4. "
        "Improve the opaque objective using only parent feedback and inspirations. "
        "Explore different valid points; the objective formula and optimum are hidden."
    )
    proposers = {
        policy: LongemmaProposer(
            backend, task, name=f"gemma-{policy}", message_factory=ChatMessage
        )
        for policy in ("greedy", "quality_diversity")
    }
    results = [
        run_policy(
            policy,
            proposers[policy],
            args.generations,
            args.proposals,
            29,
        )
        for policy in ("greedy", "quality_diversity")
    ]
    backend.close()
    report = {
        "schema_version": 1,
        "experiment_id": "E29-gemma-deceptive",
        "claim_boundary": (
            "one seeded real-model comparison on a synthetic opaque objective; "
            "exploratory evidence, not a statistical recursive-improvement claim"
        ),
        "model": MODEL,
        "generations": args.generations,
        "proposals_per_generation": args.proposals,
        "matched_model_calls": True,
        "results": results,
        "receipts": {
            policy: [asdict(receipt) for receipt in proposer.receipts]
            for policy, proposer in proposers.items()
        },
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)
    for result in results:
        print(
            f"{result['policy']}: best={result['best_objective']:.3f} "
            f"target={result['target_hit']} cells={result['occupied_cells']}"
        )


if __name__ == "__main__":
    main()
