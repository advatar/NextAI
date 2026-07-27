"""E81: does a descendant improver produce better further descendants?

This is the project's Phase 3 criterion, and the first time it has been
runnable. E80 showed a model-proposed strategy beating its ancestor on held-out
instances (93% vs 47%, p=0.0142) -- bounded scaffold improvement. That is a
statement about the artifact, not about the improver.

The recursive question is different: used as an IMPROVER, does the descendant
generate better children than its ancestor generates?

  arm A: MINIMAL       proposes strategies -> best child A -> held-out score
  arm B: E80 descendant proposes strategies -> best child B -> held-out score

Both arms get the same number of proposals, the same development set for
selection, and the same number of solver calls at held-out. The only difference
is which strategy sat in the improver seat. If child B beats child A, the
descendant is a better improver than its ancestor -- a recursive effect. If it
does not, the E80 gain was a one-off improvement to the artifact with no
compounding, which is the null this experiment exists to detect.

Children are tested on the SAME held-out instances neither was selected
against, so the comparison is between improvers rather than between selections.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from compare_selection import _atomic_json
from recursive_lab.model_proposer import LocalOpenAICompatibleClient
from recursive_lab.strategy_proposer import MINIMAL, Strategy
from run_e80_strategy_evolution import (
    DevEnv,
    HeldoutEnv,
    STRATEGY_BRIEF,
    score_strategy,
)

CHILDREN = 4
DEV_SAMPLES = 8
HELDOUT_SAMPLES = 15


def propose_children(client, improver_text, count):
    """Generate strategies USING the improver's own text as the system prompt.

    This is what puts the strategy in the improver seat rather than merely
    being the thing improved.
    """
    system = f"{improver_text}\n\n{STRATEGY_BRIEF}"
    children = []
    for index in range(count):
        user = json.dumps(
            {"note": "write an improved instruction", "attempt": index},
            sort_keys=True, indent=2,
        )
        text, _, _ = client.complete(
            model="default_model", system=system, user=user,
            temperature=1.2, max_tokens=300,
        )
        text = text.strip().strip("`").strip()
        if 20 <= len(text) <= 2000:
            children.append(Strategy(name=f"child_{index}", preamble=text))
    return children


def run_arm(client, dev, held, label, improver_text):
    children = propose_children(client, improver_text, CHILDREN)
    print(f"[{label}] proposed {len(children)} children", flush=True)
    if not children:
        return {"label": label, "children": {}, "best": None, "heldout": None}
    rows = {}
    for child in children:
        row = score_strategy(client, dev, child, DEV_SAMPLES)
        rows[child.name] = {**row, "text": child.preamble[:300]}
        print(f"  [{label}] dev {child.name}: {row['solved']}/{row['samples']}", flush=True)
    best_name = max(rows, key=lambda k: rows[k]["rate"])
    best = next(c for c in children if c.name == best_name)
    held_row = score_strategy(client, held, best, HELDOUT_SAMPLES)
    print(f"  [{label}] HELD-OUT best child {held_row['solved']}/{HELDOUT_SAMPLES} "
          f"({held_row['rate']:.0%})", flush=True)
    return {"label": label, "children": rows, "best": best_name,
            "best_text": best.preamble, "heldout": held_row}


def main() -> None:
    client = LocalOpenAICompatibleClient(timeout=600.0)
    dev, held = DevEnv(), HeldoutEnv()
    started = time.perf_counter()

    e80 = json.loads(Path("experiments/E80-strategy-evolution.json").read_text())
    descendant_text = e80["promoted_text"]

    arm_a = run_arm(client, dev, held, "ancestor_as_improver", MINIMAL.preamble)
    arm_b = run_arm(client, dev, held, "descendant_as_improver", descendant_text)

    a_rate = arm_a["heldout"]["rate"] if arm_a["heldout"] else None
    b_rate = arm_b["heldout"]["rate"] if arm_b["heldout"] else None
    delta = (b_rate - a_rate) if (a_rate is not None and b_rate is not None) else None

    report = {
        "schema_version": 1, "experiment_id": "E81-recursive-effect",
        "question": ("Used as an improver, does the E80 descendant generate "
                     "better children than its ancestor generates?"),
        "claim_boundary": ("One task family, one generation of children, "
                           "n=15 per held-out arm. A positive result is a "
                           "single-lineage recursive observation, far short of "
                           "POC_PLAN's bar of three generations and five "
                           "independent lineages with sealed transfer."),
        "makes_capability_claim": True,
        "children_per_arm": CHILDREN,
        "arm_ancestor_as_improver": arm_a,
        "arm_descendant_as_improver": arm_b,
        "heldout_delta": delta,
        "verdict": ("descendant is the better improver" if (delta or 0) > 0
                    else "no recursive advantage" if delta == 0
                    else "descendant is the worse improver" if delta is not None
                    else "indeterminate"),
        "wall_seconds": time.perf_counter() - started,
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(Path("experiments/E81-recursive-effect.json"), report)
    print(f"\nheld-out: ancestor-as-improver {a_rate}, descendant-as-improver {b_rate}")
    print(f"delta {delta} -> {report['verdict']}")


if __name__ == "__main__":
    main()
