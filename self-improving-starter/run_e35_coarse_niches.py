"""E35: coarse external niches with Gemma optimizing inside each assigned row."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from pathlib import Path
from types import SimpleNamespace

from compare_selection import _atomic_json
from run_e29_gemma_deceptive import MODEL
from run_e32_structured_policy import objective


def parse_y(text: str) -> int:
    value = text.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        value = "\n".join(
            lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        ).strip()
    y = json.loads(value)["y"]
    if type(y) is not int or not 0 <= y <= 4:
        raise ValueError("y must be an integer in [0,4]")
    return y


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=4)
    parser.add_argument("--seed", type=int, default=35)
    parser.add_argument("--base-url", default="http://127.0.0.1:12345/v1")
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E35-coarse-niches.json")
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
    rng = random.Random(args.seed)
    observations: dict[int, list[tuple[int, float]]] = {x: [] for x in range(5)}
    rows = []
    receipts = []
    best_score = objective((0, 0))
    first_target_call = None
    call = 0
    for round_index in range(1, args.rounds + 1):
        row_order = list(range(5))
        rng.shuffle(row_order)
        for x in row_order:
            call += 1
            observed = ", ".join(
                f"y={y}:score={score:.3f}" for y, score in observations[x]
            )
            if not observed:
                observed = "none"
            prompt = (
                'Return JSON only as {"y": integer}. y must be from 0 through 4. '
                f"The external scheduler assigns row x={x}. Prior evaluations in "
                f"this row: [{observed}]. Choose an unevaluated y expected to "
                "improve the opaque objective. Its formula and optimum are hidden."
            )
            generation_seed = rng.randrange(2**63)
            started = time.monotonic()
            response = backend.generate(
                [ChatMessage(role="user", content=prompt)],
                temperature=1.0,
                top_p=0.95,
                seed=generation_seed,
                max_tokens=32,
            )
            text = str(response.text)
            y = None
            error = None
            try:
                y = parse_y(text)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
            novel_within_niche = y is not None and all(
                previous_y != y for previous_y, _ in observations[x]
            )
            score = 0.0 if y is None else objective((x, y))
            if y is not None:
                observations[x].append((y, score))
            best_score = max(best_score, score)
            if score == 1.0 and first_target_call is None:
                first_target_call = call
            usage = response.usage
            receipts.append(
                {
                    "call": call,
                    "seed": generation_seed,
                    "prompt_digest": hashlib.sha256(prompt.encode()).hexdigest(),
                    "response_digest": hashlib.sha256(text.encode()).hexdigest(),
                    "prompt_tokens": int(usage.prompt_tokens),
                    "completion_tokens": int(usage.completion_tokens),
                    "total_tokens": int(usage.total_tokens),
                    "latency_seconds": time.monotonic() - started,
                    "parse_ok": y is not None,
                    "error": error,
                }
            )
            rows.append(
                {
                    "call": call,
                    "round": round_index,
                    "assigned_x": x,
                    "returned_y": y,
                    "novel_within_niche": novel_within_niche,
                    "objective": score,
                    "best_objective": best_score,
                }
            )
    backend.close()
    covered = {
        (row["assigned_x"], row["returned_y"])
        for row in rows
        if row["returned_y"] is not None
    }
    report = {
        "schema_version": 1,
        "experiment_id": "E35-coarse-niches",
        "claim_boundary": (
            "single seeded coarse-niche optimization run on one synthetic opaque "
            "objective; scheduler assigns x while Gemma chooses y"
        ),
        "model": MODEL,
        "rounds": args.rounds,
        "model_calls": len(rows),
        "valid_responses": sum(receipt["parse_ok"] for receipt in receipts),
        "novel_within_niche": sum(row["novel_within_niche"] for row in rows),
        "covered_cells": len(covered),
        "best_objective": best_score,
        "target_hit": best_score == 1.0,
        "first_target_call": first_target_call,
        "rows": rows,
        "receipts": receipts,
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)
    print(
        f"valid={report['valid_responses']}/{report['model_calls']} "
        f"novel={report['novel_within_niche']}/{report['model_calls']} "
        f"cells={report['covered_cells']} target={report['target_hit']} "
        f"call={report['first_target_call']}"
    )


if __name__ == "__main__":
    main()
