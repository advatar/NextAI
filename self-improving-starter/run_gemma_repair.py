import argparse
import hashlib
import json
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
    "increment": ("def solve(n):\n    return n - 1\n", "Return solve(n)=n+1."),
    "square": ("def solve(n):\n    return n * 3\n", "Return solve(n)=n squared."),
    "clamp": (
        "def solve(n):\n    return max(0,min(9,n))\n",
        "Return numeric solve(n) clamped to [0,10].",
    ),
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--out", type=Path, default=Path("experiments/E26-gemma-repair.json")
    )
    add_unsafe_local_demo_argument(p)
    a = p.parse_args()
    require_unsafe_local_demo(p, a.unsafe_local_demo)
    from gemma_agent_lab.backends.base import ChatMessage
    from gemma_agent_lab.backends.openai_compatible import OpenAICompatibleBackend

    b = OpenAICompatibleBackend(
        SimpleNamespace(
            model="/Users/johansellstrom/dev/advatar/Broom/diskspace-gemma/models/gemma-4-e2b-it-4bit-mlx",
            base_url="http://127.0.0.1:12345/v1",
            api_key_env=None,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
    )
    rows = []
    receipts = []
    import random

    for i, (k, (bug, task)) in enumerate(TASKS.items()):
        parent = ProgramRecord(
            "bug", bug, CandidateEvaluation(0.0, (0.0,), {}), 0, None, (), "seed"
        )
        pr = LongemmaProposer(
            b,
            "Repair the program using the failing feedback. "
            + task
            + " Return only a complete Python module.",
            message_factory=ChatMessage,
        )
        cand = pr.propose(
            PromptSample(
                parent, (), {"failure": "seeded implementation fails contract tests"}
            ),
            random.Random(26 + i),
        )
        ns = {}
        exec(cand, ns)
        f = ns["solve"]
        tests = {
            "increment": all(f(n) == n + 1 for n in (-10, 0, 7, 100)),
            "square": all(f(n) == n * n for n in (-9, -1, 0, 4, 12)),
            "clamp": all(f(n) == max(0, min(10, n)) for n in (-5, 0, 3, 10, 99)),
        }
        rows.append({"task": k, "candidate": cand, "pass": tests[k]})
        receipts += [asdict(x) for x in pr.receipts]
    b.close()
    r = {
        "schema_version": 1,
        "experiment_id": "E26-gemma-repair",
        "claim_boundary": "three local-Gemma seeded repairs; synthetic contracts only",
        "rows": rows,
        "receipts": receipts,
    }
    r["report_digest"] = hashlib.sha256(
        json.dumps(r, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    _atomic_json(a.out, r)
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
