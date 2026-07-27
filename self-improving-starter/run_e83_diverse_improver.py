"""E83: does the recursive effect appear once offspring diversity is enforced?

E81 and E82 both found no recursive advantage, and E82 located the mechanism:
the descendant improver produced FIVE IDENTICAL children -- one unique text,
pairwise similarity 1.00 -- despite temperature 1.2 and a per-call attempt
index. The ancestor produced three unique of five at similarity 0.72.

That is the E58 pathology one level up. ``candidate_diversity`` was built to void
a run where many model calls yield one program; nothing was watching the same
failure in strategy offspring. An improver whose children are identical cannot
explore, so it has no standout child to select and no advantage in expectation
either -- which is exactly what E81 and E82 measured.

This removes the confound by construction rather than by hoping. Children are
resampled until the required number of DISTINCT texts is obtained, at raised
temperature, with a cap on attempts so a collapsed improver cannot loop forever.
Every child is then scored on held-out instances with no selection step, so
improvers are compared in expectation as in E82.

Three outcomes, all informative:

* the descendant now wins -- the earlier null was caused by diversity collapse,
  and a recursive effect exists once exploration is preserved;
* the descendant still does not win -- the null is robust and diversity was not
  the binding constraint;
* the descendant cannot produce distinct children at all -- the collapse is a
  property of the strategy itself, which is a finding about what makes a bad
  improver.
"""

from __future__ import annotations

import hashlib
import json
import statistics
import time
from pathlib import Path

from compare_selection import _atomic_json
from recursive_lab.model_proposer import LocalOpenAICompatibleClient
from recursive_lab.strategy_proposer import MINIMAL, Strategy
from run_e80_strategy_evolution import HeldoutEnv, STRATEGY_BRIEF, score_strategy

REQUIRED_CHILDREN = 4
MAX_ATTEMPTS = 12
HELDOUT_SAMPLES = 8
TEMPERATURE = 1.5


def propose_distinct_children(client, improver_text, required, max_attempts):
    """Resample until `required` DISTINCT child texts are obtained."""
    system = f"{improver_text}\n\n{STRATEGY_BRIEF}"
    seen: dict[str, Strategy] = {}
    attempts = 0
    while len(seen) < required and attempts < max_attempts:
        user = json.dumps(
            {"note": "write an improved instruction", "attempt": attempts,
             "avoid_repeating": sorted(seen)[:3]},
            sort_keys=True, indent=2,
        )
        text, _, _ = client.complete(
            model="default_model", system=system, user=user,
            temperature=TEMPERATURE, max_tokens=300,
        )
        attempts += 1
        text = text.strip().strip("`").strip()
        if not (20 <= len(text) <= 2000):
            continue
        digest = hashlib.sha256(text.encode()).hexdigest()[:12]
        if digest in seen:
            continue
        seen[digest] = Strategy(name=f"child_{len(seen)}", preamble=text)
    return list(seen.values()), attempts


def run_arm(client, held, label, improver_text):
    children, attempts = propose_distinct_children(
        client, improver_text, REQUIRED_CHILDREN, MAX_ATTEMPTS
    )
    print(f"[{label}] {len(children)} distinct children from {attempts} attempts",
          flush=True)
    rows = {}
    for child in children:
        row = score_strategy(client, held, child, HELDOUT_SAMPLES)
        rows[child.name] = {**row, "text": child.preamble[:200]}
        print(f"  [{label}] {child.name}: {row['solved']}/{HELDOUT_SAMPLES} "
              f"({row['rate']:.0%})", flush=True)
    rates = [r["rate"] for r in rows.values()]
    return {
        "label": label, "children": rows,
        "distinct_children": len(children), "proposal_attempts": attempts,
        "mean_heldout_rate": statistics.fmean(rates) if rates else None,
        "sd_heldout_rate": statistics.pstdev(rates) if len(rates) > 1 else 0.0,
        "max_heldout_rate": max(rates) if rates else None,
    }


def main() -> None:
    client = LocalOpenAICompatibleClient(timeout=600.0)
    held = HeldoutEnv()
    started = time.perf_counter()
    e80 = json.loads(Path("experiments/E80-strategy-evolution.json").read_text())

    arm_a = run_arm(client, held, "ancestor_as_improver", MINIMAL.preamble)
    arm_b = run_arm(client, held, "descendant_as_improver", e80["promoted_text"])

    mean_delta = (arm_b["mean_heldout_rate"] - arm_a["mean_heldout_rate"]
                  if arm_a["mean_heldout_rate"] is not None
                  and arm_b["mean_heldout_rate"] is not None else None)

    report = {
        "schema_version": 1, "experiment_id": "E83-diverse-improver",
        "question": ("With offspring diversity enforced by construction, is the "
                     "descendant a better improver than its ancestor?"),
        "claim_boundary": ("One task family, one generation, four children per "
                           "arm, eight held-out samples per child. Far short of "
                           "POC_PLAN's three generations and five lineages."),
        "makes_capability_claim": True,
        "diversity_enforcement": (f"resample until {REQUIRED_CHILDREN} distinct "
                                  f"child texts, temperature {TEMPERATURE}, cap "
                                  f"{MAX_ATTEMPTS} attempts"),
        "motivation": ("E82 measured the descendant producing 1 unique text of "
                       "5 at pairwise similarity 1.00, the E58 collapse one "
                       "level up."),
        "arm_ancestor_as_improver": arm_a,
        "arm_descendant_as_improver": arm_b,
        "mean_delta": mean_delta,
        "verdict": ("descendant is the better improver" if (mean_delta or 0) > 0
                    else "no recursive advantage" if mean_delta == 0
                    else "descendant worse" if mean_delta is not None
                    else "indeterminate"),
        "wall_seconds": time.perf_counter() - started,
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(Path("experiments/E83-diverse-improver.json"), report)
    print(f"\nancestor   mean {arm_a['mean_heldout_rate']} "
          f"({arm_a['distinct_children']} distinct / {arm_a['proposal_attempts']} attempts)")
    print(f"descendant mean {arm_b['mean_heldout_rate']} "
          f"({arm_b['distinct_children']} distinct / {arm_b['proposal_attempts']} attempts)")
    print(f"mean delta {mean_delta} -> {report['verdict']}")


if __name__ == "__main__":
    main()
