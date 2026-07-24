"""E23: clamp contract normalization: numeric inputs only."""

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
    cases = [(-1.5, 0), (10.5, 10), (1, 1), (9, 9)]
    rows = []
    for r in d["rows"]:
        if r["task"] != "clamp":
            continue
        ns = {}
        exec(r["candidate"], ns)
        f = ns["solve"]
        passed = 0
        for x, e in cases:
            try:
                passed += f(x) == e
            except Exception:
                pass
        rows.append({"index": r["index"], "passed": passed, "total": len(cases)})
    report = {
        "schema_version": 1,
        "experiment_id": "E23-clamp-contract",
        "claim_boundary": "numeric-only clamp contract; nonnumeric inputs excluded by specification",
        "contract": {
            "input": "int or float",
            "output": "clamped numeric in [0,10]",
            "nonnumeric": "out of scope",
        },
        "proposals": rows,
        "pass_rate": sum(r["passed"] for r in rows) / sum(r["total"] for r in rows),
    }
    report["report_digest"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    _atomic_json(Path("experiments/E23-clamp-contract.json"), report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
