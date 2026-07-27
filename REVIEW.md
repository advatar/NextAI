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

## E60 — the corrected gate, pre-registered

The defect E59 recorded was fixed the honest way. `preregister_e60.py` froze the
criteria, instrument, analysis plan and four falsifiable predictions **before**
the run and content-hashed them.
`compare_e60_corrected_admission.py` reloads that document, recomputes the
digest, and refuses to run if anything drifted — the same fail-closed identity
discipline as `recursive_lab/manifest.py`. Only the admission gate differs from
E59; instrument, seeds, budget and candidate grid are identical, so the two runs
are a controlled comparison of the gate itself.

`minimum_policy_disagreement_rate = 0.2` was chosen to mirror the existing
saturation bound, not tuned against observed rates.

**The count-based gate was indeed vacuous.** Five of nine families were rejected,
all on the rate criterion:

| Rejected family | Disagreement rate |
| --- | --- |
| spike | 0.033 |
| checkerboard | 0.058 |
| plateau | 0.067 |
| ridge | 0.142 |
| decoy | 0.150 |

Every one cleared the old absolute count of 3 while being unable to express an
effect at all.

**Primary result — per family, on the four admitted families:**

| Family | Regret delta | 95% CI | Verdict |
| --- | --- | --- | --- |
| monotone | −0.00732 | [−0.01001, −0.00456] | reduces regret |
| curved | −0.00003 | [−0.00006, −0.00001] | reduces regret |
| rugged | **+0.00836** | **[+0.00167, +0.01533]** | **increases regret** |
| sinusoidal | −0.00333 | [−0.01334, +0.00667] | inconclusive |

Secondary pooled: `−0.00058`, CI `[−0.00382, +0.00269]` — inconclusive, as
pre-registered and as expected when averaging across families.

All four predictions were supported (H1–H4).

### Two things worth reading carefully

**The promoted router appears to harm `rugged`.** Its interval excludes zero on
the wrong side: the policy selected on training data makes held-out performance
*worse* on a family it was trained across. The old instrument could not have
shown this — at 80% coverage every policy tied at the ceiling.

> **Superseded by E61.** This did **not** replicate on fresh seeds. E61 measured
> `−0.00165`, CI `[−0.00843, +0.00503]` — inconclusive, spanning zero, and the
> opposite sign. The E60 result was a false positive, and calling it "the most
> actionable finding in the series" was wrong. See
> [E61](#e61--the-rugged-regression-does-not-replicate) for what actually
> happened and why the pre-registration anticipated it.

**`curved`'s result is statistically significant and practically meaningless.**
The interval excludes zero, but the effect is −0.00003. With low variance and 120
seeds a bootstrap interval can exclude zero for an effect three orders of
magnitude below anything that matters. It is reported as measured, but it should
not be read as the router "working" on curved. A minimum effect size belongs in
the next pre-registration alongside the rate criterion.

Note also that the promoted router changed between runs — E59 selected
`(0.5, 0.0)` and E60 selected `(0.0, 0.03)` — because training now happens over
admitted families only. The monotone effect is correspondingly smaller here
(−0.0073 against E59's −0.0237). Same direction, same sign, different magnitude;
these are different selections, not a replication failure.

## E61 — the rugged regression does not replicate

E61 was designed to explain E60's `rugged` regression with a causal ablation. It
instead found there was nothing to explain.

The plan was frozen first (`preregister_e61.py`, digest `235d865d…`) with five
predictions and a new **minimum effect size** criterion of 0.005 regret units,
closing the gap E60 left open. Seeds 1000–1239 are disjoint from E59 and E60's
0–239.

### The headline: a false positive, caught by replication

| Experiment | Seeds | `rugged` delta | 95% CI |
| --- | --- | --- | --- |
| E60 | 120–239 | +0.00836 | [+0.00167, +0.01533] |
| E61 | 1000–1239 | **−0.00165** | **[−0.00843, +0.00503]** |

The effect vanished, changed sign, and its interval now spans zero. E60's
interval only barely excluded zero, and nine families were examined without
multiplicity correction — which E60's own pre-registration disclosed in advance:

> "any family reaching an interval that excludes zero is reported as a
> single-family result requiring replication, not as a confirmed effect."

That caveat fired exactly as written. The process worked; my summary of it did
not. I called this "the most actionable finding in the series" and it was noise.

**Three of five predictions failed.** H1 (regression replicates), H2
(endpoint_control also harms), and H5 (e41_gate harms less) are all NOT
supported, because all three presupposed a real effect on rugged.

### What the ablation did establish

The two mechanistic predictions — the ones that did not depend on the regression
being real — both held.

| Family | Fit-following component | 95% CI | Reading |
| --- | --- | --- | --- |
| rugged | +0.00014 | [−0.00581, +0.00611] | fit carries no signal (H3 ✓) |
| monotone | −0.00261 | [−0.00445, −0.00074] | fit carries real signal (H4 ✓) |

The component is `e60_promoted` minus `endpoint_control`: two arms that fire on
identical conditions and both always land on a column endpoint, differing only
in whether the fitted line or a coin flip picks which end. On `rugged` a
three-point linear fit is worth exactly nothing, as expected on a hash-derived
surface. On `monotone` it is worth something real. The positive control passes,
so the ablation measures what it claims to.

### An unplanned finding worth acting on

On `monotone`, E41's older gate is **three times better** than E60's promoted
router:

| Arm | monotone delta | 95% CI | Endpoint pick rate |
| --- | --- | --- | --- |
| e41_gate (0.5, 0.01) | **−0.01967** | [−0.02167, −0.01777] | 0.56 |
| e60_promoted (0.0, 0.03) | −0.00625 | [−0.00835, −0.00425] | 0.12 |
| endpoint_control | −0.00364 | [−0.00517, −0.00213] | 0.12 |

The endpoint rates explain it: E60's router demands `variance >= 0.03`, which
`monotone` columns rarely produce, so it declines to exploit 88% of the time.
E41's gate keys on `R^2 >= 0.5`, which monotone satisfies constantly, so it
exploits on 56% of columns and captures the available signal.

**The promotion objective is the problem.** Selecting on *worst-family* regret
across four admitted families picked a router that is mediocre everywhere over
one that is excellent where signal exists. That is a defensible objective, but it
was never compared against alternatives, and E61 shows it costs a factor of three
on the one family with a real effect.

### The effect-size floor earned its place immediately

`endpoint_control` on monotone measured −0.00364 with an interval excluding
zero, and was correctly reported as **negligible** rather than as a result. Under
E60's rules it would have been a fourth "reduces regret" finding.

## E62 — worst-family selection is dominated on its own yardstick

E61 suggested the promotion objective, not the router, was the real problem. E62
tested that directly: three selection objectives, identical training data, and
**two disjoint held-out blocks** so replication is structural rather than a
follow-up experiment. Plan frozen first (`preregister_e62.py`, digest
`a2484275…`); seeds 2000–2119 / 3000–3119 / 4000–4119, disjoint from everything
prior.

The comparison was designed to avoid rigging itself. Scoring three objectives on
macro-mean regret would hand the win to the macro-mean objective by
construction, so **both** yardsticks are reported for every selected router and
the pre-registered question is whether any objective generalises beyond the one
it optimises.

### Selection

| Objective | Selected router |
| --- | --- |
| worst_family | R² ≥ 0.0, var ≥ 0.0 (always exploit) |
| macro_mean | R² ≥ 0.0, var ≥ 0.0 (always exploit) |
| signal_weighted | **R² ≥ 0.5**, var ≥ 0.0 |

Weighting families by their policy-disagreement rate recovered a genuinely
support-aware gate; the other two objectives both collapsed to unconditional
exploitation.

### Held-out scores, both yardsticks, both blocks

| Objective | Block | macro-mean regret | worst-family regret |
| --- | --- | --- | --- |
| signal_weighted | A | **0.17146** | **0.46583** |
| signal_weighted | B | **0.16888** | **0.45922** |
| worst_family | A | 0.17487 | 0.48253 |
| worst_family | B | 0.17220 | 0.47419 |

**The headline: `worst_family` selection loses on the worst-family yardstick.**
It selected the router that minimised worst-family regret *on training data*, and
on held-out seeds `signal_weighted`'s router is better on that exact metric — by
0.0167 in block A and 0.0150 in block B, both comfortably clearing the 0.005
effect floor and agreeing across blocks. That is overfitting, plainly: maximin
selection on this benchmark generalises worse than the thing it was chosen to
beat.

On macro-mean the same ordering holds but the gap is 0.0034 and 0.0033 — *below*
the effect floor, so that half is negligible.

All four testable predictions were supported (H1–H4), including the stability
check: both blocks rank the objectives identically.

### What did not happen

**H5 was not supported.** No effect cleared in one block and failed in the other.
The replication rule caught nothing this time, because the weak per-family
effects were already inconclusive *within* each block. The rule is insurance that
did not need to pay out here — worth stating plainly rather than presenting the
machinery as having proven itself.

`monotone` is the one solidly replicated per-family effect, at −0.0228 (A) and
−0.0222 (B) across all three objectives. Every other family is inconclusive in
both blocks, including `decoy` swinging +0.01417 to −0.01000 — a good picture of
what noise looks like here.

### A limitation to carry forward

The objective-level comparison uses point estimates only. Per-family deltas carry
bootstrap intervals, but the macro and worst-family scores do not, so "0.0167
better in both blocks" has no interval attached. The frozen plan should have
required paired intervals on the objective-level contrast, and did not. The
two-block agreement is real evidence, but it is weaker than an interval would
be. Pre-registered for the next run rather than added post hoc.

## E63 — auditing the executable substrate before building on it

The recommended next move was the executable task substrate, which cannot
saturate the way a 5×5 grid did. The lesson of E51 is to audit an instrument
*before* building on it, so E63 makes **no capability claim under any outcome**.
It asks only whether the suite can measure an improvement.

The tool throughout is a **null variant**: each environment's own starting
solution with a trailing comment appended. Semantically identical by
construction, so every non-zero reward it earns is measurement artefact.

Plan frozen first (`preregister_e63.py`, digest `0ec039c7…`), with the
disclosure that a scouting probe informed the thresholds.

### Results

| Task | Starting reward | Null sd | Best-of-5 null | Verdict |
| --- | --- | --- | --- | --- |
| optimize_function | 0.0000 | 0.0000 | 0.0000 | **admitted** |
| count_primes | 0.0000 | 0.0760 | **0.2539** | rejected |
| sum_digits | **1.0000** | 0.0000 | 1.0000 | rejected |

**`sum_digits` ships already solved.** Its `starting_solution` is a correct
digit-sum implementation and its reward is binary, so it scores 1.0 before any
work is done. Zero headroom — the same failure as the saturated grid, in a new
substrate.

**`count_primes` cannot distinguish work from noise.** Re-scoring semantically
identical programs gives rewards from 0.000 to 0.276. The consequential number is
the best-of-k curve:

| k (no-op proposals) | 1 | 2 | 3 | 5 | 8 |
| --- | --- | --- | --- | --- | --- |
| phantom reward | 0.174 | 0.217 | 0.236 | **0.254** | 0.265 |

A search loop that proposes five candidates and keeps the highest scorer books
**0.254 of reward for changing nothing at all.** Any self-improvement result
measured on this task would be substantially this artefact.

### The deeper defect: a reward scale set by one noisy measurement

`count_primes.py:16` captures `self._baseline_time` from a **single**
measurement at construction, and every candidate is normalised against it. In
this run that measurement came out at 3.92 ms against a null median of 3.22 ms —
21.8% slow — so every no-op variant collected a free +0.174.

The scouting probe showed the same defect with the opposite sign: there the
captured baseline was *fast* (9.17 ms against a ~11 ms typical), so identical
programs scored a mean of **−0.171** before clamping. The reference point is
unstable in magnitude *and direction* between runs of the same code on the same
machine.

That instability is why **H4 was not supported**. The predicted rectification
bias from `max(0.0, …)` was +0.0001, not ≥ 0.05, because in this particular run
the clamp barely bound — the nulls landed positive, so there was almost nothing
to censor. The clamping hazard is real but conditional on which side the noisy
baseline falls; the single-measurement reference is the more fundamental problem
and the one to fix.

### H5 was wrong, and that is good news

I predicted no task would be admitted. `optimize_function` was, and it holds up.
An unplanned follow-up check (recorded here as unplanned, not as a frozen
prediction) confirmed it detects real signal: replacing the O(n) loop with the
closed form `(n−1)n(2n−1)/6` scores a stable **1.0** across five trials, raw
timing 2.1e-07 s against the starting solution's 8.6e-03 s — roughly a 40,000×
speedup, cleanly measured.

So the substrate is not unusable. It contains one sound task, one saturated task,
and one task whose reward is mostly noise.

### A hole in my own admission criteria

The four frozen criteria test for the **absence of noise** and never for the
**presence of signal**. A task whose reward function returned a constant would
pass all four trivially. `optimize_function` genuinely detects improvement, but
E63's criteria are not what established that — a separate unplanned check was. A
minimum-detectable-effect criterion belongs in the next pre-registration, and it
is the exact mirror of the E51 mistake: I checked one direction only.

## E64 — the repairs worked; the audit criteria did not

E63 left four repairs. They were built: `environments/timed_task.py` gives
median-of-calibrated-batches anchors, an **unclamped** reward per `base.py`'s
documented `[<0, ~1+]` contract, and a held-out reference defining the 1.0 point.
`count_primes_v2` is that rebuild; `power_mod` is a new task whose optimum is an
algorithm (binary exponentiation) rather than a closed form. The v1 environments
were left untouched so prior records stay interpretable.

Four of five predictions failed, and the reason is more interesting than the
repairs.

### `count_primes` v1 was admitted this run

The task E63 rejected as the worst in the suite passed every noise criterion
perfectly: null sd `0.0000`, best-of-5 `0.0000`, null mean `0.0000`.

It is the same unrepaired code. In E63 the import-time baseline landed on the
slow side, nulls scored positive, and the task produced a 0.254 phantom gain. In
E64 the baseline landed at 6.178 ms while nulls ran 6.36–7.39 ms, so every
unclamped reward was negative (−0.03 to −0.20) and `max(0.0, …)` floored **all of
them to exactly zero**.

**The clamp manufactured a perfect noise profile.** Zero variance from censoring
is indistinguishable from zero variance from precision. Same code, opposite
verdict across two experiments, decided entirely by which side one noisy
measurement fell.

`optimize_function` is not exempt: line 363 applies a 3% deadband, returning 0.0
for any improvement below `starting_time * 0.03`. Its exact zeros are also
censoring — a principled deadband rather than a bug, but still not evidence of
precision.

### My signal criterion was silently skipped, and my own check missed it

E63's hole was criteria that tested for absence of noise but never presence of
signal. E64 added signal-to-noise = (reference mean − null mean) / null sd, and
H5 existed specifically *"as a check that the criterion is actually being applied
rather than silently skipped."*

Signal-to-noise is undefined exactly when the null sd is zero — which is
precisely the censoring case. Both admitted tasks had undefined ratios, so the
criterion was skipped for both. And the grader read:

```python
all(value is None or value >= threshold for value in ratios.values())
```

`None` counted as passing. **H5 was graded "supported" while performing the exact
silent skip it was written to detect.** The recorded E64 report's
`H5: supported` should be read as **NOT supported**; the rule is corrected in the
runner with a regression test pinning both the buggy and corrected semantics.

### `power_mod` is the best task in the suite and was rejected

| Task | Headroom | Null mean | Null sd | Best-of-5 | Signal/noise | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| optimize_function | — | +0.0000 | 0.0000 | 0.0000 | undefined | admitted |
| count_primes (v1) | — | +0.0000 | 0.0000 | 0.0000 | undefined | admitted |
| count_primes_v2 | 22.2× | −0.2726 | 0.3684 | 0.0944 | 3.5 | rejected |
| **power_mod** | **669×** | +0.0132 | 0.0495 | 0.0727 | **19.9** | rejected |

`power_mod` has a null mean near zero, by far the best signal-to-noise in the
suite, and 669× headroom. It was rejected on a single criterion: best-of-5 =
0.073 against a 0.05 bar. Meanwhile two tasks whose rewards are censored to a
constant were admitted.

**The criteria are ranking censored rewards above honest ones.** That is a defect
in the audit, not in `power_mod`.

`count_primes_v2` genuinely failed (H4, the one supported prediction): 22×
headroom is too small against host jitter, so the repair is necessary but not
sufficient. Headroom magnitude decides usability. But note its null mean of
−0.273 is *honest* — an unclamped reward reporting that these runs really were
slower than the anchor — whereas v1's +0.0000 is a censored fiction.

### The thing that cannot be engineered away

Best-of-k phantom gain is intrinsic to taking a maximum over any noisy reward. No
environment fix drives it to zero; only reducing the spread does. The right
response is not a stricter environment but a **scoring protocol**: evaluate each
candidate as a median of *m* repeated measurements, which shrinks the effective
sd by roughly √m, and require a claimed improvement to exceed the measured
best-of-k null baseline. That belongs in the next pre-registration, applied
prospectively rather than by relaxing the 0.05 bar after seeing that `power_mod`
missed it.

## E65 — with probes that cannot be evaded, nothing is admissible

E63 and E64 both used "the starting solution with a comment appended" as the
semantically-null probe. `optimize_function` compares candidates by `ast.dump`,
so a comment is invisible to it: the variant was recognised as *the same program*
and returned exactly `0.0` every time, by design and correctly. Both audits read
that string of exact zeros as a perfect noise profile and admitted the task.

It was neither precision nor censoring. **The probe was evaded.** The one task
admitted by both prior audits is the one that defeated the instrument.

E65 re-runs with AST-distinct null variants (renamed locals — free at runtime), a
monotonicity probe, and a median-of-*m* protocol measured as a curve.

### Every task fails

| Task | Monotonicity | Null mean (m=9) | Null sd (m=9) | Best-of-5 | Signal/noise | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| optimize_function | responds (−1.17) | **+0.1493** | 0.1422 | **+0.2934** | 6.0 | rejected |
| count_primes (v1) | **+0.0000 — no response** | +0.0000 | 0.0000 | +0.0000 | **undefined** | rejected |
| count_primes_v2 | responds (−1.10) | +0.0035 | 0.1296 | +0.0920 | 7.5 | rejected |
| power_mod | responds (−0.69) | −0.0911 | 0.0851 | −0.0257 | 12.8 | rejected |

**`optimize_function` is the worst-behaved task in the suite**, not the best. Its
null sd is 0.1097 at m=1 against the `0.0000` E64 recorded, a semantically null
rename earns a mean of **+0.17**, and best-of-5 phantom gain is **+0.29** — higher
than the 0.254 that got `count_primes` v1 rejected in E63. Its admission in two
consecutive experiments was entirely a probe artefact.

**`count_primes` v1 is now caught cleanly.** A program doing exactly twice the
work scored `+0.0000`. A reward that cannot tell "twice as slow" from "identical"
is censored, and its signal-to-noise is undefined — which now fails rather than
being silently skipped as it was in E64.

H1, H2 and H3 supported. The repaired base class does fix monotonicity: both
`count_primes_v2` and `power_mod` respond sharply to a genuinely slower program.

### The median-of-*m* protocol does not work, and that is the finding

**H4 failed.** `power_mod`'s null sd went 0.1064 → 0.0851 from m=1 to m=9, a 20%
reduction where √9 predicts about 67%. Averaging bought almost nothing.

That rules out the fix I proposed at the end of E64. The noise is not independent
per measurement — it is **drift**, and a median over m measurements taken close
together cannot cancel a trend common to all of them.

The direct evidence is the starting solutions' own scores. Each *should* score
exactly 0.0 by definition, being the anchor:

| Task | Starting solution reward |
| --- | --- |
| count_primes_v2 | **+0.2339** |
| power_mod | **−0.1902** |

Every environment in the suite, including the repaired ones, captures its anchor
timing once at construction and scores candidates against it minutes later. The
machine drifts — thermal state, cache, competing load — and the whole reward
scale shifts with it. `optimize_function`'s +0.17 null mean and `power_mod`'s
−0.09 are the same defect with opposite sign.

**The fix is not averaging but pairing.** Re-measure the anchor immediately
adjacent to each candidate measurement and compute the reward from the paired
difference, so drift common to both cancels. That is the interleaved-measurement
design used for exactly this reason in benchmarking, and it is the next thing to
build. Note E59–E62 already used paired comparison on the synthetic side; the
executable substrate never adopted it.

### Standing

Four experiments into the executable substrate, **no task can currently measure
an improvement**, and two prior admissions were wrong. That is a worse position
than E63 reported and a more accurate one. Nothing here licenses running a search
loop.

## E66 — pairing fixes it; two tasks are now usable

E65 diagnosed drift and ruled out averaging. E66 tested the alternative:
`recursive_lab/paired_timing.py` measures the anchor and the candidate
**interleaved in one process**, alternating which goes first each round, and
computes the reward from the *ratio* `t_candidate / t_anchor`. Multiplicative
drift scales both timings and cancels.

Only the anchor is co-located with candidate code. The starting solution is
public — it is printed in the task prompt — so nothing leaks. The held-out
reference is calibrated separately against the same anchor, also by paired
measurement, and a test asserts it never appears in the candidate's process.

Both protocols were measured on the same tasks in the same run. Comparing across
experiments would inherit exactly the drift under investigation.

**All five predictions supported.**

| Task | Protocol | Anchor self | Null mean | Null sd | Best-of-5 | Signal/noise | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| optimize_function | unpaired | +0.0000 | −0.1072 | 0.1070 | −0.0473 | 10.3 | rejected |
| optimize_function | **paired** | −0.0181 | −0.0018 | **0.0211** | +0.0191 | **47.5** | **admitted** |
| count_primes_v2 | unpaired | −0.0405 | +0.0588 | 0.0883 | +0.1637 | 10.6 | rejected |
| count_primes_v2 | paired | +0.0068 | +0.0230 | 0.0329 | +0.0657 | 29.7 | rejected |
| power_mod | unpaired | −0.0191 | −0.0854 | 0.0870 | −0.0094 | 12.5 | rejected |
| power_mod | **paired** | +0.0033 | +0.0098 | **0.0136** | +0.0261 | **72.7** | **admitted** |

Null spread falls by 5.1×, 2.7× and 6.4× — against the 20% that median-of-9
managed in E65. That gap is the signature of drift versus independent jitter:
averaging cannot touch a common-mode term, and a ratio removes it outright.

Signal-to-noise rises from ~10–12 to 30–73.

**The sharpest number is the anchor self-score.** Scoring the starting solution
against itself involves no candidate at all, so any deviation is pure measurement
error. Unpaired it reached +0.2339 and −0.1902 in E65; paired it is −0.0181,
+0.0068 and +0.0033.

**H5 is the control that matters:** the unpaired arm admitted nothing, reproducing
E65 within this run. E65's rejections were stable, so the comparison is sound.

`count_primes_v2` still fails, on best-of-5 = 0.0657 against the 0.05 bar. That
is consistent with E64's H4: its 22× headroom is simply too small for one reward
unit to dominate residual jitter, where `power_mod` has 669×. Headroom magnitude
remains the deciding property, and the bar was not relaxed.

### Standing

**Two tasks can now measure an improvement.** That is the first admissible
instrument in this substrate after four experiments that produced none, and it is
what E63 set out to establish.

It licenses future work; it is not a capability result. Nothing here says
anything about a model improving anything. Note also that best-of-5 phantom gain
is still positive everywhere (+0.019, +0.026) — reduced below the bar, not
eliminated, because taking a maximum over any noisy reward is intrinsically
biased upward. A search loop must still be scored against a measured null
baseline rather than against zero.

## E67 — two solid tasks, and admission verdicts turn out to need replication too

Three things changed after E66 and E67 is the gate that checks them together:
paired scoring became the default for `TimedTaskEnvironment`; `count_divisors`
was added as a third task (~280× headroom, solved by *bounding* a loop at
`sqrt(n)` rather than replacing it, so it rewards a different insight from the
closed form and the binary exponentiation already in the suite); and an order
bias in the paired harness was fixed.

### A bug the anchor self-score caught immediately

`PAIRED_ROUNDS` was **7**. The order within a round alternates, so an odd count
ran anchor-first four times against candidate-first three, leaving a residual
bias that warm-up amplifies. `count_divisors` exposed it on its first run:

| Harness | `count_divisors` anchor self-score |
| --- | --- |
| 7 rounds, no warm-up | **+0.1059** |
| 8 rounds + warm-up | −0.0081, −0.0016, −0.0179 |

The anchor self-score has now caught three distinct defects (construction-time
anchors in E65, this order bias, and drift generally). It is the most valuable
measurement in the substrate precisely because it removes the candidate from the
equation: any deviation from 0.0 is pure instrument error.

**E66's figures were taken with the buggy harness**, so E67 re-measures every
task rather than carrying them forward.

### Results

| Task | Headroom | Anchor self | Null mean | Null sd | Best-of-5 | S/N | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| optimize_function | 8740× | −0.0038 | +0.0035 | 0.0148 | +0.0198 | 67.2 | **admitted** |
| count_divisors | 279× | +0.0044 | +0.0146 | 0.0141 | +0.0312 | 69.8 | **admitted** |
| power_mod | 636× | −0.0053 | +0.0130 | 0.0337 | **+0.0533** | 29.3 | rejected |
| count_primes_v2 | 28× | −0.0120 | +0.0329 | 0.0770 | +0.1288 | 12.6 | rejected |

H1, H2, H3 and H5 supported. **H4 failed: only two tasks admitted, so the
substrate is not ready** by the pre-registered bar of three.

### `power_mod` flipped, and that is the real finding

It was **admitted** in E66 at best-of-5 = +0.0261 and is **rejected** here at
+0.0533, against a 0.05 bar. Neither run is wrong. The task simply sits near the
threshold, and a borderline quantity crosses it between runs.

This is the E60/E61 lesson arriving in the substrate work. I made replication
structural for *effects* in E62 — two disjoint blocks, agreement required — and
never applied the same rule to *admission verdicts*, which are equally
threshold-crossing decisions made from a single noisy sample. E66 reported
"two tasks admitted" from one run, and one of those two does not hold up.

The correct fix is the one already used elsewhere: run the admission audit K
times and require consistent admission, reporting anything that flips as
**marginal** rather than as admitted or rejected. Under that rule the honest
current state is:

- **Solid:** `optimize_function`, `count_divisors` — comfortably inside every
  criterion on both the numbers here and E66's.
- **Marginal:** `power_mod` — flips across the bar between runs.
- **Rejected:** `count_primes_v2` — 28× headroom, consistently far outside.

`optimize_function`'s headroom now reads 8740× because the paired protocol
measures the closed form against the O(n) loop at n = 100 000, where the earlier
anchored harness never expressed the full ratio.

### Standing

Two solid tasks, one marginal, one rejected. **Not ready for a governed search
run** by the pre-registered bar, and the bar was not lowered after seeing the
result.

## E68 — replicated admission: nothing is solid

E62 made replication structural for effects and never applied it to admission
verdicts, which are equally threshold-crossing decisions taken from one noisy
sample. E68 runs the whole audit five times per task and classifies by
consistency: **solid** (admitted every round), **marginal** (some rounds),
**rejected** (none). Marginal is not half-admitted — it is a verdict that is not
yet a measurement — so it does not count toward readiness.

`gcd_fixed` was added as a fifth task (Euclidean algorithm; the naive loop is
*replaced* rather than bounded or recalled), along with a `MIN_TIMING_REPEATS`
floor after `gcd_fixed` exposed a second harness defect: at ~7 ms per call it
calibrated to 2–3 repeats, so each batch was effectively a single measurement and
two *identical* programs measured ratios from 1.00 to 1.48 — an anchor self-score
of **+0.5058**.

### Result

| Task | Headroom | Classification | Admitted rounds |
| --- | --- | --- | --- |
| optimize_function | 8934× | **rejected** | 0/5 |
| count_primes_v2 | 27× | marginal | 1/5 |
| power_mod | 638× | marginal | 1/5 |
| count_divisors | 367× | marginal | 1/5 |
| gcd_fixed | 2565× | marginal | 1/5 |

**No task is solid. The substrate is not ready**, and the readiness bar was not
lowered.

### The two failed predictions are the finding

**H3 failed:** `count_primes_v2` — 27× headroom, rejected in E64, E65, E66 *and*
E67 — was **admitted in round 3**.

**H4 failed:** `optimize_function` — 8934× headroom, the widest margin on every
criterion in E67 — was **rejected in all five rounds**.

Together these say something stronger than "borderline tasks flip". A single
round can **invert the ranking between the best and worst tasks in the suite**.
Every admission verdict this project has recorded on the executable substrate —
E63's, E64's, E66's, E67's — was a single-round measurement of a quantity that
moves this much.

### What is actually moving

Per-round null standard deviations span **0.020 to 0.415**, a 20× range within
the same task and criteria.

Two contributions, and it is worth separating them:

- **Estimator noise.** A sample standard deviation from 8 nulls carries about
  ±27% relative error (`1/sqrt(2(n-1))`). Simulated, a task whose true sd is
  0.045 measures above the 0.05 bar in roughly 20% of rounds at n=8, against 15%
  at n=30. Real, but modest.
- **A non-stationary measurement environment.** The observed 20× spread is far
  beyond what estimator error explains. The machine's timing behaviour genuinely
  changes between rounds — and E68 ran immediately after a burst of scouting
  probes, so it began under load and settled.

The second dominates, and it is not a property of any task. Pairing removed
drift *within* a measurement; it does not make the machine stationary *between*
measurements.

### Consequence for E66 and E67

Both are superseded on the specific question of which tasks are admissible. E66's
"two tasks admitted" and E67's "optimize_function and count_divisors admitted"
were single-round claims, and E68 admits `optimize_function` in zero of five
rounds. Their measurement-protocol findings stand — pairing beats anchoring, and
the numbers behind that were within-run comparisons — but their admission
verdicts do not.

### Standing

Ten experiments into the executable substrate, **no task is admissible under a
replicated standard**. That is the most accurate statement available and it is
worse than any single run suggested.

The instrument work has been genuinely convergent — saturation, censoring, probe
evasion, drift, order bias, repeat-count floors have all been found and fixed,
and each fix was validated. But the remaining obstacle is not a defect to fix in
the harness: it is that a shared, loaded developer machine is not a stable enough
platform for threshold-crossing decisions at these tolerances.

## E69 — a deterministic substrate, and the first admissible one

E63–E68 spent ten experiments making a wall-clock speedup signal trustworthy on
a developer machine. Every defect found was a *timing* defect — saturation,
censoring, probe evasion, drift, order bias, repeat-count floors — and each was
found and fixed. E68's verdict was still: no task solid.

E69 drops timing. `GradedCorrectnessEnvironment` scores the share of hidden
cases a candidate answers correctly, normalised so the starting solution is 0.0
and a fully correct solution is 1.0, unclamped so regressions go negative. Four
tasks ship a plausible but incomplete starting solution failing a documented
class of inputs — the shape of fix a coding agent is actually asked to make.

### Every prediction supported

| Task | Start | Headroom | Classification | Rounds |
| --- | --- | --- | --- | --- |
| digit_sum_graded | 9/16 | 7 cases | **solid** | 5/5 |
| count_one_bits | 12/17 | 5 cases | **solid** | 5/5 |
| collatz_steps | 12/16 | 4 cases | **solid** | 5/5 |
| integer_sqrt | 7/18 | 11 cases | **solid** | 5/5 |

Across all 20 rounds: anchor self-score exactly `+0.0000`, null sd exactly
`0.000000`, best-of-5 phantom gain exactly `0.000000`, reference exactly
`+1.0000`, determinism verified.

**Best-of-5 phantom gain is the number to compare.** The timing tasks in E68
handed a no-op search between **+0.018 and +0.325** for free. Here it is exactly
zero, because a maximum over identical values is that value. That property
cannot be engineered into a timing reward; it falls out of determinism.

### Zero spread earns a pass by evidence, not by default

E64 and E65 established that an undefined signal-to-noise ratio must **fail** —
it is undefined exactly when null spread is zero, and a reward clamped to a
constant produces that. `count_primes` v1 was admitted in E64 on the artefact.

A deterministic reward has zero spread for the opposite reason, so the criterion
needed care rather than a quiet exemption. The discriminator already existed:
the **monotonicity probe**. A censored reward returns ~0.0 for a genuinely worse
program — that is exactly how E65 caught `count_primes` v1, which scored
`+0.0000` for a program doing twice the work. Here the regression probe scores
**−0.5455 to −2.7500**, and determinism is separately verified by rescoring
identical programs across rounds. Zero spread is admitted only with both.

### The substrate is ready

Four solid tasks against a bar of three. This is the first admissible instrument
this line of work has produced, and it took abandoning the reward that was
causing the trouble rather than fixing it again.

Two honest limits. It measures **correctness improvement**, not optimisation —
narrower than the speedup framing, though still a real question for coding
agents. And readiness licenses a governed search run; it is not evidence about
one. Nothing here says anything about a model improving anything.

### What the timing work was worth

Not nothing, but less than its cost. The probe machinery — null variants that
cannot be evaded, the monotonicity probe, best-of-k phantom gain, replicated
admission — all transferred directly and is what makes E69's result
trustworthy rather than merely clean-looking. But ten experiments to conclude
that a laptop cannot time reliably is a poor trade, and the signal was there
early: E63 already showed `count_primes` handing out 0.254 for nothing.

## E70 — the governed search runs, and produces one real improvement

The first capability measurement in this series. It took **four attempts**, and
three of them failed on measurement, not on the science.

### The three failures, because they are the lesson

| Attempt | Failure | How it was caught |
| --- | --- | --- |
| E70 | 15s timeout against a proposer emitting non-terminating programs 25–58% of the time | process state: 39s of CPU in 2h11m — blocked, not computing |
| E70b | 0.5s timeout, below the noise floor for a *correct* program on a loaded machine | **the null control**: `null_only` scored −0.4444 where exactly 0.0 is required |
| E70c | calibrated timeout; sound but still load-dependent, and opaque — no progress output | abandoned at 1h29m in favour of the guarded run |

All three are the same error: **using time to detect non-termination**, when the
two failure modes move in opposite directions with machine load. No timeout
value resolves it.

`recursive_lab/loop_guard.py` removes the dependence: every loop shares one
bounded iteration counter, so a non-terminating program returns wrong answers in
milliseconds, fails its cases and is never promoted. Validated on 240 real
mutants — all ran to completion at 1.9–178.8 ms, zero timeouts. The limit comes
from a cost model (largest legitimate workload ~350 iterations, so 20,000 is
~57× headroom); an earlier draft used 1,000,000 and had to be killed after ten
minutes, which is *the same failure in a different currency*.

### Result

| Task | governed | null_only | random_walk | hang rate |
| --- | --- | --- | --- | --- |
| digit_sum_graded | +0.0000 | 0.0000 | −1.0000 | 3.6% |
| **count_one_bits** | **+0.5000** | 0.0000 | −2.0000 | 4.7% |
| collatz_steps | +0.0000 | 0.0000 | −1.6667 | 14% |
| integer_sqrt | +0.0000 | 0.0000 | −0.5333 | 42.9% |
| **pooled** | **+0.1250** | **0.0000** | **−1.3000** | |

**A governed mutation search produced a genuine held-out correctness improvement
on one of four tasks.** On `count_one_bits` it scored +0.3333 on development and
**+0.5000 on held-out** — the search never saw those cases, and the held-out
figure is the *higher* of the two, so this is not overfitting.

**H1, H2, H4, H5 supported.** The two controls behaved exactly as designed:
`null_only` returned **exactly 0.0** on every task and seed, and `random_walk` —
identical operators and budget, selection removed — **actively destroyed** the
programs at −1.30 pooled. The +1.425 gap between them is attributable to
selection alone.

### Two corrections to the record

**H6's recorded verdict is wrong.** The plan states "fewer than 5% of candidates
fail every case on `digit_sum_graded` and `count_one_bits`"; observed 3.6% and
4.7%, which satisfies it. The runner still graded it with E70b's superseded
0.20–0.70 band because I updated the statement and not the check. That is a
grader defect, not a finding — the same class of error as E64's H5. The code is
corrected; the recorded report is left as it ran.

**H3's failure is under-powered, not informative.** I predicted `collatz_steps`
would improve most, since its fix is a single constant mutation (`return 0` →
`return -1`). It scored 0.0. But the mutator picks uniformly among five
operators, then among ~10 constants, then a branch and a delta:
P ≈ 0.25% per candidate, giving **31.3% per seed over 150 evaluations and a
32.4% chance that none of three seeds finds it**. So 0/3 is an unremarkable
outcome of too small a budget. H3 should not be read as evidence that the fix is
unreachable — the honest statement is that the experiment could not distinguish
the two.

### Claim boundary

A generic AST mutator on four small Python tasks. **No model is in the loop.**
This says nothing about model self-improvement and nothing about a recursive
effect. What it does establish is that the instrument works end to end: a search
ran, a control confirmed zero phantom gain, and a held-out improvement was
measured rather than asserted.

## E71 — a model in the proposer slot, and the tasks turn out to be too easy

The local Gemma 4 E2B server replaces the AST mutator. 192 model calls, 192
parsed, 186 validator-clean (97%), 638 seconds, nothing leaving the machine.

| Task | governed | single_shot | null_only |
| --- | --- | --- | --- |
| digit_sum_graded | +1.0000 | +1.0000 | 0.0000 |
| count_one_bits | +1.0000 | +1.0000 | 0.0000 |
| collatz_steps | +1.0000 | +1.0000 | 0.0000 |
| integer_sqrt | +1.0000 | +0.3333 | 0.0000 |
| **pooled** | **+1.0000** | **+0.8333** | **0.0000** |

**The model solves all four tasks completely on held-out cases.** H1, H2, H3, H4
and H6 all supported. Against E70's mutator, which managed one task out of four
at +0.5, this is a different order of capability.

### The loop earned its cost exactly once

Every governed run recorded **exactly one promotion**. The model fixes the bug on
its first valid proposal and the remaining fourteen add nothing. Only
`integer_sqrt` distinguishes the arms:

| | per-seed held-out |
| --- | --- |
| single_shot | [0.0, 0.0, **1.0**] |
| governed | [1.0, 1.0, 1.0] |

One-shot succeeds a third of the time there; the governed loop converts that to
three out of three. That is a real benefit of iterate-and-select, and it is the
*only* one in the run. On the other three tasks the governed machinery is
decoration.

**The honest reading is that these tasks are too easy to test search.** They were
calibrated in E69 against a generic mutator that could barely move them; a
language model one-shots them. The substrate has gone from too noisy to measure
anything, straight past useful, to too easy to discriminate.

### My void rule is wrong, and it fired on the successes

H5 failed: **10 of 12 governed runs were flagged VOID** — including runs scoring
+1.0000. `collatz_steps` produced *one* unique candidate across 15 proposals.

That looks exactly like the E58 defect I opened this review with, and it is not.
E58's collapse was six calls yielding one program while the report claimed a
result from n=1. Here the single repeated candidate **is the correct fix**: the
model solved the task on proposal 1 and then returned the same correct program
fourteen more times. Low diversity *after success* is convergence, not failure to
search.

My pre-registered rule cannot tell those apart, because it tests diversity alone.
The fix is to void only when diversity is low **and** no improvement was
achieved. I am not applying that retroactively to rescue this run — the frozen
rule fired as written and is recorded as failing. It is pre-registered for the
next run instead.

Worth stating plainly: the headline result comes from runs my own rule marks
void. The improvement itself is not in doubt — it is measured on held-out cases
the search never saw, with a null control at exactly 0.0 — but the rule that was
supposed to certify the search is unfit and needs replacing before it certifies
anything.

### Claim boundary

A local model repairing four small Python functions under a governed loop. The
model does not modify its own scaffold, weights, or proposer. **Nothing here is
recursive and nothing here is self-improvement.**

## Recommended next steps

1. ~~**Change `minimum_policy_disagreements` to a rate** and pre-register it
   before the next cohort.~~ Done in E60; five of nine families were rejected.
2. ~~**Report per-family, not pooled, as the primary claim.**~~ Done in E60,
   pre-registered as the primary analysis.
3. ~~**Pre-register a minimum effect size.**~~ Done in E61 at 0.005 regret units;
   it immediately demoted a significant-but-negligible result.
4. ~~**Investigate the `rugged` regression.**~~ Done in E61: it did not
   replicate. No further work is warranted.
5. ~~**Replicate before reporting, as policy.**~~ Done in E62: two disjoint
   held-out blocks, with a replication rule that refuses single-block effects.
6. ~~**Revisit the promotion objective.**~~ Done in E62: worst-family selection
   is dominated on its own yardstick by signal-weighted selection, replicated
   across both blocks. **Stop using worst-family selection.**

7. **Put bootstrap intervals on objective-level contrasts.** E62 compared
   objectives by point estimate only. Cheap to fix, and the current evidence for
   the headline is weaker than it should be.
8. ~~**Move to the executable substrate.**~~ Audited in E63. One task of three
   is usable; see the fixes below before running any search on it.
9. ~~**Fix `count_primes` or drop it.**~~ Rebuilt as `count_primes_v2` in E64.
   Still not usable: 22x headroom is too small against host jitter.
10. ~~**Add a minimum-detectable-effect criterion.**~~ Added in E64 as
   signal-to-noise, and it exposed a deeper problem — see 11.
11. ~~**Make the audit criteria immune to censoring.**~~ Done in E65, which
   also found the probe itself was evadable. Undefined signal-to-noise now fails.
12. ~~**Score candidates as a median of m repeated evaluations.**~~ Tried in E65
   and it **does not work**: sd fell only 20% from m=1 to m=9 where sqrt(m)
   predicts 67%. The noise is drift, not independent jitter.
13. ~~**Interleave anchor and candidate measurement.**~~ Done in E66. Null
   spread fell 2.7-6.4x and two tasks are now admissible.
14. ~~**Adopt paired scoring as the substrate's default.**~~ Done in E67.
   `anchored` remains selectable only so E66's runner stays reproducible.
15. **Score any search against a measured null baseline, not against zero.**
   Best-of-5 phantom gain is still +0.019 to +0.026 under pairing — below the
   bar, not eliminated, because a maximum over noisy rewards is intrinsically
   biased upward. A claimed improvement must clear the null best-of-k for the
   same k the search used.
16. **Retire `sum_digits`.** It ships already solved and was not worth repairing;
   `power_mod` replaces it as a second task with real headroom.
17. ~~**Replicate admission verdicts, not just effects.**~~ Done in E68. No
   task is solid; a single round can invert the ranking between the best and
   worst tasks in the suite.
18. ~~**Add one or two more high-headroom tasks.**~~ `gcd_fixed` added in E68
   (2565x, Euclidean algorithm). Headroom is no longer the binding constraint.
19. ~~**Stabilise the measurement platform.**~~ Not pursued. E69 removed the
   need by dropping the timing signal; the timing tasks remain unusable and are
   left that way rather than tuned further.
20. ~~**Abandon wall-clock reward for this substrate.**~~ Done in E69. Four
   deterministic tasks, all solid across five rounds, zero phantom gain.
21. ~~**Run the governed search.**~~ Done in E70d: +0.5000 held-out on
   count_one_bits, null control at exactly 0.0, unselected control at -1.30.
22. **Raise the budget before concluding a task is unreachable.** H3 failed at
   31% power per seed. Three of four tasks scoring 0.0 is currently ambiguous
   between "the mutator cannot reach it" and "150 evaluations was too few". A
   power calculation belongs in the plan, not in the post-mortem.
23. ~~**Put a model in the loop.**~~ Done in E71: local Gemma 4 E2B solves all
   four tasks on held-out cases, pooled +1.0000.
27. **Fix the void rule before it certifies anything.** Void only when diversity
   is low AND no improvement was achieved. As written it flagged 10 of 12
   *successful* runs, because it cannot distinguish convergence-after-success
   from never having searched.
28. **Harder tasks.** These four were calibrated against a weak mutator and a
   model one-shots them; every governed run made exactly one promotion. To
   measure search rather than single-shot capability, tasks need to be beyond
   one proposal — multi-bug programs, or contracts a single edit cannot satisfy.
29. **Then re-ask whether the loop is worth its cost.** On this suite it earned
   its keep exactly once, converting integer_sqrt from 1-in-3 to 3-in-3. That is
   a real but narrow result and it deserves a benchmark that can test it.
24. **Hold out a task.** All four current tasks are visible to any search. At
   least one should be sealed for a final transfer check, per `POC_PLAN.md`'s
   sealed-suite discipline, before any result is reported as generalising.
25. **Restore real search in the live loop.** Wire
   `recursive_lab.candidate_diversity` into the live runners so E58's collapse
   cannot recur silently, and vary temperature and prompt across the candidate
   stream.
26. **Split the tracks.** Keep Capsulang/MeTTa governance work in its own
   numbering. It is decent engineering, but sharing the E-series makes parity of
   machinery read as capability evidence in the ledger.

## Claim boundary

E59 and E60 are synthetic landscape studies of one exploitation rule. Neither is
evidence of scaffold self-improvement, and certainly not of a recursive effect.
Their value
is that it establishes a benchmark on which such a claim could, for the first
time in this series, actually be tested.

## Validation

- 296 tests pass (186 before this work).
- All 55 `report_digest` values in `experiments/` reproduce exactly; 0
  mismatches. No existing experiment JSON or runner was modified.
- `verify_capsulang_evidence.py` exits 0 with `contradictions=0 assumptions=1`.
