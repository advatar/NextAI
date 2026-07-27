"""E82: is the recursive effect present when improvers are judged by expectation?

E81 found no recursive advantage: the descendant-as-improver's BEST child scored
13/15 against the ancestor's 14/15, p=1.000. But that comparison used
best-of-k selection, and the children's distributions were not close:

    ancestor as improver     children 8, 0, 2, 0 of 8   mean 2.50  sd 3.28
    descendant as improver   children 6, 6, 6, 6 of 8   mean 6.00  sd 0.00

Taking a maximum rewards VARIANCE. An erratic improver that mostly fails but
occasionally excels beats a reliable one whose children are uniformly good, even
though the reliable one is better in expectation. E81 therefore measured which
improver produces the best single child, which is not what POC_PLAN asks: its
Phase 3 criterion is "descendant gain-per-cost", an expectation.

This measures the expectation directly. Every child of every improver is scored
on held-out instances -- no selection step at all -- and the improvers are
compared on the MEAN held-out quality of the children they produce. Removing
selection also removes the selection-noise confound that made E80's development
step necessary to control.

If the descendant wins on the mean, the E81 null was an artifact of the
selection rule rather than an absence of effect, and the recursive question has
a different answer depending on which statistic the governor optimises. That
distinction matters more than either result on its own.
"""

from __future__ import annotations

import hashlib
import json
import statistics
import time
from pathlib import Path

from compare_selection import _atomic_json
from recursive_lab.model_proposer import LocalOpenAICompatibleClient
from recursive_lab.strategy_proposer import MINIMAL
from run_e80_strategy_evolution import DevEnv, HeldoutEnv, score_strategy
from run_e81_recursive_effect import propose_children

CHILDREN = 5
HELDOUT_SAMPLES = 8


def run_arm(client, held, label, improver_text):
    children = propose_children(client, improver_text, CHILDREN)
    print(f"[{label}] proposed {len(children)} children", flush=True)
    rows = {}
    for child in children:
        row = score_strategy(client, held, child, HELDOUT_SAMPLES)
        rows[child.name] = {**row, "text": child.preamble[:200]}
        print(f"  [{label}] held-out {child.name}: "
              f"{row['solved']}/{HELDOUT_SAMPLES} ({row['rate']:.0%})", flush=True)
    rates = [r["rate"] for r in rows.values()]
    return {
        "label": label,
        "children": rows,
        "mean_heldout_rate": statistics.fmean(rates) if rates else None,
        "sd_heldout_rate": statistics.pstdev(rates) if len(rates) > 1 else 0.0,
        "max_heldout_rate": max(rates) if rates else None,
    }


def main() -> None:
    client = LocalOpenAICompatibleClient(timeout=600.0)
    held = HeldoutEnv()
    _ = DevEnv  # no development split: there is no selection step here
    started = time.perf_counter()

    e80 = json.loads(Path("experiments/E80-strategy-evolution.json").read_text())
    arm_a = run_arm(client, held, "ancestor_as_improver", MINIMAL.preamble)
    arm_b = run_arm(client, held, "descendant_as_improver", e80["promoted_text"])

    mean_delta = (arm_b["mean_heldout_rate"] - arm_a["mean_heldout_rate"]
                  if arm_a["mean_heldout_rate"] is not None
                  and arm_b["mean_heldout_rate"] is not None else None)
    max_delta = (arm_b["max_heldout_rate"] - arm_a["max_heldout_rate"]
                 if arm_a["max_heldout_rate"] is not None
                 and arm_b["max_heldout_rate"] is not None else None)

    report = {
        "schema_version": 1, "experiment_id": "E82-improver-expectation",
        "question": ("Judged by the MEAN held-out quality of the children it "
                     "produces, is the descendant a better improver than its "
                     "ancestor?"),
        "claim_boundary": ("One task family, one generation, five children per "
                           "arm, eight held-out samples per child. Far short of "
                           "POC_PLAN's three generations and five independent "
                           "lineages with sealed transfer."),
        "makes_capability_claim": True,
        "method": ("Every child is scored on held-out instances with no "
                   "selection step, so improvers are compared in expectation "
                   "rather than by their best single child."),
        "arm_ancestor_as_improver": arm_a,
        "arm_descendant_as_improver": arm_b,
        "mean_delta": mean_delta,
        "max_delta": max_delta,
        "verdict_by_mean": ("descendant is the better improver" if (mean_delta or 0) > 0
                            else "no advantage by mean" if mean_delta == 0
                            else "descendant worse by mean" if mean_delta is not None
                            else "indeterminate"),
        "verdict_by_max": ("descendant better by max" if (max_delta or 0) > 0
                           else "no advantage by max" if max_delta == 0
                           else "descendant worse by max" if max_delta is not None
                           else "indeterminate"),
        "wall_seconds": time.perf_counter() - started,
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(Path("experiments/E82-improver-expectation.json"), report)

    print(f"\nMEAN held-out child quality:")
    print(f"  ancestor-as-improver   {arm_a['mean_heldout_rate']:.1%} "
          f"(sd {arm_a['sd_heldout_rate']:.2f})")
    print(f"  descendant-as-improver {arm_b['mean_heldout_rate']:.1%} "
          f"(sd {arm_b['sd_heldout_rate']:.2f})")
    print(f"  mean delta {mean_delta:+.1%} -> {report['verdict_by_mean']}")
    print(f"  max  delta {max_delta:+.1%} -> {report['verdict_by_max']}")


if __name__ == "__main__":
    main()
