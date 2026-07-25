"""E34: external coverage scheduler with structured Gemma niche compliance."""
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
from run_e31_structured_emitter import parse_point
from run_e32_structured_policy import objective


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=34)
    parser.add_argument("--base-url", default="http://127.0.0.1:12345/v1")
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E34-coverage-scheduler.json")
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
    assignments = [(x, y) for x in range(5) for y in range(5)]
    rng.shuffle(assignments)
    rows = []
    receipts = []
    best_score = 0.0
    first_target_call = None
    for call, assigned in enumerate(assignments, 1):
        prompt = (
            'Return JSON only as {"x": integer, "y": integer}. '
            f"The external archive scheduler assigns niche x={assigned[0]}, y={assigned[1]}. "
            "Return exactly that assigned coordinate."
        )
        generation_seed = rng.randrange(2**63)
        started = time.monotonic()
        response = backend.generate(
            [ChatMessage(role="user", content=prompt)],
            temperature=0.0,
            top_p=1.0,
            seed=generation_seed,
            max_tokens=32,
        )
        text = str(response.text)
        returned = None
        error = None
        try:
            returned = parse_point(text)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        compliant = returned == assigned
        score = objective(returned) if returned is not None else 0.0
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
                "parse_ok": returned is not None,
                "error": error,
            }
        )
        rows.append(
            {
                "call": call,
                "assigned": list(assigned),
                "returned": None if returned is None else list(returned),
                "compliant": compliant,
                "objective": score,
                "best_objective": best_score,
            }
        )
    backend.close()
    report = {
        "schema_version": 1,
        "experiment_id": "E34-coverage-scheduler",
        "claim_boundary": (
            "single seeded compliance test for externally scheduled synthetic "
            "archive niches; demonstrates coverage control, not model learning"
        ),
        "model": MODEL,
        "scheduler_seed": args.seed,
        "assignments": len(assignments),
        "valid_responses": sum(receipt["parse_ok"] for receipt in receipts),
        "compliant_responses": sum(row["compliant"] for row in rows),
        "covered_assigned_cells": len(
            {tuple(row["returned"]) for row in rows if row["compliant"]}
        ),
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
        f"valid={report['valid_responses']}/25 "
        f"compliant={report['compliant_responses']}/25 "
        f"covered={report['covered_assigned_cells']}/25 "
        f"target={report['target_hit']} call={report['first_target_call']}"
    )


if __name__ == "__main__":
    main()
