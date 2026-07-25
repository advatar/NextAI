"""E31: structured-JSON novelty emitter with mechanical program construction."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from pathlib import Path
from types import SimpleNamespace

from compare_selection import _atomic_json
from recursive_lab.quality_diversity import QualityDiversityArchive
from run_e29_gemma_deceptive import MODEL, SEED_PROGRAM, evaluate


def parse_point(text: str) -> tuple[int, int]:
    value = text.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        value = "\n".join(
            lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        ).strip()
    payload = json.loads(value)
    x, y = payload["x"], payload["y"]
    if type(x) is not int or type(y) is not int or not (0 <= x <= 4 and 0 <= y <= 4):
        raise ValueError("coordinates must be integers in [0,4]")
    return x, y


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generations", type=int, default=5)
    parser.add_argument("--proposals", type=int, default=4)
    parser.add_argument("--base-url", default="http://127.0.0.1:12345/v1")
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E31-structured-emitter.json")
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
    archive: QualityDiversityArchive[str] = QualityDiversityArchive(bins=(5, 5))
    seed_evaluation = evaluate(SEED_PROGRAM)
    archive.add(SEED_PROGRAM, seed_evaluation, 0)
    occupied = {(0, 0)}
    champion = SEED_PROGRAM
    champion_evaluation = seed_evaluation
    rows = []
    receipts = []
    rng = random.Random(31)

    for generation in range(1, args.generations + 1):
        for proposal_index in range(1, args.proposals + 1):
            occupied_summary = ",".join(
                f"({x},{y})" for x, y in sorted(occupied)
            )
            prompt = (
                'Return JSON only as {"x": integer, "y": integer}. '
                "Each coordinate must be from 0 through 4. Choose an unexplored "
                f"point. Already evaluated: [{occupied_summary}]. "
                "The objective is hidden; maximize exploration and never repeat."
            )
            seed = rng.randrange(2**63)
            started = time.monotonic()
            response = backend.generate(
                [ChatMessage(role="user", content=prompt)],
                temperature=1.0,
                top_p=0.95,
                seed=seed,
                max_tokens=64,
            )
            text = str(response.text)
            point = None
            error = None
            try:
                point = parse_point(text)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
            novel = point is not None and point not in occupied
            program = (
                None
                if point is None
                else f"def solve():\n    return ({point[0]}, {point[1]})\n"
            )
            evaluation = evaluate(program or "")
            accepted = False
            if program is not None:
                accepted = archive.add(program, evaluation, generation)
                occupied.add(point)
            if evaluation.objective > champion_evaluation.objective:
                champion, champion_evaluation = program or champion, evaluation
            usage = response.usage
            receipts.append(
                {
                    "seed": seed,
                    "prompt_digest": hashlib.sha256(prompt.encode()).hexdigest(),
                    "response_digest": hashlib.sha256(text.encode()).hexdigest(),
                    "prompt_tokens": int(usage.prompt_tokens),
                    "completion_tokens": int(usage.completion_tokens),
                    "total_tokens": int(usage.total_tokens),
                    "latency_seconds": time.monotonic() - started,
                    "parse_ok": point is not None,
                    "error": error,
                }
            )
            rows.append(
                {
                    "generation": generation,
                    "proposal": proposal_index,
                    "point": None if point is None else list(point),
                    "novel": novel,
                    "objective": evaluation.objective,
                    "best_objective": champion_evaluation.objective,
                    "accepted": accepted,
                    "occupied_cells": len(archive.entries),
                }
            )

    backend.close()
    report = {
        "schema_version": 1,
        "experiment_id": "E31-structured-emitter",
        "claim_boundary": (
            "single seeded real-model structured-emitter run on E29's synthetic "
            "opaque objective; exploratory evidence only"
        ),
        "model": MODEL,
        "generations": args.generations,
        "proposals_per_generation": args.proposals,
        "model_calls": len(receipts),
        "best_objective": champion_evaluation.objective,
        "target_hit": champion_evaluation.objective == 1.0,
        "occupied_cells": len(archive.entries),
        "unique_valid_points": len(occupied),
        "valid_responses": sum(bool(receipt["parse_ok"]) for receipt in receipts),
        "novel_proposals": sum(bool(row["novel"]) for row in rows),
        "rows": rows,
        "receipts": receipts,
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)
    print(
        f"best={report['best_objective']:.3f} target={report['target_hit']} "
        f"valid={report['valid_responses']}/{report['model_calls']} "
        f"novel={report['novel_proposals']} cells={report['occupied_cells']}"
    )


if __name__ == "__main__":
    main()
