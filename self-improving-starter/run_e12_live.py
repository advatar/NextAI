"""E12: paid, model-backed program evolution on the executable benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

from compare_selection import TASKS, VARIANTS, _atomic_json
from recursive_lab.local_execution import (
    add_unsafe_local_demo_argument,
    require_unsafe_local_demo,
)
from recursive_lab.quality_diversity import CandidateEvaluation, QualityDiversityArchive
from recursive_lab.task_harness import ExecutableTaskSuite


def load_env(path=Path(".env")):
    for line in path.read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def evaluate(suite, program):
    results = [suite.evaluate(program[t], task_id=t)[0] for t in TASKS]
    utilities = tuple(max(0, min(1, r.reward)) if r.correct else 0 for r in results)
    return CandidateEvaluation(
        sum(utilities) / 3,
        (*utilities, sum(r.correct for r in results) / 3),
        {
            **{t: u for t, u in zip(TASKS, utilities)},
            "correct_fraction": sum(r.correct for r in results) / 3,
        },
    )


def propose(client, model, policy, parent, inspirations, seed, max_tokens):
    prompts = {
        t: ExecutableTaskSuite((t,), correctness_only=True).manifest[0]["prompt"]
        for t in TASKS
    }
    payload = {
        "policy": policy,
        "seed": seed,
        "task_prompts": prompts,
        "parent": parent,
        "inspirations": inspirations,
        "instruction": "Return complete, distinct Python modules. Improve runtime while preserving exact contracts.",
    }
    started = time.monotonic()
    response = client.responses.create(
        model=model,
        instructions="You are an evolutionary coding model. Emit only the required JSON. Never use imports, I/O, networking, introspection, or test references.",
        input=json.dumps(payload, sort_keys=True),
        max_output_tokens=max_tokens,
        text={
            "format": {
                "type": "json_schema",
                "name": "program_portfolio",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": list(TASKS),
                    "properties": {task: {"type": "string"} for task in TASKS},
                },
            }
        },
    )
    text = response.output_text
    usage = getattr(response, "usage", None)
    return json.loads(text), {
        "request_id": response.id,
        "tokens": int(getattr(usage, "total_tokens", 0) or 0),
        "response_digest": hashlib.sha256(text.encode()).hexdigest(),
        "wall_seconds": time.monotonic() - started,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--proposals", type=int, default=4)
    p.add_argument("--seeds", type=int, default=2)
    p.add_argument("--max-output-tokens", type=int, default=3000)
    p.add_argument("--out", default="runs/E12-live.json")
    add_unsafe_local_demo_argument(p)
    a = p.parse_args()
    require_unsafe_local_demo(p, a.unsafe_local_demo)
    load_env()
    from openai import OpenAI

    model = os.environ["RECURSIVE_MODEL"]
    client = OpenAI()
    suite = ExecutableTaskSuite(TASKS, correctness_only=False)
    initial = {t: VARIANTS[t][0] for t in TASKS}
    initial_eval = evaluate(suite, initial)
    runs = []
    for seed in range(a.seeds):
        for policy in ("greedy", "random_sampling", "alphaevolve"):
            champion = initial
            champion_eval = initial_eval
            database = [(initial, initial_eval)]
            archive = QualityDiversityArchive(bins=(2, 2, 2, 2))
            archive.add(initial, initial_eval, 0)
            attempts = []
            for step in range(a.proposals):
                parent = champion if policy != "random_sampling" else initial
                inspirations = (
                    []
                    if policy != "alphaevolve"
                    else [
                        entry.candidate
                        for entry in archive.entries
                        if entry.candidate != parent
                    ][:2]
                )
                try:
                    candidate, receipt = propose(
                        client,
                        model,
                        policy,
                        parent,
                        inspirations,
                        seed * 1000 + step,
                        a.max_output_tokens,
                    )
                    result = evaluate(suite, candidate)
                    accepted = result.objective > champion_eval.objective
                    if result.objective > champion_eval.objective:
                        champion, champion_eval = candidate, result
                    database.append((candidate, result))
                    if policy == "alphaevolve":
                        archive.add(candidate, result, step + 1)
                    attempts.append(
                        {
                            "step": step + 1,
                            "status": "evaluated",
                            "objective": result.objective,
                            "metrics": result.metrics,
                            "accepted_as_champion": accepted,
                            "source_digests": {
                                t: hashlib.sha256(candidate[t].encode()).hexdigest()
                                for t in TASKS
                            },
                            **receipt,
                        }
                    )
                except Exception as error:
                    attempts.append(
                        {
                            "step": step + 1,
                            "status": "failed",
                            "error_type": type(error).__name__,
                        }
                    )
            runs.append(
                {
                    "policy": policy,
                    "seed": seed,
                    "proposal_budget": a.proposals,
                    "attempts": attempts,
                    "best_objective": champion_eval.objective,
                    "best_metrics": champion_eval.metrics,
                    "model_calls": len(attempts),
                    "successful_evaluations": sum(
                        x["status"] == "evaluated" for x in attempts
                    ),
                }
            )
    report = {
        "schema_version": 1,
        "experiment_id": "E12-live-model-code-evolution",
        "claim_boundary": "small paid model-backed executable pilot; no statistical or recursive-improvement claim",
        "model": model,
        "benchmark_manifest_digest": suite.manifest_digest,
        "tasks": list(TASKS),
        "budget": {
            "proposals_per_run": a.proposals,
            "seeds": a.seeds,
            "max_output_tokens": a.max_output_tokens,
        },
        "matched_model_call_budget": all(r["model_calls"] == a.proposals for r in runs),
        "initial_objective": initial_eval.objective,
        "runs": runs,
    }
    canonical = json.dumps(
        report, allow_nan=False, sort_keys=True, separators=(",", ":")
    )
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(Path(a.out), report)
    for r in runs:
        print(
            r["policy"],
            r["seed"],
            f"best={r['best_objective']:.3f}",
            f"evals={r['successful_evaluations']}/{a.proposals}",
        )


if __name__ == "__main__":
    main()
