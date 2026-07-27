"""E84: the powered, pre-registered test of the recursive effect.

See ``preregister_e84.py``; this reloads the frozen plan, recomputes its digest
and refuses to run on drift. The primary analysis, statistic and threshold were
fixed before any data was collected.
"""

from __future__ import annotations

import hashlib
import json
import statistics
import time
from math import comb
from pathlib import Path

from compare_selection import _atomic_json
from compare_e60_corrected_admission import load_preregistration
from recursive_lab.model_proposer import LocalOpenAICompatibleClient
from recursive_lab.strategy_proposer import MINIMAL
from run_e80_strategy_evolution import HeldoutEnv, score_strategy
from run_e83_diverse_improver import propose_distinct_children

CHILDREN = 16
SAMPLES = 12
MAX_ATTEMPTS = 48


def fisher_two_sided(a: int, b: int, c: int, d: int) -> float:
    n = a + b + c + d
    obs = comb(a + b, a) * comb(c + d, c) / comb(n, a + c)
    total = 0.0
    for x in range(0, min(a + b, a + c) + 1):
        y = a + c - x
        if not 0 <= y <= c + d:
            continue
        pr = comb(a + b, x) * comb(c + d, y) / comb(n, a + c)
        if pr <= obs + 1e-12:
            total += pr
    return min(1.0, total)


def run_arm(client, held, label, improver_text):
    children, attempts = propose_distinct_children(
        client, improver_text, CHILDREN, MAX_ATTEMPTS
    )
    print(f"[{label}] {len(children)} distinct from {attempts} attempts", flush=True)
    rows, solved, total = {}, 0, 0
    for child in children:
        row = score_strategy(client, held, child, SAMPLES)
        rows[child.name] = {**row, "text": child.preamble[:160]}
        solved += row["solved"]
        total += SAMPLES
        print(f"  [{label}] {child.name}: {row['solved']}/{SAMPLES}", flush=True)
    rates = [r["rate"] for r in rows.values()]
    return {
        "label": label, "children": rows,
        "distinct_children": len(children), "proposal_attempts": attempts,
        "pooled_solved": solved, "pooled_calls": total,
        "pooled_rate": solved / total if total else None,
        "mean_child_rate": statistics.fmean(rates) if rates else None,
        "sd_child_rate": statistics.pstdev(rates) if len(rates) > 1 else 0.0,
    }


def main() -> None:
    plan = load_preregistration(Path("experiments/E84-preregistration.json"))
    client = LocalOpenAICompatibleClient(timeout=600.0)
    held = HeldoutEnv()
    started = time.perf_counter()
    e80 = json.loads(Path("experiments/E80-strategy-evolution.json").read_text())

    arm_a = run_arm(client, held, "ancestor_as_improver", MINIMAL.preamble)
    arm_b = run_arm(client, held, "descendant_as_improver", e80["promoted_text"])

    a, b = arm_a["pooled_solved"], arm_a["pooled_calls"] - arm_a["pooled_solved"]
    c, d = arm_b["pooled_solved"], arm_b["pooled_calls"] - arm_b["pooled_solved"]
    p = fisher_two_sided(a, b, c, d)
    delta = arm_b["pooled_rate"] - arm_a["pooled_rate"]
    observed = bool(delta > 0 and p < 0.05)

    report = {
        "schema_version": 1, "experiment_id": "E84-powered-recursive-effect",
        "preregistration_digest": plan["preregistration_digest"],
        "question": plan["question"],
        "claim_boundary": plan["claim_boundary"],
        "multiplicity_disclosure": plan["multiplicity_disclosure"],
        "power_calculation": plan["power_calculation"],
        "decision_rule": plan["decision_rule"],
        "makes_capability_claim": True,
        "arm_ancestor_as_improver": arm_a,
        "arm_descendant_as_improver": arm_b,
        "pooled_delta": delta,
        "fisher_exact_two_sided": p,
        "recursive_effect_observed": observed,
        "predictions": [
            {"id": "H1", "supported": delta > 0,
             "evidence": f"ancestor {a}/{a+b}, descendant {c}/{c+d}, delta {delta:+.4f}"},
            {"id": "H2", "supported": p < 0.05, "evidence": f"p={p:.4f}"},
            {"id": "H3",
             "supported": arm_a["distinct_children"] == CHILDREN
             and arm_b["distinct_children"] == CHILDREN,
             "evidence": f"ancestor {arm_a['distinct_children']}/{CHILDREN} in "
                         f"{arm_a['proposal_attempts']} attempts; descendant "
                         f"{arm_b['distinct_children']}/{CHILDREN} in "
                         f"{arm_b['proposal_attempts']}"},
        ],
        "wall_seconds": time.perf_counter() - started,
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(Path("experiments/E84-powered-recursive-effect.json"), report)

    print(f"\nancestor   {a}/{a+b} = {arm_a['pooled_rate']:.1%}")
    print(f"descendant {c}/{c+d} = {arm_b['pooled_rate']:.1%}")
    print(f"delta {delta:+.1%}   Fisher exact two-sided p={p:.4f}")
    print(f"RECURSIVE EFFECT OBSERVED: {observed}")
    for item in report["predictions"]:
        print(f"  {item['id']}: {'supported' if item['supported'] else 'NOT supported'} — {item['evidence']}")


if __name__ == "__main__":
    main()
