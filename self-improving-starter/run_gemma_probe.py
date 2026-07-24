"""E14: one real local Gemma proposal through the Longemma adapter."""

from __future__ import annotations

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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:12345/v1")
    parser.add_argument(
        "--out", type=Path, default=Path("experiments/E14-gemma-probe.json")
    )
    add_unsafe_local_demo_argument(parser)
    args = parser.parse_args()
    require_unsafe_local_demo(parser, args.unsafe_local_demo)
    try:
        from gemma_agent_lab.backends.base import ChatMessage
        from gemma_agent_lab.backends.openai_compatible import OpenAICompatibleBackend
    except ImportError as error:
        raise SystemExit(
            "Run this command in Longemma's uv environment with NExtAI on PYTHONPATH"
        ) from error
    model = "/Users/johansellstrom/dev/advatar/Broom/diskspace-gemma/models/gemma-4-e2b-it-4bit-mlx"
    config = SimpleNamespace(
        model=model,
        base_url=args.base_url,
        api_key_env=None,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    backend = OpenAICompatibleBackend(config)
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
    candidate = proposer.propose(PromptSample(parent, (), {}), random.Random(13))
    backend.close()
    namespace = {}
    exec(candidate, namespace)
    solve = namespace["solve"]
    cases = (-10, -1, 0, 1, 7, 100)
    correct = all(solve(n) == n + 1 for n in cases)
    receipt = proposer.receipts[0]
    report = {
        "schema_version": 1,
        "experiment_id": "E14-gemma-probe",
        "claim_boundary": "one real local Gemma generation and external correctness probe; no capability or recursive-improvement claim",
        "model": model,
        "backend": "openai_compatible",
        "base_url": args.base_url,
        "candidate": candidate,
        "cases": list(cases),
        "correct": correct,
        "receipt": asdict(receipt),
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(args.out, report)
    print(f"Gemma proposal: {'PASS' if correct else 'FAIL'}; wrote {args.out}")
    if not correct:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
