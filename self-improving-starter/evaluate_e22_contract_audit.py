"""E22: audit and correct the increment adversarial oracle."""

import argparse
import hashlib
import json
from pathlib import Path

from compare_selection import _atomic_json
from recursive_lab.local_execution import (
    add_unsafe_local_demo_argument,
    require_unsafe_local_demo,
)


def main():
    parser = argparse.ArgumentParser()
    add_unsafe_local_demo_argument(parser)
    args = parser.parse_args()
    require_unsafe_local_demo(parser, args.unsafe_local_demo)
    d = json.loads(Path("experiments/E17-gemma-multitask.json").read_text())
    rows = []
    cases = {
        "increment": [(-1.5, 0.5), (True, 2), (0.0, 1.0)],
        "square": [(-1.5, 2.25), (True, 1), (0.0, 0.0)],
        "clamp": [(-1.5, 0), (10.5, 10), (None, None), ("3", 3)],
    }
    corrected = {"increment": [(-1.5, -0.5), (True, 2), (0.0, 1.0)]}
    for r in d["rows"]:
        ns = {}
        exec(r["candidate"], ns)
        f = ns["solve"]
        checks = corrected.get(r["task"], cases[r["task"]])
        passed = 0
        for x, e in checks:
            try:
                passed += f(x) == e
            except Exception:
                pass
        rows.append(
            {
                "task": r["task"],
                "old_expected": cases[r["task"]][0][1],
                "corrected_passed": passed,
                "total": len(checks),
            }
        )
    summaries = {
        k: {
            "proposals": sum(r["task"] == k for r in rows),
            "corrected_rate": sum(r["corrected_passed"] for r in rows if r["task"] == k)
            / sum(r["total"] for r in rows if r["task"] == k),
        }
        for k in cases
    }
    report = {
        "schema_version": 1,
        "experiment_id": "E22-contract-audit",
        "claim_boundary": "oracle correction; no model-generation claim",
        "correction": "increment(-1.5) = -0.5, not 0.5",
        "summaries": summaries,
        "rows": rows,
    }
    report["report_digest"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    _atomic_json(Path("experiments/E22-contract-audit.json"), report)
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
