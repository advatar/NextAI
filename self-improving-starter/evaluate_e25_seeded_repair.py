"""E25: seeded-bug repair regression."""

import hashlib
import json
from pathlib import Path

from compare_selection import _atomic_json

TASKS = {
    "increment": (
        "def solve(n):\n    return n - 1\n",
        "def solve(n):\n    return n + 1\n",
        lambda f: all(f(n) == n + 1 for n in (-10, 0, 7, 100)),
    ),
    "square": (
        "def solve(n):\n    return n * 3\n",
        "def solve(n):\n    return n ** 2\n",
        lambda f: all(f(n) == n * n for n in (-9, -1, 0, 4, 12)),
    ),
    "clamp": (
        "def solve(n):\n    return max(0, min(9, n))\n",
        "def solve(n):\n    return max(0, min(10, n))\n",
        lambda f: all(f(n) == max(0, min(10, n)) for n in (-5, 0, 3, 10, 99)),
    ),
}


def main():
    rows = []
    for task, (bug, repair, check) in TASKS.items():
        ns = {}
        exec(bug, ns)
        bug_ok = check(ns["solve"])
        ns = {}
        exec(repair, ns)
        rows.append(
            {
                "task": task,
                "seeded_bug_passes": bug_ok,
                "repair_passes": check(ns["solve"]),
            }
        )
    report = {
        "schema_version": 1,
        "experiment_id": "E25-seeded-repair",
        "claim_boundary": "deterministic repair regression; not a model-generation result",
        "rows": rows,
        "all_repairs_pass": all(r["repair_passes"] for r in rows),
    }
    report["report_digest"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    _atomic_json(Path("experiments/E25-seeded-repair.json"), report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
