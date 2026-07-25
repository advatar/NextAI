# Review — recursive scaffold optimization, E30–E58

Independent review of the experiment series, the stall after E51, and the
instrument fix landed as E59.

## Summary

The engineering is sound and the claim discipline is genuinely good. The
research stalled for a measurable reason: **the benchmark had no measurement
headroom.** Every sophisticated component built between E30 and E50 — surrogate
emitters, confidence-gated routers, quality-diversity archives — was pointed at
an objective that random search already solved.

The project's own audit found this. E51 returned `admitted: false`,
`decision: "reject and redesign cohort"`. The redesign did not happen. E52–E58
pivoted into governance infrastructure instead, and all seven pass their own
adoption gates because they test parity of machinery rather than capability.

## Diagnosis

### The instrument was saturated

The nine synthetic families were defined on a 5×5 score table. The budget was
three exploration samples per column plus one exploitation choice per column, so
each run evaluated 5 × 4 = 20 of 25 cells.

Coverage is `(exploration_per_column + 1) / grid_size` — the column count
cancels, so **only a wider grid buys headroom**; sampling more per column makes
coverage worse. At grid size 5 that is 0.80.

No search policy can demonstrate an advantage over random when random samples
four fifths of the universe. The consequences are visible throughout:

| Evidence | Observation |
| --- | --- |
| `E51-benchmark-admission.json` | `exploration_target_rate: 0.8` against a criterion of ≤ 0.2 |
| `E43-risk-router.json` | paired promoted-minus-random delta `0.0038` |
| `E40-unseen-families.json` | every policy scores `1.0` on every held-out family — a ceiling tie |
| `E45-support-guard.json` | delta `0.0302`, CI `[0.0252, 0.0353]` — a tight interval around a quantity with no headroom |

`E45` also hardcodes `external_domain_regret: 0.0` and injects
`zeros = [0.0] * seeds` for 4 of its 10 domains "by construction"
(`validate_e45_support_guard.py:51-61`). This is honestly labelled in the file,
but it means a governance constraint of `external_domain_regret >= 0` checks a
tautology rather than a measurement.

### The binary metric hid the problem at both ends

`target_hit` saturates at the ceiling on a narrow grid and collapses to the
floor on a wide one. It is uninformative in both directions. Since every family
scores exactly `1.0` at its target, continuous `regret = 1.0 - best_score` is
well defined and retains resolution at any scale. E59 uses regret as the primary
metric and keeps hit rate only as a diagnostic.

### E58 does not support its weight

`E58-gemma-governed-program.json` records 6 model calls whose `model_receipts`
share **one** `candidate_digest` and **one** `response_digest`
(`2f5a0b29…`). The model returned an identical program every time, so there was
no search — a single sample. `valid_candidates: 6`, `promotion_parity: True`
and `adoption_gate.passed: True` are all trivially true at n = 1.

Separately, the evaluator was revised after seeing candidates
(`initial_expression_only_accepts: 0` → `revised_safe_piecewise_accepts: 6`) to
admit exactly the shape the model emitted. `new_authority_granted: false` is a
real mitigation, but this remains post-hoc gate loosening and should not be
scored as a clean result.

### A governance constraint contradicted the evidence

`capsulang/e53_recursive_governor.caps` declares
`(constraint benchmark_admitted == 1)`, and the showcase scenario
`capsulang/scenarios/e45_promote.json` fed it `"benchmark_admitted": true` while
`E51-benchmark-admission.json` records `false`. The governor's demonstration
path asserted a fact the project's own audit refuted.

Runners were also inconsistent about where this value came from:
`run_e55_governed_lineage.py:30` derives it from real gate results, while
`run_e53_capsulang_governor.py:74` hardcodes it.

### Measured against the project's own bar

`POC_PLAN.md` Phase 2 requires "a positive paired hidden-task gain under the
same budget … and positive sealed-OOD transfer". E40's ceiling ties do not meet
it. Phase 3 has never been genuinely attempted with a live model.

## What was changed

Nothing in the existing evidence chain was modified. All 55 `report_digest`
values still reproduce exactly, and no existing runner or experiment JSON was
edited. Everything below is additive.

### `recursive_lab/scaled_landscape.py` — the instrument

Generalizes all nine families to an arbitrary grid size. The historical magic
numbers were all expressions of the grid extent (`/4` → `/(G-1)`, `/32` →
`/(2(G-1)²)`, `/8` → `/(2(G-1))`, `%5` → `%G`, decoy corner `(4-tx, 4-ty)` →
`(G-1-tx, G-1-ty)`).

`tests/test_scaled_landscape.py` asserts **cell-for-cell equality** against the
original implementations in `compare_e37_surrogate_generalization.py`,
`compare_e40_unseen_families.py` and `compare_e42_second_audit.py`, across every
family and every target placement. The new benchmark is therefore a verified
widening of the old one, not a different one. Historical evidence stays valid at
the scale it was collected; it simply has no headroom there.

Two bugs were caught by writing those invariants:

- `spike` and `decoy` used `0.02 * ((x+y) % grid_size)`-style noise floors.
  Bounded at G=5, these reach 5.3 and 25.6 at G=256 — overtaking the target and
  destroying the `optimum = 1.0` invariant that makes regret meaningful. Both now
  hold their range fixed and normalize by extent, still reducing exactly at G=5.
- Exploitation used an O(G) scan over unseen cells. For a linear predictor the
  maximiser is always an endpoint of the unseen range, so `surrogate_choice` is
  O(1); a randomized test asserts it agrees with the naive scan. This is what
  makes wide grids tractable.

### `recursive_lab/admission.py` — pre-registration, not post-mortem

E51's audit rebuilt as a reusable gate that runs **before** a cohort may produce
results. `require_admitted` raises `BenchmarkNotAdmittedError`, so an
uninformative cohort structurally cannot emit an artifact that later reads as
evidence.

The critical semantic: admission is judged from the **random baseline's**
behaviour, never from the candidate policy under test. Admitting a cohort based
on the policy being evaluated would be circular — which is the failure mode
being prevented. A regression test reproduces E51's exact numbers
(rate 0.8, disagreements 0, tasks 5) and asserts rejection.

### `recursive_lab/candidate_diversity.py` — degenerate streams void a run

Makes candidate diversity a first-class enforced metric. A collapsed proposer
stream now yields a **void** run — not a passing one and not a failing one; the
distinction is scientific, since a run that never searched has no result either
way. A regression test loads the real E58 receipts and pins 6 total / 1 unique /
`repeat_ratio 1.0` as void under every constructible requirement.

### `verify_capsulang_evidence.py` — scenario evidence must match reality

Cross-checks each Capsulang scenario's evidence payload against the experiment
JSON it claims to represent. The known contradiction is now surfaced on every
run rather than sitting silent:

```
[assumption] e45_promote.json::benchmark_admitted: scenario asserts
benchmark_admitted=True but experiments/E51-benchmark-admission.json#admitted
gives False
```

`e45_promote.json` is relabelled as an explicitly **hypothetical** fixture, and a
new `e51_real_evidence_quarantine.json` drives the governor with the *real* E51
value to a non-promoted state — so the governor can now be shown to **refuse**
promotion on measured evidence, which is far more valuable than one that only
ever promotes.

## E59 — the result

`compare_e59_scaled_router.py` re-runs E43's exact protocol (same candidate
threshold grid, evolve on training seeds, validate on disjoint held-out seeds)
changing **only** the instrument.

```
grid size 128    search space 16384    512 evaluations/run
coverage 0.031   (legacy 0.800)
```

**Headline: the pooled result is inconclusive, and one family shows a large,
clearly real effect.**

| Family | Paired regret delta | 95% bootstrap CI |
| --- | --- | --- |
| **monotone** | **−0.02372** | **[−0.02635, −0.02116]** |
| checkerboard | −0.01500 | [−0.03375, +0.00375] |
| sinusoidal | −0.00333 | [−0.01333, +0.00666] |
| rugged | −0.00171 | [−0.01204, +0.00859] |
| spike | −0.00002 | [−0.02402, +0.02398] |
| curved | +0.00006 | [−0.00002, +0.00015] |
| plateau | +0.00000 | [0.00000, 0.00000] |
| ridge | +0.00141 | [−0.00696, +0.00980] |
| decoy | +0.00159 | [−0.02255, +0.02578] |

Pooled: `−0.00453`, CI `[−0.00916, +0.00028]` → **inconclusive, interval spans
zero.**

Negative means less regret, i.e. better. The read: the confidence-gated router
delivers a real and comparatively large advantage on `monotone` — the one family
whose surface is genuinely linear and separable, where a linear surrogate should
help — and does nothing distinguishable anywhere else. Pooling across eight
null families dilutes the one real effect into an inconclusive aggregate.

This is a more useful result than E43's `0.0038`-on-everything, not because it is
positive but because it **discriminates**. The instrument can now tell where the
router works from where it does not.

Per `POC_PLAN.md` ("A null result is retained and reported rather than optimized
away"), the inconclusive pooled verdict is recorded as-is. It was not tuned.

### A defect in the new admission gate, found by running it

`plateau` was admitted (8 disagreements over 120 tasks) yet its measured effect
is exactly `0.00000` with CI `[0, 0]` — a family where no effect is possible.
`minimum_policy_disagreements` is an **absolute count**, which is far too lenient
once a cohort has 120 tasks; it should be a **rate**.

This is deliberately *not* patched here. Changing an admission criterion after
seeing results and re-running is precisely the post-hoc adjustment this review
criticizes. It is recorded as a pre-registered change for the next run.

## Recommended next steps

1. **Change `minimum_policy_disagreements` to a rate** and pre-register it before
   the next cohort. Re-run E59 under the corrected gate.
2. **Report per-family, not pooled, as the primary claim.** Pooling across
   families with no possible effect is a dilution artifact.
3. **Move to the executable substrate.** `task_harness.py` and
   `container_runner.py` already exist and cannot saturate. The synthetic grids
   were scaffolding for the plumbing, and the plumbing is finished and tested.
   `GEM_ASSESSMENT.md` step 1 identified this and it remains the highest-value
   move.
4. **Restore real search in the live loop.** Wire
   `recursive_lab.candidate_diversity` into the live runners so E58's collapse
   cannot recur silently, and vary temperature and prompt across the candidate
   stream.
5. **Split the tracks.** Keep Capsulang/MeTTa governance work in its own
   numbering. It is decent engineering, but sharing the E-series makes parity of
   machinery read as capability evidence in the ledger.

## Claim boundary

E59 is a synthetic landscape study of one exploitation rule. It is not evidence
of scaffold self-improvement, and certainly not of a recursive effect. Its value
is that it establishes a benchmark on which such a claim could, for the first
time in this series, actually be tested.

## Validation

- 296 tests pass (186 before this work).
- All 55 `report_digest` values in `experiments/` reproduce exactly; 0
  mismatches. No existing experiment JSON or runner was modified.
- `verify_capsulang_evidence.py` exits 0 with `contradictions=0 assumptions=1`.
