# Handoff — E59 to E71

Written for whoever picks this up next. Repo state, what changed, what is
running, and the traps that cost the most time.

## Repository state

- `NExtAI` on `main`, clean, `0` ahead / `0` behind `origin/main`.
- `LandingPage` submodule on `main`, clean, synced. Pointer recorded in NExtAI.
- No other local or remote branches.
- 457 Python tests pass. Every committed `report_digest` reproduces.
- Nothing in the pre-existing evidence chain (E1–E58) was modified. All the work
  below is additive.

## Something is running

**A local model server was started and is still up.** Codex's previous handoff
said "model server is stopped"; that is no longer true.

```sh
# what is running
pgrep -fl mlx_lm.server

# stop it
pkill -f mlx_lm.server

# start it again (NOT plain mlx_lm — see traps)
cd ../Longemma
LONGEMMA_USE_OPTIQ=1 \
LONGEMMA_MODEL=../Broom/diskspace-gemma/models/gemma-4-e2b-it-4bit-mlx \
  ./scripts/start_local_model.sh
# endpoint: http://127.0.0.1:12345/v1
```

## Where the work stands

The review started from a stall: E51 audited the benchmark, returned
`admitted: false` / "reject and redesign cohort", and the redesign never
happened — E52–E58 went into governance parity instead. E59–E71 fixed the
instrument and then used it.

**The short version:** there is now a working benchmark and a model that solves
it. The benchmark is currently *too easy* to answer the question the project
cares about.

| Phase | Outcome |
| --- | --- |
| E59–E62 | Synthetic benchmark rebuilt with headroom. Worst-family selection shown to be dominated on its own yardstick. |
| E63–E68 | Executable substrate audited. **Ten experiments, no task admissible.** Every defect was a *timing* defect. |
| E69 | Timing abandoned for deterministic graded correctness. First admissible instrument: 4 tasks solid, phantom gain exactly 0. |
| E70 | Governed search with a generic AST mutator. One real held-out improvement (+0.5 on one task of four). |
| E71 | Local Gemma 4 E2B in the proposer slot. **Solves all four tasks, pooled +1.0000 held-out.** |

## Open items, most important first

1. **The void rule is wrong. Fix before it certifies anything.**
   It voids a run when unique candidates fall below a floor. In E71 that flagged
   **10 of 12 governed runs that scored +1.0000**, because the model solved the
   task on proposal 1 and then re-proposed the same correct program. Low
   diversity *after success* is convergence, not the E58 pathology.
   Correct form, already pre-registered for the next run: void only when
   diversity is low **and** no improvement was achieved.

2. **The tasks are too easy to test search.**
   Every E71 governed run made **exactly one promotion**. The four tasks were
   calibrated in E69 against a generic mutator; a language model one-shots them.
   Only `integer_sqrt` distinguished the arms (single-shot `[0.0, 0.0, 1.0]` vs
   governed `[1.0, 1.0, 1.0]`). Harder tasks are needed — multi-bug programs, or
   contracts a single edit cannot satisfy.

3. **Nothing here is recursive or self-improving.** The model does not modify its
   scaffold, weights, or proposer. `POC_PLAN.md` Phase 3 remains untouched.

4. **The timing tasks remain unusable** (`count_primes_v2`, `power_mod`,
   `count_divisors`, `gcd_fixed`, `optimize_function`). E68 found no task solid
   under replication. They are left that way deliberately rather than tuned
   further.

## Traps — each of these cost hours

**Do not use a timeout to detect non-termination.** A mutation proposer emits
non-terminating programs 25–58% of the time. Too long and the run never finishes
(E70 spent 2h11m accumulating 39s of CPU — blocked, not computing). Too short and
*correct* programs fail spuriously (E70b at 0.5s corrupted its own null control).
The two failure modes move in opposite directions with machine load, so no value
works. Use `recursive_lab/loop_guard.py`, which bounds *iterations*.

**Pick limits from a cost model, not intuition.** The loop guard's first draft
used a 1,000,000-iteration limit — 16M iterations per hanging candidate — and had
to be killed after ten minutes. That is the same failure as the 15-second timeout
in a different currency. Largest legitimate workload in the suite is ~350
iterations; the limit is 20,000.

**A null control is worth more than it looks.** `null_only` proposes semantically
identical programs and must score exactly 0.0. It is what caught E70b's
contamination. Without it, a corrupted +0.3333 would have been reported as a
finding. Keep it in every run.

**Probes can be evaded.** E63 and E64 both admitted `optimize_function` on a
null variant that was "starting solution + appended comment". That environment
compares programs by `ast.dump`, so the comment was invisible and it correctly
returned exact zeros for what it saw as the same program — which both audits read
as a perfect noise profile. Use `semantic_noop_variant`, which renames locals and
is AST-distinct.

**Single-run verdicts are not measurements.** E66 and E67 reported admission from
one run each; E68 replicated and found *no* task solid, with a single round able
to invert the ranking between the best and worst tasks in the suite. Replicate
admission verdicts, not just effects.

**This model returns one identical program per call at default settings.**
Measured 1/5 unique at temperature 1.0, and prompt variation alone does not help.
Temperature 1.3 **plus** a per-call prompt nonce gives 5/10 unique at 10/10
validator-clean. Both levers are required. This is the E58 defect, still live.

**Log progress.** Three runs were opaque because the runner printed nothing until
completion, making a long run indistinguishable from a hung one.

**The machine is not quiet.** Xcode, WindowServer and an unrelated
`evolve_market_strategy.py` were consuming most of the CPU during this work. It
inflates every subprocess and it is the likeliest explanation for E68's
non-stationary timing noise. Anything wall-clock should be re-checked on an idle
machine.

## New modules

| Path | Purpose |
| --- | --- |
| `recursive_lab/scaled_landscape.py` | Synthetic families at arbitrary grid size; reduces exactly to the historical 5×5 |
| `recursive_lab/admission.py` | E51's audit as a pre-registration gate, judged from the random baseline only |
| `recursive_lab/candidate_diversity.py` | Collapsed proposer streams void a run (E58) |
| `recursive_lab/reward_probes.py` | Non-evadable null variants, monotonicity probe, best-of-k phantom gain |
| `recursive_lab/paired_timing.py` | Drift-cancelling paired measurement (superseded in practice by dropping timing) |
| `recursive_lab/loop_guard.py` | Bounds loop iterations so non-termination is not a timeout |
| `recursive_lab/program_mutation.py` | Generic AST mutation proposer, encodes no task fix |
| `recursive_lab/model_proposer.py` | Live-model proposer; public/private split enforced by signature |
| `environments/graded_correctness.py` | Deterministic reward: share of hidden cases fixed |
| `environments/correctness_tasks.py` | The four admissible tasks |
| `verify_capsulang_evidence.py` | Governance scenarios cross-checked against experiment JSON |

## Method notes

Every experiment from E60 on is **pre-registered**: criteria, instrument,
analysis plan and falsifiable predictions frozen and content-hashed before the
run, with the runner refusing to proceed on digest drift. Amendments are separate
documents recording why, and each states whether results had been seen.

Two failed predictions are recorded rather than smoothed over, and both are
graded defects rather than findings: E64's H5 and E71's H5 both used a check that
disagreed with the statement they were meant to test. Worth reading before
writing a new grader.

Null and inconclusive results are retained as measured. E61 overturned E60's
`rugged` regression as a false positive; E68 overturned E66/E67's admissions.
Those reversals are in `REVIEW.md` with the corrections attached to the original
claims.
