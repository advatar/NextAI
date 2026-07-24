"""E20: archive admission gate requiring normal plus adversarial correctness."""

import hashlib
import json
from pathlib import Path

from compare_selection import _atomic_json


def main():
    d = json.loads(Path("experiments/E17-gemma-multitask.json").read_text())
    adv = json.loads(Path("experiments/E19-adversarial-holdout.json").read_text())
    rows = []
    for r, a in zip(d["rows"], adv["rows"]):
        rows.append(
            {
                "task": r["task"],
                "index": r["index"],
                "normal_pass": r["score"] == 1.0,
                "adversarial_pass": a["passed"] == a["total"],
                "admitted": r["score"] == 1.0 and a["passed"] == a["total"],
            }
        )
    summaries = {
        k: {
            "candidates": sum(x["task"] == k for x in rows),
            "admitted": sum(x["task"] == k and x["admitted"] for x in rows),
            "admission_rate": sum(x["task"] == k and x["admitted"] for x in rows)
            / sum(x["task"] == k for x in rows),
        }
        for k in ("increment", "square", "clamp")
    }
    report = {
        "schema_version": 1,
        "experiment_id": "E20-repair-gate",
        "claim_boundary": "admission-gate analysis over existing proposals; no new model generations",
        "summaries": summaries,
        "rows": rows,
    }
    report["report_digest"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    _atomic_json(Path("experiments/E20-repair-gate.json"), report)
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
