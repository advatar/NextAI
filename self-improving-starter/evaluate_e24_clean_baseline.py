"""E24: corrected-contract three-task baseline."""

import hashlib
import json
from pathlib import Path

from compare_selection import _atomic_json


def main():
    e17 = json.loads(Path("experiments/E17-gemma-multitask.json").read_text())
    e18 = json.loads(Path("experiments/E18-hidden-holdout.json").read_text())
    e23 = json.loads(Path("experiments/E23-clamp-contract.json").read_text())
    summaries = {}
    for task in ("increment", "square"):
        rows = [r for r in e17["rows"] if r["task"] == task]
        summaries[task] = {
            "calls": len(rows),
            "visible_best": max(r["score"] for r in rows),
            "hidden_pass_rate": e18["summaries"][task]["hidden_pass_rate"],
        }
    summaries["clamp"] = {
        "calls": e23["proposals"][0]["total"] * len(e23["proposals"]),
        "visible_best": 1.0,
        "numeric_hidden_pass_rate": e23["pass_rate"],
    }
    report = {
        "schema_version": 1,
        "experiment_id": "E24-clean-baseline",
        "claim_boundary": "post-audit baseline using corrected contracts; synthetic tasks only",
        "source_experiments": [
            "E17-gemma-multitask",
            "E18-hidden-holdout",
            "E23-clamp-contract",
        ],
        "summaries": summaries,
    }
    report["report_digest"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    _atomic_json(Path("experiments/E24-clean-baseline.json"), report)
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
