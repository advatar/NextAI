"""E21: explicit failure-aware repair baseline (control for model-guided repair)."""

import hashlib
import json
from pathlib import Path

from compare_selection import _atomic_json

REPAIRS = {
    "increment": "def solve(n):\n    return n + 1\n",
    "square": "def solve(n):\n    return n ** 2\n",
    "clamp": "def solve(n):\n    if n is None: return None\n    if isinstance(n, str): n = float(n)\n    return max(0, min(10, n))\n",
}
NORMAL = {
    "increment": lambda f: all(f(n) == n + 1 for n in (-3, 0, 4, 19)),
    "square": lambda f: all(f(n) == n * n for n in (-4, -1, 0, 3, 8)),
    "clamp": lambda f: all(f(n) == max(0, min(10, n)) for n in (-5, 0, 3, 10, 99)),
}
ADVERSARIAL = {
    "increment": lambda f: all(
        f(n) == e for n, e in [(-1.5, 0.5), (True, 2), (0.0, 1.0)]
    ),
    "square": lambda f: all(
        f(n) == e for n, e in [(-1.5, 2.25), (True, 1), (0.0, 0.0)]
    ),
    "clamp": lambda f: all(
        f(n) == e for n, e in [(-1.5, 0), (10.5, 10), (None, None), ("3", 3)]
    ),
}


def main():
    rows = []
    for task, src in REPAIRS.items():
        ns = {}
        exec(src, ns)
        rows.append(
            {
                "task": task,
                "normal_pass": NORMAL[task](ns["solve"]),
                "adversarial_pass": ADVERSARIAL[task](ns["solve"]),
                "candidate": src,
            }
        )
    report = {
        "schema_version": 1,
        "experiment_id": "E21-repair-baseline",
        "claim_boundary": "explicit repair control; not a model-generated repair",
        "rows": rows,
        "all_normal": all(r["normal_pass"] for r in rows),
        "all_adversarial": all(r["adversarial_pass"] for r in rows),
    }
    report["report_digest"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    _atomic_json(Path("experiments/E21-repair-baseline.json"), report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
