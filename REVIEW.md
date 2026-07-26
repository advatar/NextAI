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
13. **Interleave anchor and candidate measurement.** This is now the blocking
   item. Every environment captures its anchor once at construction and scores
   candidates against it minutes later, so the starting solution itself scores
   +0.2339 (count_primes_v2) and -0.1902 (power_mod) instead of 0.0 by
   definition. Re-measure the anchor adjacent to each candidate and compute the
   reward from the paired difference so drift cancels. E59-E62 already pair on
   the synthetic side; the executable substrate never adopted it.
14. **Retire `sum_digits`.** It ships already solved and was not worth repairing;
   `power_mod` replaces it as a second task with real headroom.
15. **Then add two or three more tasks with large headroom.** `power_mod`'s 669x
   is what made it well-behaved; `count_primes_v2`'s 22x is what sank it.
16. **Restore real search in the live loop.** Wire
   `recursive_lab.candidate_diversity` into the live runners so E58's collapse
   cannot recur silently, and vary temperature and prompt across the candidate
   stream.
17. **Split the tracks.** Keep Capsulang/MeTTa governance work in its own
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
