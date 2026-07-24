"""E16: generous local-Gemma proposal budget with archive retention."""

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


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--calls", type=int, default=12)
    p.add_argument(
        "--out", type=Path, default=Path("experiments/E16-gemma-budget.json")
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
    parent = ProgramRecord(
        "seed",
        "def solve(n):\n    return n\n",
        CandidateEvaluation(0.0, (0.0,), {}),
        0,
        None,
        (),
        "seed",
    )
    proposer = LongemmaProposer(
        backend,
        "Return a complete Python module defining solve(n) that returns n + 1.",
        message_factory=ChatMessage,
    )
    archive = []
    archive_records = []
    rows = []
    rng = random.Random(16)
    cases = (-10, -1, 0, 1, 7, 100)
    for i in range(a.calls):
        inspirations = tuple(archive_records[-2:])
        sample = PromptSample(
            parent,
            inspirations,
            {"previous_scores": [x["score"] for x in archive[-3:]]},
        )
        started = time.time()
        candidate = proposer.propose(sample, rng)
        ns = {}
        score = 0
        try:
            exec(candidate, ns)
            score = sum(ns["solve"](n) == n + 1 for n in cases) / len(cases)
        except Exception:
            score = 0
        row = {
            "index": i + 1,
            "score": score,
            "candidate": candidate,
            "latency_seconds": time.time() - started,
        }
        rows.append(row)
        if score >= (archive[-1]["score"] if archive else -1):
            archive.append(row)
            parent = ProgramRecord(
                f"gemma-{i}",
                candidate,
                CandidateEvaluation(score, (score,), {}),
                i,
                None,
                (),
                "gemma",
            )
            archive_records.append(parent)
    backend.close()
    report = {
        "schema_version": 1,
        "experiment_id": "E16-gemma-budget",
        "claim_boundary": "local model budget probe; correctness on one synthetic contract, not general learning",
        "calls": a.calls,
        "best_score": max(x["score"] for x in rows),
        "archive_size": len(archive),
        "rows": rows,
        "receipts": [asdict(x) for x in proposer.receipts],
    }
    report["report_digest"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    _atomic_json(a.out, report)
    print(f"calls={a.calls} best={report['best_score']:.0%} archive={len(archive)}")


if __name__ == "__main__":
    main()
