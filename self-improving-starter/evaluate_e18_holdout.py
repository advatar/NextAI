"""E18: hidden edge-case evaluation of the E17 local-Gemma archive."""

import argparse
import hashlib
import json
from pathlib import Path

from compare_selection import _atomic_json
from recursive_lab.local_execution import (
    add_unsafe_local_demo_argument,
    require_unsafe_local_demo,
)

HIDDEN = {
    "increment": lambda f: all(f(n) == n + 1 for n in (-(10**6), -999, 2, 31, 10**6)),
    "square": lambda f: all(f(n) == n * n for n in (-100, -7, 2, 17, 123)),
    "clamp": lambda f: all(
        f(n) == max(0, min(10, n)) for n in (-(10**6), -1, 1, 9, 10, 11, 10**6)
    ),
}


def main():
    parser = argparse.ArgumentParser()
    add_unsafe_local_demo_argument(parser)
    args = parser.parse_args()
    require_unsafe_local_demo(parser, args.unsafe_local_demo)
    src = Path("experiments/E17-gemma-multitask.json")
    data = json.loads(src.read_text())
    rows = []
    for row in data["rows"]:
        ns = {}
        ok = False
        try:
            exec(row["candidate"], ns)
            ok = bool(HIDDEN[row["task"]](ns["solve"]))
        except Exception:
            pass
        rows.append(
            {
                "task": row["task"],
                "index": row["index"],
                "visible_score": row["score"],
                "hidden_pass": ok,
            }
        )
    summaries = {
        k: {
            "proposals": sum(r["task"] == k for r in rows),
            "hidden_pass_rate": sum(r["task"] == k and r["hidden_pass"] for r in rows)
            / sum(r["task"] == k for r in rows),
        }
        for k in HIDDEN
    }
    report = {
        "schema_version": 1,
        "experiment_id": "E18-hidden-holdout",
        "claim_boundary": "hidden edge-case evaluation of E17 proposals; no generalization claim beyond these cases",
        "source_experiment": "E17-gemma-multitask",
        "summaries": summaries,
        "rows": rows,
    }
    report["report_digest"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    _atomic_json(Path("experiments/E18-hidden-holdout.json"), report)
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
