"""E33: controlled prompt perturbations for independent novelty trajectories."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
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
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--calls", type=int, default=15)
    parser.add_argument("--base-url", default="http://127.0.0.1:12345/v1")
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E33-prompt-perturbation.json")
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
    runs = []
    receipts = []
    for seed_index in range(args.seeds):
        rng = random.Random(33000 + seed_index)
        occupied = {(0, 0)}
        best_score = objective((0, 0))
        rows = []
        for call in range(1, args.calls + 1):
            ordered = list(occupied)
            rng.shuffle(ordered)
            summary = ",".join(f"({x},{y})" for x, y in ordered)
            ticket = rng.randrange(1_000_000_000)
            prompt = (
                'Return JSON only as {"x": integer, "y": integer}. '
                "Each coordinate must be from 0 through 4. The objective formula "
                "and optimum are hidden. Choose an unexplored point and never repeat. "
                f"Already evaluated: [{summary}]. Exploration ticket: {ticket}."
            )
            generation_seed = rng.randrange(2**63)
            started = time.monotonic()
            response = backend.generate(
                [ChatMessage(role="user", content=prompt)],
                temperature=1.0,
                top_p=0.95,
                seed=generation_seed,
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
            score = 0.0 if point is None else objective(point)
            if point is not None:
                occupied.add(point)
            best_score = max(best_score, score)
            usage = response.usage
            receipts.append(
                {
                    "run_seed": seed_index,
                    "call": call,
                    "ticket": ticket,
                    "seed": generation_seed,
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
                    "call": call,
                    "point": None if point is None else list(point),
                    "novel": novel,
                    "score": score,
                    "best_score": best_score,
                }
            )
        runs.append(
            {
                "seed": seed_index,
                "best_score": best_score,
                "target_hit": best_score == 1.0,
                "first_target_call": next(
                    (row["call"] for row in rows if row["score"] == 1.0), None
                ),
                "unique_points": len(occupied),
                "valid_responses": sum(row["point"] is not None for row in rows),
                "novel_proposals": sum(bool(row["novel"]) for row in rows),
                "rows": rows,
            }
        )
        print(
            f"seed={seed_index} best={best_score:.3f} target={best_score == 1.0} "
            f"unique={len(occupied)}"
        )
    backend.close()
    trajectories = [
        tuple(
            None if row["point"] is None else tuple(row["point"])
            for row in run["rows"]
        )
        for run in runs
    ]
    report = {
        "schema_version": 1,
        "experiment_id": "E33-prompt-perturbation",
        "claim_boundary": (
            "controlled prompt-perturbation study on one synthetic opaque objective; "
            "prompt-induced trajectories are independent conditions, not backend RNG seeds"
        ),
        "model": MODEL,
        "seeds": args.seeds,
        "calls_per_run": args.calls,
        "unique_trajectories": len(set(trajectories)),
        "target_hit_rate": sum(run["target_hit"] for run in runs) / len(runs),
        "mean_unique_points": math.fsum(run["unique_points"] for run in runs)
        / len(runs),
        "valid_response_rate": math.fsum(
            run["valid_responses"] for run in runs
        )
        / (len(runs) * args.calls),
        "runs": runs,
        "receipts": receipts,
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)
    print(
        f"unique_trajectories={report['unique_trajectories']}/{args.seeds} "
        f"target_hit_rate={report['target_hit_rate']:.1%}"
    )


if __name__ == "__main__":
    main()
