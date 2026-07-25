"""E32: matched-budget structured greedy, sampling, and novelty emitters."""
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

POLICIES = ("greedy", "sampling", "novelty")


def objective(point: tuple[int, int]) -> float:
    x, y = point
    if point == (0, 0):
        return 0.8
    if point == (4, 4):
        return 1.0
    return 0.1 + 0.6 * ((x + y) / 8)


def prompt_for(
    policy: str,
    occupied: set[tuple[int, int]],
    best_point: tuple[int, int],
    best_score: float,
) -> str:
    contract = (
        'Return JSON only as {"x": integer, "y": integer}. '
        "Each coordinate must be from 0 through 4. "
        "The objective formula and optimum are hidden. "
    )
    if policy == "greedy":
        return (
            contract
            + f"The best point so far is {best_point} with score {best_score:.3f}. "
            "Choose a point expected to improve that score."
        )
    if policy == "sampling":
        return contract + "Choose a point to evaluate."
    summary = ",".join(f"({x},{y})" for x, y in sorted(occupied))
    return (
        contract
        + f"Already evaluated: [{summary}]. Choose an unexplored point. "
        "Maximize exploration and never repeat."
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--calls", type=int, default=10)
    parser.add_argument("--base-url", default="http://127.0.0.1:12345/v1")
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E32-structured-policy.json")
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
        for policy_index, policy in enumerate(POLICIES):
            rng = random.Random(32000 + seed_index * 10 + policy_index)
            occupied = {(0, 0)}
            best_point = (0, 0)
            best_score = objective(best_point)
            rows = []
            for call in range(1, args.calls + 1):
                prompt = prompt_for(policy, occupied, best_point, best_score)
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
                if score > best_score:
                    best_point, best_score = point, score
                usage = response.usage
                receipts.append(
                    {
                        "policy": policy,
                        "run_seed": seed_index,
                        "call": call,
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
                    "policy": policy,
                    "seed": seed_index,
                    "best_score": best_score,
                    "target_hit": best_score == 1.0,
                    "unique_points": len(occupied),
                    "valid_responses": sum(row["point"] is not None for row in rows),
                    "novel_proposals": sum(bool(row["novel"]) for row in rows),
                    "rows": rows,
                }
            )
            print(
                f"seed={seed_index} policy={policy} best={best_score:.3f} "
                f"target={best_score == 1.0} unique={len(occupied)}"
            )
    backend.close()

    summaries = {}
    for policy in POLICIES:
        cohort = [run for run in runs if run["policy"] == policy]
        summaries[policy] = {
            "runs": len(cohort),
            "mean_best_score": math.fsum(run["best_score"] for run in cohort)
            / len(cohort),
            "target_hit_rate": sum(run["target_hit"] for run in cohort) / len(cohort),
            "mean_unique_points": math.fsum(
                run["unique_points"] for run in cohort
            )
            / len(cohort),
            "valid_response_rate": math.fsum(
                run["valid_responses"] for run in cohort
            )
            / (len(cohort) * args.calls),
        }
    report = {
        "schema_version": 1,
        "experiment_id": "E32-structured-policy",
        "claim_boundary": (
            "five seeded matched-budget real-model runs on one synthetic opaque "
            "objective; exploratory comparison, not broad learning evidence"
        ),
        "model": MODEL,
        "seeds": args.seeds,
        "calls_per_policy_run": args.calls,
        "matched_model_calls": True,
        "summaries": summaries,
        "runs": runs,
        "receipts": receipts,
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
