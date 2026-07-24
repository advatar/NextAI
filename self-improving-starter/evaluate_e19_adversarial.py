"""E19: adversarial robustness checks for E17 proposals."""

import argparse
import hashlib
import json
from pathlib import Path

from compare_selection import _atomic_json
from recursive_lab.local_execution import (
    add_unsafe_local_demo_argument,
    require_unsafe_local_demo,
)

CASES = {
    "increment": [(-1.5, 0.5), (True, 2), (0.0, 1.0)],
    "square": [(-1.5, 2.25), (True, 1), (0.0, 0.0)],
    "clamp": [(-1.5, 0), (10.5, 10), (None, None), ("3", 3)],
}


def main():
    parser = argparse.ArgumentParser()
    add_unsafe_local_demo_argument(parser)
    args = parser.parse_args()
    require_unsafe_local_demo(parser, args.unsafe_local_demo)
    d = json.loads(Path("experiments/E17-gemma-multitask.json").read_text())
    rows = []
    for r in d["rows"]:
        ns = {}
        passed = []
        try:
            exec(r["candidate"], ns)
            f = ns["solve"]
        except Exception:
            f = None
        for x, expected in CASES[r["task"]]:
            try:
                passed.append(f(x) == expected if f else False)
            except Exception:
                passed.append(False)
        rows.append(
            {
                "task": r["task"],
                "index": r["index"],
                "passed": sum(passed),
                "total": len(passed),
            }
        )
    summaries = {
        k: {
            "proposals": sum(r["task"] == k for r in rows),
            "adversarial_pass_rate": sum(r["passed"] for r in rows if r["task"] == k)
            / sum(r["total"] for r in rows if r["task"] == k),
        }
        for k in CASES
    }
    report = {
        "schema_version": 1,
        "experiment_id": "E19-adversarial-holdout",
        "claim_boundary": "adversarial robustness of E17 proposals; type/error policy is not part of the original contract",
        "summaries": summaries,
        "rows": rows,
    }
    report["report_digest"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    _atomic_json(Path("experiments/E19-adversarial-holdout.json"), report)
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
