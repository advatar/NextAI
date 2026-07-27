"""E80: can a proposed strategy beat its ancestor on held-out instances?

E79 measured a capability difference between three HAND-WRITTEN strategies. That
is discrimination, not improvement: nothing in the system produced a strategy.
This is the first attempt at the project's Phase 2 -- bounded scaffold
improvement -- where the mutable artifact is proposed by the model, selected on
measured capability, and then tested on instances it was never selected against.

Protocol, and the parts that matter are the controls:

* **Ancestor**: ``minimal``, the best hand-written strategy from E79 (60%).
* **Proposal**: the model writes candidate strategies -- instructions for a
  solver -- given only the ancestor's text and a coarse note that it scored
  moderately. It never sees the tasks, the cases, or the oracle.
* **Development selection**: each candidate is scored on task seeds 1-20 and the
  best is promoted.
* **Held-out test**: the promoted strategy and the ancestor are then compared on
  seeds 101-120, which no strategy was selected against, under an IDENTICAL
  number of solver calls.

The held-out split is what separates improvement from selection noise. With four
candidates scored on the same development set, the best will look good there by
construction; only the held-out comparison can show whether anything real was
gained.

A negative result is expected to be common and is reported as such: with the
ancestor already the simplest strategy and E79 showing elaborateness hurts, a
proposed strategy may well be worse.
"""

from __future__ import annotations

import hashlib
import json
import statistics
import time
from pathlib import Path

from compare_selection import _atomic_json
from environments.budgeted_tasks import PartitionFeasibleEnv
from recursive_lab.model_proposer import (
    LocalOpenAICompatibleClient,
    ModelProgramProposer,
)
from recursive_lab.strategy_proposer import MINIMAL, SUBSET_RULES, Strategy
from recursive_lab.widened_validator import validate_widened

BUDGET = 20_000
DEV_SEEDS = tuple(range(1, 21))
HELDOUT_SEEDS = tuple(range(101, 121))


class DevEnv(PartitionFeasibleEnv):
    name = "partition_feasible_dev"
    iteration_budget = BUDGET

    @property
    def hidden_cases(self):
        return DEV_SEEDS


class HeldoutEnv(PartitionFeasibleEnv):
    name = "partition_feasible_heldout"
    iteration_budget = BUDGET

    @property
    def hidden_cases(self):
        return HELDOUT_SEEDS


STRATEGY_BRIEF = (
    "You are writing the SYSTEM INSTRUCTION that another model will follow when "
    "it writes Python functions to solve algorithmic problems under a strict "
    "limit on total loop iterations. Write instructions that help it choose an "
    "efficient algorithm. Reply with the instruction text only: no preamble, no "
    "explanation, no code, and no more than 120 words."
)


def propose_strategies(client, count, ancestor_text):
    """Ask the model for candidate instructions. It never sees tasks or cases."""
    out = []
    for index in range(count):
        user = json.dumps(
            {
                "current_instruction": ancestor_text,
                "note": "the current instruction solves a moderate share of problems",
                "attempt": index,
            },
            sort_keys=True,
            indent=2,
        )
        text, _, _ = client.complete(
            model="default_model",
            system=STRATEGY_BRIEF,
            user=user,
            temperature=1.2,
            max_tokens=300,
        )
        text = text.strip().strip("`").strip()
        if 20 <= len(text) <= 2000:
            out.append(Strategy(name=f"proposed_{index}", preamble=text))
    return out


def score_strategy(client, env, strategy, samples):
    system = strategy.system_instruction().replace(SUBSET_RULES, "").strip()
    proposer = ModelProgramProposer(
        client, model="default_model", temperature=1.0, max_tokens=1400,
        system_override=system,
    )
    solved = valid = 0
    for i in range(samples):
        result = proposer.propose(
            env.task_prompt,
            env.starting_solution,
            f"passes {env.starting_passed} of {env.total_cases} hidden tests; attempt {i}",
        )
        if result.candidate and validate_widened(result.candidate)[1] is None:
            valid += 1
            if env.score(result.candidate).reward >= 1.0:
                solved += 1
    return {"solved": solved, "valid": valid, "samples": samples,
            "rate": solved / samples}


def main() -> None:
    client = LocalOpenAICompatibleClient(timeout=600.0)
    dev, held = DevEnv(), HeldoutEnv()
    started = time.perf_counter()

    ancestor = MINIMAL
    candidates = propose_strategies(client, 4, ancestor.preamble)
    print(f"proposed {len(candidates)} strategies", flush=True)

    dev_rows = {}
    for strategy in candidates:
        row = score_strategy(client, dev, strategy, 8)
        dev_rows[strategy.name] = {**row, "text": strategy.preamble[:400]}
        print(f"  dev {strategy.name}: {row['solved']}/{row['samples']} "
              f"({row['rate']:.0%}) valid {row['valid']}", flush=True)

    if not dev_rows:
        print("no valid strategy proposals; nothing to promote")
        return
    promoted_name = max(dev_rows, key=lambda k: dev_rows[k]["rate"])
    promoted = next(s for s in candidates if s.name == promoted_name)
    print(f"promoted {promoted_name} at {dev_rows[promoted_name]['rate']:.0%} dev", flush=True)

    held_desc = score_strategy(client, held, promoted, 15)
    held_anc = score_strategy(client, held, ancestor, 15)
    print(f"  heldout descendant {held_desc['solved']}/15 ({held_desc['rate']:.0%})", flush=True)
    print(f"  heldout ancestor   {held_anc['solved']}/15 ({held_anc['rate']:.0%})", flush=True)

    delta = held_desc["rate"] - held_anc["rate"]
    report = {
        "schema_version": 1,
        "experiment_id": "E80-strategy-evolution",
        "question": ("Does a model-proposed strategy, selected on development "
                     "instances, beat its ancestor on held-out instances under "
                     "matched budget?"),
        "claim_boundary": ("One lineage, one generation, one task family. A "
                           "positive result would be bounded scaffold "
                           "improvement (Phase 2), NOT a recursive effect, "
                           "which requires a descendant improver producing "
                           "better further descendants."),
        "makes_capability_claim": True,
        "ancestor": ancestor.to_dict(),
        "development_seeds": list(DEV_SEEDS),
        "heldout_seeds": list(HELDOUT_SEEDS),
        "development_results": dev_rows,
        "promoted": promoted_name,
        "promoted_text": promoted.preamble,
        "heldout_descendant": held_desc,
        "heldout_ancestor": held_anc,
        "heldout_delta": delta,
        "verdict": ("descendant beats ancestor" if delta > 0
                    else "no improvement" if delta == 0
                    else "descendant worse than ancestor"),
        "wall_seconds": time.perf_counter() - started,
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(Path("experiments/E80-strategy-evolution.json"), report)
    print(f"\nheld-out delta {delta:+.0%} -> {report['verdict']}")
    print(f"wall {report['wall_seconds']:.0f}s")


if __name__ == "__main__":
    main()
