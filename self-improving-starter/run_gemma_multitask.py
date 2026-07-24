"""E17: shared local-Gemma budget across three independent contracts."""

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
from recursive_lab.quality_diversity import CandidateEvaluation

TASKS = {
    "increment": (
        "Return a complete Python module defining solve(n) that returns n + 1.",
        lambda f: all(f(n) == n + 1 for n in (-3, 0, 4, 19)),
    ),
    "square": (
        "Return a complete Python module defining solve(n) that returns n squared.",
        lambda f: all(f(n) == n * n for n in (-4, -1, 0, 3, 8)),
    ),
    "clamp": (
        "Return a complete Python module defining solve(n) that clamps n to the inclusive range 0..10.",
        lambda f: all(f(n) == max(0, min(10, n)) for n in (-5, 0, 3, 10, 99)),
    ),
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--calls", type=int, default=18)
    p.add_argument(
        "--out", type=Path, default=Path("experiments/E17-gemma-multitask.json")
    )
    add_unsafe_local_demo_argument(p)
    a = p.parse_args()
    require_unsafe_local_demo(p, a.unsafe_local_demo)
    from gemma_agent_lab.backends.base import ChatMessage
    from gemma_agent_lab.backends.openai_compatible import OpenAICompatibleBackend

    model = "/Users/johansellstrom/dev/advatar/Broom/diskspace-gemma/models/gemma-4-e2b-it-4bit-mlx"
    backend = OpenAICompatibleBackend(
        SimpleNamespace(
            model=model,
            base_url="http://127.0.0.1:12345/v1",
            api_key_env=None,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
    )
    rng = random.Random(17)
    rows = []
    archives = {k: [] for k in TASKS}
    archive_records = {k: [] for k in TASKS}
    parents = {
        k: ProgramRecord(
            "seed",
            "def solve(n):\n    return n\n",
            CandidateEvaluation(0.0, (0.0,), {}),
            0,
            None,
            (),
            "seed",
        )
        for k in TASKS
    }
    proposers = {
        k: LongemmaProposer(backend, v[0], message_factory=ChatMessage)
        for k, v in TASKS.items()
    }
    for i in range(a.calls):
        key = list(TASKS)[i % 3]
        sample = PromptSample(
            parents[key],
            tuple(archive_records[key][-2:]),
            {"previous_scores": [x["score"] for x in archives[key][-3:]]},
        )
        candidate = proposers[key].propose(sample, rng)
        ns = {}
        score = 0
        try:
            exec(candidate, ns)
            score = 1.0 if TASKS[key][1](ns["solve"]) else 0.0
        except Exception:
            pass
        row = {"task": key, "index": i + 1, "score": score, "candidate": candidate}
        rows.append(row)
        if score >= (archives[key][-1]["score"] if archives[key] else -1):
            archives[key].append(row)
            parents[key] = ProgramRecord(
                f"{key}-{i}",
                candidate,
                CandidateEvaluation(score, (score,), {}),
                i,
                None,
                (),
                "gemma",
            )
            archive_records[key].append(parents[key])
    backend.close()
    summaries = {
        k: {
            "calls": len([r for r in rows if r["task"] == k]),
            "best_score": max(r["score"] for r in rows if r["task"] == k),
            "archive_size": len(archives[k]),
        }
        for k in TASKS
    }
    report = {
        "schema_version": 1,
        "experiment_id": "E17-gemma-multitask",
        "claim_boundary": "three synthetic contracts under a shared local-model budget; no general learning claim",
        "calls": a.calls,
        "summaries": summaries,
        "rows": rows,
        "receipts": {k: [asdict(x) for x in v.receipts] for k, v in proposers.items()},
    }
    report["report_digest"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    _atomic_json(a.out, report)
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
