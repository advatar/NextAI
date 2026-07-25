"""E46: real-Gemma exploration plus support-aware engine exploitation."""
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
from compare_e37_surrogate_generalization import score
from compare_e38_adaptive_emitter import fit_linear
from run_e29_gemma_deceptive import MODEL
from run_e35_coarse_niches import parse_y

TASKS = {
    "monotone": (4, 4),
    "curved": (2, 3),
    "spike": (4, 4),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:12345/v1")
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E46-real-router.json")
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
    rng = random.Random(46)
    receipts = []
    tasks = []
    for family, target in TASKS.items():
        observations: dict[int, list[tuple[int, float]]] = {x: [] for x in range(5)}
        exploration_rows = []
        for round_index in range(1, 4):
            order = list(range(5))
            rng.shuffle(order)
            for x in order:
                prior = ", ".join(
                    f"y={y}:score={value:.3f}"
                    for y, value in observations[x]
                ) or "none"
                prompt = (
                    'Return JSON only as {"y": integer}. y must be from 0 through 4. '
                    f"The engine assigns row x={x}. Prior evaluations in this row: "
                    f"[{prior}]. Choose an unevaluated y for the opaque {family} "
                    "task. The objective formula and optimum are hidden."
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
                novel = y is not None and all(
                    previous_y != y for previous_y, _ in observations[x]
                )
                value = 0.0 if y is None else score(family, (x, y), target)
                if y is not None:
                    observations[x].append((y, value))
                usage = response.usage
                receipts.append(
                    {
                        "family": family,
                        "round": round_index,
                        "x": x,
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
                exploration_rows.append(
                    {
                        "round": round_index,
                        "x": x,
                        "y": y,
                        "novel": novel,
                        "score": value,
                    }
                )
        exploitation = {"support_guard": [], "random_control": []}
        policy_points = {
            policy: [
                (x, y) for x, items in observations.items() for y, _ in items
            ]
            for policy in exploitation
        }
        control_rng = random.Random(4600 + list(TASKS).index(family))
        for x in range(5):
            items = observations[x]
            valid_ys = {y for y, _ in items}
            unseen = [y for y in range(5) if y not in valid_ys]
            if not unseen:
                continue
            if len(items) >= 3:
                slope, intercept, r_squared = fit_linear(items[:3])
                mean = math.fsum(value for _, value in items[:3]) / 3
                variance = math.fsum(
                    (value - mean) ** 2 for _, value in items[:3]
                ) / 3
            else:
                slope, intercept, r_squared, variance = 0.0, 0.0, 0.0, 0.0
            use_surrogate = r_squared >= 0.5 and variance >= 0.01
            guarded_y = (
                max(unseen, key=lambda y: (intercept + slope * y, y))
                if use_surrogate
                else control_rng.choice(unseen)
            )
            random_y = control_rng.choice(unseen)
            for policy, y in (
                ("support_guard", guarded_y),
                ("random_control", random_y),
            ):
                value = score(family, (x, y), target)
                exploitation[policy].append(
                    {
                        "x": x,
                        "y": y,
                        "score": value,
                        "used_surrogate": use_surrogate
                        if policy == "support_guard"
                        else False,
                        "r_squared": r_squared,
                        "variance": variance,
                    }
                )
                policy_points[policy].append((x, y))
        summaries = {}
        for policy, points in policy_points.items():
            values = [score(family, point, target) for point in points]
            summaries[policy] = {
                "candidate_evaluations": len(points),
                "best_score": max(values),
                "target_hit": target in points,
            }
        tasks.append(
            {
                "family": family,
                "target": list(target),
                "exploration": exploration_rows,
                "exploitation": exploitation,
                "summaries": summaries,
            }
        )
        print(f"{family}: {summaries}")
    backend.close()
    report = {
        "schema_version": 1,
        "experiment_id": "E46-real-router",
        "claim_boundary": (
            "single real-model exploration run per supported synthetic family "
            "with matched engine-side exploitation counterfactuals"
        ),
        "model": MODEL,
        "families": list(TASKS),
        "gemma_calls": len(receipts),
        "valid_response_rate": sum(item["parse_ok"] for item in receipts)
        / len(receipts),
        "novel_response_rate": sum(
            row["novel"] for task in tasks for row in task["exploration"]
        )
        / len(receipts),
        "tasks": tasks,
        "receipts": receipts,
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)


if __name__ == "__main__":
    main()
