"""E27: real local-Gemma multi-generation evolution with held-out promotion."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
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
from recursive_lab.quality_diversity import CandidateEvaluation

MODEL = "/Users/johansellstrom/dev/advatar/Broom/diskspace-gemma/models/gemma-4-e2b-it-4bit-mlx"
PUBLIC_CASES = (-4, -1, 0, 2, 5)
HELDOUT_CASES = (-101, -9, 1, 7, 23, 100)


def evaluate(program: str, cases: tuple[int, ...]) -> float:
    namespace: dict[str, object] = {}
    try:
        exec(program, namespace)
        solve = namespace["solve"]
        return sum(solve(n) == n * n + n + 1 for n in cases) / len(cases)
    except Exception:
        return 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generations", type=int, default=5)
    parser.add_argument("--proposals", type=int, default=2)
    parser.add_argument("--base-url", default="http://127.0.0.1:12345/v1")
    add_unsafe_local_demo_argument(parser)
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E27-gemma-recursive.json")
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
    proposer = LongemmaProposer(
        backend,
        "Improve the complete Python module. solve(n) must return n*n+n+1. "
        "Use the public feedback and archived inspirations. Return the complete module.",
        message_factory=ChatMessage,
    )
    seed_program = "def solve(n):\n    return n\n"
    parent = ProgramRecord(
        "seed",
        seed_program,
        CandidateEvaluation(evaluate(seed_program, PUBLIC_CASES), (0.0,), {}),
        0,
        None,
        (),
        "seed",
    )
    archive = [parent]
    best_heldout = evaluate(seed_program, HELDOUT_CASES)
    rng = random.Random(27)
    rows: list[dict[str, object]] = []

    for generation in range(1, args.generations + 1):
        generation_rows = []
        for proposal_index in range(args.proposals):
            inspirations = tuple(archive[-2:])
            feedback = {
                "parent_public_score": parent.evaluation.objective,
            }
            started = time.monotonic()
            candidate = proposer.propose(
                PromptSample(parent, inspirations, feedback), rng
            )
            public_score = evaluate(candidate, PUBLIC_CASES)
            heldout_score = evaluate(candidate, HELDOUT_CASES)
            promoted = heldout_score > best_heldout
            record = ProgramRecord(
                hashlib.sha256(candidate.encode()).hexdigest(),
                candidate,
                CandidateEvaluation(
                    public_score,
                    (public_score, heldout_score),
                    {"heldout_score": heldout_score},
                ),
                generation,
                parent.program_id,
                tuple(item.program_id for item in inspirations),
                "gemma",
            )
            archive.append(record)
            if promoted:
                parent = record
                best_heldout = heldout_score
            row = {
                "generation": generation,
                "proposal": proposal_index + 1,
                "program_id": record.program_id,
                "parent_id": record.parent_id,
                "inspiration_ids": list(record.inspiration_ids),
                "public_score": public_score,
                "heldout_score": heldout_score,
                "promoted": promoted,
                "latency_seconds": time.monotonic() - started,
                "candidate": candidate,
            }
            rows.append(row)
            generation_rows.append(row)
        best_public = max(float(row["public_score"]) for row in generation_rows)
        print(
            f"generation={generation} public={best_public:.0%} "
            f"heldout={best_heldout:.0%} promotions="
            f"{sum(bool(row['promoted']) for row in generation_rows)}"
        )

    backend.close()
    report = {
        "schema_version": 1,
        "experiment_id": "E27-gemma-recursive",
        "claim_boundary": (
            "five-generation local-Gemma program evolution on one synthetic "
            "contract; promotion requires held-out improvement"
        ),
        "model": MODEL,
        "generations": args.generations,
        "proposals_per_generation": args.proposals,
        "public_cases": list(PUBLIC_CASES),
        "heldout_cases": list(HELDOUT_CASES),
        "initial_heldout_score": evaluate(seed_program, HELDOUT_CASES),
        "best_heldout_score": best_heldout,
        "promotions": sum(bool(row["promoted"]) for row in rows),
        "archive_size": len(archive),
        "rows": rows,
        "receipts": [asdict(receipt) for receipt in proposer.receipts],
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
