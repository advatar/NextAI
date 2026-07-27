# Resume note — E84 in flight

Written mid-run so this can be picked up cleanly. Everything except E84's result
is committed and pushed.

## What is running right now

`run_e84_powered_recursive.py`, launched from `self-improving-starter/`, logging
to `/tmp/e84.log`. It is the pre-registered, powered test of the recursive
effect and it had **not finished** when this note was written.

```sh
cd self-improving-starter
pgrep -fl run_e84_powered            # is it alive?
tail -f /tmp/e84.log                 # watch
# on completion it writes:
#   experiments/E84-powered-recursive-effect.json
```

If the process died, rerun it. The frozen plan makes that safe: the analysis,
statistic and threshold are fixed in `experiments/E84-preregistration.json`
(digest `b1d16cee…`), and the runner refuses to start if that file has drifted.

**Do not read the partial numbers below as a result.** They are recorded only so
a restart can be recognised as a restart.

```
ancestor    [11,8,5,7,4,2,2,11,12,4,6,1,12,12,12,12]  = 121/192  (arm complete)
descendant  [12,12,12,9,12]                            =  57/60   (5 of 16 children)
```

The descendant arm is incomplete, so no comparison is available yet. The
pre-registered decision rule is Fisher exact two-sided on pooled solver calls,
and a recursive effect counts as observed **only** at p < 0.05 with the
descendant ahead.

## The question E84 settles

Phase 3 of `POC_PLAN.md`: does a better *strategy* make a better
*strategy-generator*? Tested four times now, and E84 is the first with the design
fixed in advance and powered from a calculation.

| Experiment | Protocol | Result |
| --- | --- | --- |
| E81 | best-of-k selection | null, 13/15 vs 14/15, p = 1.000 |
| E82 | expectation, no selection | null, 75.0% vs 77.5% |
| E83 | expectation + enforced offspring diversity | +12.5 points, **p = 0.387** |
| E84 | same, powered: 16 children × 12 samples = 192/arm | **in flight** |

E82 found the mechanism behind the first two nulls: the descendant improver
produced **one unique child text in five**, pairwise similarity 1.00 — the E58
collapse one level up, which nothing was watching for. E83 enforced distinct
offspring and the direction flipped as predicted, but n = 32/arm left it inside
noise.

**The multiplicity problem is real and is disclosed in the frozen plan.** E84 is
confirmatory for a hypothesis E83 generated, not independent of it. If E84 is
null, the honest summary of all four tests is that no recursive effect was
demonstrated. That sentence is in the pre-registration so it cannot be
reframed afterwards.

One measurement already in hand from E84: the descendant needed **43 attempts**
to yield 16 distinct children against the ancestor's **18** — a 2.4× higher
repetition rate, quantifying the E82 collapse rather than merely describing it.

## Standing on the goal

Recursive self-improvement is **not proven to work**.

- **Phase 1** — solid, and far stronger than at the start of this work.
- **Phase 2** — demonstrated in E80: a model-proposed strategy beat its ancestor
  14/15 vs 7/15 on held-out instances under matched budget, p = 0.0142, with no
  task-specific leakage in the promoted text. Caveat recorded: the ancestor was a
  deliberately naive baseline.
- **Phase 3** — unproven. Absent in two tests, suggestive in a third that missed
  significance, fourth in flight.

Even a significant E84 is one lineage and one generation, against `POC_PLAN`'s
bar of three generations and five independent lineages with sealed transfer.

## Infrastructure worth knowing about

A local model server is **running** and holds the 12B in memory:

```sh
pgrep -fl mlx_lm.server
pkill -f mlx_lm.server                       # stop it
cd ../Longemma && ./scripts/start_local_model.sh   # 12B, the E80-E84 proposer
```

For the 2B used in E71: add
`LONGEMMA_USE_OPTIQ=1 LONGEMMA_MODEL=../Broom/diskspace-gemma/models/gemma-4-e2b-it-4bit-mlx`.
Plain `mlx_lm` cannot load either — OptiQ is required — and requests need
`chat_template_kwargs.enable_thinking=false` or the reply carries no `content`
field at all.

Key modules added in this line of work:

| Path | Why it exists |
| --- | --- |
| `environments/budgeted_tasks.py` | The only task with capability variance. A deterministic iteration budget separates correct-but-slow from correct-and-efficient, giving the first tunable difficulty dial. |
| `recursive_lab/loop_guard.py` | Bounds iterations so non-termination is not a timeout. Timeouts failed in both directions (E70: 15s → 20h run; E70b: 0.5s → false failures on correct programs). |
| `recursive_lab/widened_validator.py` | Data structures and algorithms permitted while imports, dunder access and dangerous builtins stay banned. |
| `recursive_lab/strategy_proposer.py` | Strategies as the mutable artifact. |
| `recursive_lab/model_proposer.py` | Public/private split enforced by signature — no parameter can carry hidden cases to the model. |
| `recursive_lab/candidate_diversity.py` | Voids a run whose proposer collapsed. **Not yet wired into strategy offspring**, which is exactly where E82 found the collapse. |

## Next steps, in order

1. Read E84's result and report it against the frozen decision rule.
2. Wire `candidate_diversity` into strategy offspring so the E82 collapse voids a
   lineage automatically instead of being caught by hand.
3. If E84 is positive: replicate across independent lineages before any Phase 3
   claim. If null: the four-test summary is no demonstrated recursive effect.
4. `RESUME.md` and `HANDOFF.md` overlap; fold this into `HANDOFF.md` once E84 has
   landed.

## Traps that cost the most time

- Never detect non-termination with a timeout — bound iterations.
- Choose limits from a cost model. A 1,000,000-iteration guard was as fatal as a
  15-second timeout, in a different currency.
- Keep a null control in every run. `null_only` caught E70b's contamination;
  without it a corrupted +0.3333 would have been reported as a finding.
- Probes get evaded. E63 and E64 both admitted a task on a null variant the
  environment recognised as identical by AST.
- A harness bug impersonates task difficulty convincingly. E77 scored −0.111
  everywhere and looked impossible; the prompt had a stale generator formula
  while the oracle had the new one.
- Single-run verdicts are not measurements. E68 replicated E66/E67's admissions
  and found no task solid.
