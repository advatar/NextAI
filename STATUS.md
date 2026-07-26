# Status

## Completed — E69, a deterministic substrate: ready for a governed search run

Readiness audit. **No capability claim.** Pre-registered in
`experiments/E69-preregistration.json` (`f8a63a4d…`). **All five predictions
supported.**

E63–E68 spent ten experiments making a wall-clock signal trustworthy and every
defect found was a timing defect. E69 drops timing.
`GradedCorrectnessEnvironment` scores the share of hidden cases a candidate
answers correctly, normalised so the starting solution is 0.0 and full
correctness is 1.0, unclamped so regressions go negative. Four tasks ship a
plausible but incomplete starting solution.

| Task | Start | Headroom | Classification | Rounds |
| --- | --- | --- | --- | --- |
| digit_sum_graded | 9/16 | 7 cases | solid | 5/5 |
| count_one_bits | 12/17 | 5 cases | solid | 5/5 |
| collatz_steps | 12/16 | 4 cases | solid | 5/5 |
| integer_sqrt | 7/18 | 11 cases | solid | 5/5 |

Across all 20 rounds: anchor self-score exactly `+0.0000`, null sd exactly
`0.000000`, **best-of-5 phantom gain exactly `0.000000`** against E68's timing
range of +0.018 to +0.325, reference exactly `+1.0000`, determinism verified.

Zero spread is admitted by evidence, not by default. E64/E65 established that an
undefined signal-to-noise ratio must fail, because a censored reward produces
exactly that — `count_primes` v1 was admitted in E64 on the artefact. The
discriminator is the monotonicity probe, which already caught that case (v1
scored `+0.0000` for a program doing twice the work). Here the regression probe
scores **−0.5455 to −2.7500** and determinism is separately verified.

**Four solid tasks against a bar of three: the substrate is ready.** This is the
first admissible instrument this line of work has produced, and it came from
abandoning the reward causing the trouble rather than fixing it again.

Limits: this measures **correctness improvement**, not optimisation — narrower
than the speedup framing. Readiness licenses a governed search run; it is not
evidence about one.

Next: run the governed search on these four tasks, wire in
`recursive_lab.candidate_diversity` so a collapsed proposer stream voids the run
(the E58 defect), pre-register the effect size and replication rule beforehand,
and seal at least one task for a transfer check.

Validation: 432 tests pass; all 66 `report_digest` values reproduce; no existing
experiment JSON or v1 environment modified.

## Completed — E68, replicated admission: no task is solid

Replicated readiness audit. **No capability claim.** Pre-registered in
`experiments/E68-preregistration.json` (`96b784a9…`). Five rounds per task,
classified **solid** (admitted every round) / **marginal** (some) / **rejected**
(none). Marginal does not count toward readiness: a verdict that changes between
rounds is not yet a measurement.

Added `gcd_fixed` (Euclidean algorithm, 2565×, naive loop *replaced* rather than
bounded) and a `MIN_TIMING_REPEATS` floor, after `gcd_fixed` exposed a second
harness defect — at ~7 ms per call it calibrated to 2–3 repeats, so two identical
programs measured ratios from 1.00 to 1.48 (anchor self-score **+0.5058**). Its
timing argument dropped 120_000 → 20_000. Also gated correctness in the
`optimize_function` paired scorer, which in E67 timed candidates without checking
they were correct.

| Task | Headroom | Classification | Rounds admitted |
| --- | --- | --- | --- |
| optimize_function | 8934× | **rejected** | 0/5 |
| count_primes_v2 | 27× | marginal | 1/5 |
| power_mod | 638× | marginal | 1/5 |
| count_divisors | 367× | marginal | 1/5 |
| gcd_fixed | 2565× | marginal | 1/5 |

**No task is solid. The substrate is not ready.** The bar was not lowered.

H1, H2, H5 supported. The two failures are the finding: **H3** — `count_primes_v2`
(27×, rejected in E64–E67) was admitted in round 3; **H4** — `optimize_function`
(8934×, widest margins in E67) was rejected in all five. A single round can
**invert the ranking between the best and worst tasks in the suite**.

Per-round null sd spans **0.020–0.415** on the same task. Sd estimated from 8
nulls carries ±27% error and contributes, but a 20× spread is far beyond that:
the measurement environment is non-stationary between rounds. Pairing removed
drift *within* a measurement; it does not make the machine stationary *between*
measurements.

E66 and E67 are superseded on which tasks are admissible — both reported
single-round verdicts. Their protocol findings (pairing beats anchoring) stand,
being within-run comparisons.

Next blocking item is not a code fix: stabilise the platform (idle machine,
settling period, 30+ nulls per round), or drop wall-clock reward for this
substrate in favour of correctness-only tasks, which carry no timing noise and
cannot be gamed by best-of-k phantom gain.

Validation: 415 tests pass; all 65 `report_digest` values reproduce; no existing
experiment JSON or v1 environment modified. One flaky timing assertion in
`tests/test_paired_timing.py` was loosened to a median-of-three with a wide bound
— a tight tolerance there fails for exactly the reason E68 documents.

## Completed — E67, two solid tasks; admission verdicts need replication too

Readiness audit. **No capability claim.** Pre-registered in
`experiments/E67-preregistration.json` (`1c3c3339…`).

Three changes since E66, checked together: paired scoring is now the
`TimedTaskEnvironment` default (`anchored` retained only so
`compare_e66_paired_timing.py` stays reproducible); `count_divisors` added as a
third task (~280× headroom, solved by bounding a loop at `sqrt(n)` rather than
replacing it); and an order bias fixed in the paired harness.

**The order bias.** `PAIRED_ROUNDS` was 7. Order alternates within a round, so an
odd count ran anchor-first four times against candidate-first three.
`count_divisors` exposed it at once — its anchor self-score, which must be 0.0
because no candidate is involved, read **+0.1059**. With an even count and a
warm-up it reads −0.0081/−0.0016/−0.0179. E66's figures were taken with the buggy
harness, so every task was re-measured here rather than carried forward.

| Task | Headroom | Anchor self | Null mean | Null sd | Best-of-5 | S/N | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| optimize_function | 8740× | −0.0038 | +0.0035 | 0.0148 | +0.0198 | 67.2 | admitted |
| count_divisors | 279× | +0.0044 | +0.0146 | 0.0141 | +0.0312 | 69.8 | admitted |
| power_mod | 636× | −0.0053 | +0.0130 | 0.0337 | +0.0533 | 29.3 | rejected |
| count_primes_v2 | 28× | −0.0120 | +0.0329 | 0.0770 | +0.1288 | 12.6 | rejected |

H1, H2, H3, H5 supported. **H4 failed** — only two tasks admitted against a
pre-registered readiness bar of three, so the substrate is **not ready** for a
governed search run. The bar was not lowered.

**`power_mod` flipped.** Admitted in E66 at best-of-5 = +0.0261, rejected here at
+0.0533 against a 0.05 bar. Neither run is wrong; the task sits near the
threshold. E62 made replication structural for *effects* and that rule was never
applied to *admission verdicts*, which are equally threshold-crossing decisions
taken from a single noisy sample. Honest current state: **solid** —
`optimize_function`, `count_divisors`; **marginal** — `power_mod`; **rejected** —
`count_primes_v2`.

Next blocking item: run the admission audit K times, require consistent
admission, and report anything that flips as marginal.

Validation: 415 tests pass; all 64 `report_digest` values reproduce; no existing
experiment JSON or v1 environment modified.

## Completed — E66, paired measurement works; two tasks are usable

Measurement-protocol comparison. **No capability claim.** Pre-registered in
`experiments/E66-preregistration.json` (`815e8e22…`). **All five predictions
supported.**

`recursive_lab/paired_timing.py` measures anchor and candidate interleaved in one
process, alternating order each round, and computes the reward from the ratio
`t_candidate / t_anchor`, so multiplicative drift cancels. Only the anchor is
co-located with candidate code — it is public, printed in the task prompt — and a
test asserts the held-out reference never enters the candidate's process.

Both protocols measured on the same tasks in the same run.

| Task | Protocol | Anchor self | Null mean | Null sd | Best-of-5 | S/N | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| optimize_function | unpaired | +0.0000 | −0.1072 | 0.1070 | −0.0473 | 10.3 | rejected |
| optimize_function | paired | −0.0181 | −0.0018 | 0.0211 | +0.0191 | 47.5 | **admitted** |
| count_primes_v2 | unpaired | −0.0405 | +0.0588 | 0.0883 | +0.1637 | 10.6 | rejected |
| count_primes_v2 | paired | +0.0068 | +0.0230 | 0.0329 | +0.0657 | 29.7 | rejected |
| power_mod | unpaired | −0.0191 | −0.0854 | 0.0870 | −0.0094 | 12.5 | rejected |
| power_mod | paired | +0.0033 | +0.0098 | 0.0136 | +0.0261 | 72.7 | **admitted** |

Null spread falls 5.1×, 2.7× and 6.4×, against the 20% median-of-9 managed in
E65 — the signature of drift rather than independent jitter. Signal-to-noise
rises from ~10–12 to 30–73. The anchor self-score, which involves no candidate
and must be 0.0 by definition, moves from +0.2339/−0.1902 (E65, unpaired) to
−0.0181/+0.0068/+0.0033.

H5 is the control: the unpaired arm admitted nothing, reproducing E65 within this
run, so E65's rejections were stable and the comparison is sound.

`count_primes_v2` still fails on best-of-5 = 0.0657 against the 0.05 bar,
consistent with E64's H4 — its 22× headroom is too small where `power_mod` has
669×. The bar was not relaxed.

Standing: **two tasks can now measure an improvement**, the first admissible
instrument after four experiments that produced none. This licenses future work;
it is not a capability result. Best-of-5 phantom gain remains positive (+0.019,
+0.026) because a maximum over noisy rewards is intrinsically biased upward, so a
search must be scored against a measured null baseline, not against zero.

Validation: 410 tests pass; all 63 `report_digest` values reproduce; no existing
experiment JSON or v1 environment modified.

## Completed — E65, no task in the executable suite can measure an improvement

Instrument audit only. **No capability claim.** Pre-registered in
`experiments/E65-preregistration.json` (`bb18d1b9…`).

E63 and E64 both used "starting solution + appended comment" as the null probe.
`optimize_function` compares candidates by `ast.dump`, so the comment was
invisible: it recognised the variant as the *same program* and returned exact
zeros by design. Both audits read that as a perfect noise profile and admitted
it. The probe was **evaded** — neither precision nor censoring. Those two
admissions are superseded.

E65 uses AST-distinct null variants (renamed locals, free at runtime), a
monotonicity probe, and a median-of-*m* curve.

| Task | Monotonicity | Null mean (m=9) | Null sd | Best-of-5 | Signal/noise | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| optimize_function | responds (−1.17) | +0.1493 | 0.1422 | +0.2934 | 6.0 | rejected |
| count_primes (v1) | **+0.0000 — none** | +0.0000 | 0.0000 | +0.0000 | undefined | rejected |
| count_primes_v2 | responds (−1.10) | +0.0035 | 0.1296 | +0.0920 | 7.5 | rejected |
| power_mod | responds (−0.69) | −0.0911 | 0.0851 | −0.0257 | 12.8 | rejected |

`optimize_function` is the **worst**-behaved task, not the best: null sd 0.1097 at
m=1 against E64's recorded 0.0000, a null rename earning a mean of +0.17, and a
best-of-5 phantom gain of +0.29 — higher than the 0.254 that got `count_primes`
v1 rejected in E63.

`count_primes` v1 is now caught cleanly: a program doing exactly twice the work
scored `+0.0000`. Its signal-to-noise is undefined, which now fails rather than
being silently skipped as in E64.

H1–H3 supported; the repaired base class does fix monotonicity.

**H4 failed, and it rules out the E64 recommendation.** `power_mod`'s null sd fell
only 0.1064 → 0.0851 from m=1 to m=9, a 20% reduction where √m predicts 67%.
Averaging buys almost nothing because the noise is **drift**, not independent
jitter. The direct evidence: starting solutions score `+0.2339`
(count_primes_v2) and `−0.1902` (power_mod) when they must score 0.0 by
definition. Every environment captures its anchor once at construction and scores
candidates against it minutes later.

Next blocking item: **interleave anchor and candidate measurement** so drift
cancels in a paired difference. E59–E62 already pair on the synthetic side; the
executable substrate never adopted it.

Standing: four experiments in, no task can measure an improvement and two prior
admissions were wrong. Nothing licenses running a search loop.

Validation: 394 tests pass; all 62 `report_digest` values reproduce; no existing
experiment JSON or v1 environment modified.

## Completed — E64, the repairs worked and the audit criteria did not

Instrument audit only. Makes **no capability claim**. Pre-registered in
`experiments/E64-preregistration.json` (`744dc2be…`).

Built the E63 repairs: `environments/timed_task.py` (median-of-calibrated-batch
anchors, **unclamped** reward per `base.py`'s documented `[<0, ~1+]` contract, a
held-out reference defining 1.0), `count_primes_v2`, and `power_mod` — a new task
whose optimum is an algorithm rather than a closed form. The v1 environments are
untouched so prior records stay interpretable.

| Task | Headroom | Null mean | Null sd | Best-of-5 | Signal/noise | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| optimize_function | — | +0.0000 | 0.0000 | 0.0000 | undefined | admitted |
| count_primes (v1) | — | +0.0000 | 0.0000 | 0.0000 | undefined | admitted |
| count_primes_v2 | 22.2× | −0.2726 | 0.3684 | 0.0944 | 3.5 | rejected |
| power_mod | 669× | +0.0132 | 0.0495 | 0.0727 | 19.9 | rejected |

Four of five predictions failed, and the reason matters more than the repairs.

**`count_primes` v1 — the task E63 rejected as worst — was admitted.** Same
unrepaired code. This run's import-time baseline landed at 6.178 ms while nulls
ran 6.36–7.39 ms, so every unclamped reward was negative and `max(0.0, …)`
floored all of them to exactly zero. The clamp manufactured a perfect noise
profile. Zero variance from censoring is indistinguishable from zero variance
from precision. `optimize_function:363` likewise applies a 3% deadband, so its
exact zeros are censoring too.

**The signal criterion added to close E63's hole was silently skipped.**
Signal-to-noise is undefined exactly when null sd is zero — the censoring case —
so it was skipped for both admitted tasks. Worse, the H5 grader read
`value is None or value >= threshold`, counting undefined as passing, so H5 was
graded *supported* while performing the very silent skip it was written to
detect. **The recorded report's `H5: supported` must be read as NOT supported.**
The rule is corrected in the runner with regression tests pinning both the buggy
and corrected semantics.

**`power_mod` is the best-behaved task in the suite and was rejected** on
best-of-5 = 0.073 against a 0.05 bar, despite a near-zero null mean, 19.9
signal-to-noise and 669× headroom — while two censored tasks were admitted. The
criteria are ranking censored rewards above honest ones; that is a defect in the
audit, not in `power_mod`. The 0.05 bar is not being relaxed post hoc.

H4 was the one supported prediction: `count_primes_v2` genuinely fails, because
22× headroom is too small against host jitter. The repair is necessary but not
sufficient — headroom magnitude decides usability. Its honest −0.273 null mean is
preferable to v1's censored +0.0000.

Blocking item for next time: best-of-k phantom gain is intrinsic to max-selection
over any noisy reward and cannot be engineered out of an environment. The fix is
a scoring protocol — median of *m* repeated evaluations, shrinking spread by
about √m — plus requiring an improvement to exceed the measured best-of-k null
baseline.

Validation: 373 tests pass; all 61 `report_digest` values reproduce; no existing
experiment JSON or v1 environment modified. Wall-clock measurements are not
bit-reproducible; the digest attests to the recorded report.

## Completed — E63, executable substrate audit

Instrument audit only. Makes **no capability claim** under any outcome.
Pre-registered in `experiments/E63-preregistration.json` (`0ec039c7…`) with the
disclosure that a scouting probe informed the thresholds. Probes use **null
variants**: each environment's starting solution with a trailing comment
appended, semantically identical, so any non-zero reward is artefact.

| Task | Starting reward | Null sd | Best-of-5 null | Verdict |
| --- | --- | --- | --- | --- |
| optimize_function | 0.0000 | 0.0000 | 0.0000 | admitted |
| count_primes | 0.0000 | 0.0760 | 0.2539 | rejected |
| sum_digits | 1.0000 | 0.0000 | 1.0000 | rejected |

- `sum_digits` ships already solved — its starting solution scores the maximum.
- `count_primes` cannot distinguish work from noise. A search keeping the best of
  five no-op proposals books **0.254 of reward for changing nothing**.
- `count_primes.py:16` sets the whole reward scale from a **single** timing
  measurement at construction. In this run it landed 21.8% slow, handing every
  null variant a free +0.174. The scouting probe saw the same defect with the
  opposite sign (−0.171 before clamping). The reference is unstable in magnitude
  and direction between runs.

H1–H3 supported. **H4 not supported**: the predicted clamp rectification bias was
+0.0001, because in this run the nulls landed positive and the clamp barely
bound — the unstable single-measurement reference is the more fundamental
problem. **H5 not supported**: `optimize_function` was admitted, and an unplanned
follow-up (recorded as unplanned) confirmed it detects real signal — the closed
form `(n−1)n(2n−1)/6` scores a stable 1.0, raw 2.1e-07 s against 8.6e-03 s.

Hole found in the frozen criteria: they test for absence of noise but never for
presence of signal, so a constant reward function would pass all four. A
minimum-detectable-effect criterion is pre-registered for next time. This is the
mirror of the E51 mistake.

Validation: 358 tests pass; all 60 `report_digest` values reproduce; no existing
experiment JSON, environment, or runner modified. Note this experiment measures
wall-clock time, so its numbers are not bit-reproducible; the digest attests to
the recorded report.

## Completed — E62, worst-family selection is dominated on its own yardstick

- [x] Pre-register three selection objectives, two disjoint held-out blocks, a
  replication rule, and five predictions in `experiments/E62-preregistration.json`
  (`a2484275…`) before running. Seeds 2000–2119 / 3000–3119 / 4000–4119.
- [x] Report **both** yardsticks for every selected router, so no objective is
  scored only on the metric it optimises.
- [x] Make replication structural: an effect counts only if both blocks agree in
  sign, both intervals exclude zero, and both clear the 0.005 effect floor.
- [x] Run and grade every prediction.

Selection: `worst_family` and `macro_mean` both collapsed to unconditional
exploitation (R² ≥ 0.0); `signal_weighted` — weighting families by their
policy-disagreement rate — recovered a support-aware **R² ≥ 0.5** gate.

**Worst-family selection loses on the worst-family yardstick.** It minimised
worst-family regret on training data, yet on held-out seeds the
signal-weighted router is better on that exact metric by 0.0167 (block A) and
0.0150 (block B) — clearing the effect floor and agreeing across blocks. Maximin
selection generalises worse than what it was chosen to beat. On macro-mean the
same ordering holds but the gap (0.0034 / 0.0033) is below the floor and is
reported as negligible.

H1–H4 supported, including the stability check: both blocks rank the objectives
identically. **H5 was not supported** — no effect cleared in one block and failed
in the other, so the replication rule caught nothing this time. It is insurance
that did not need to pay out, not machinery that proved itself.

`monotone` is the one solidly replicated per-family effect (−0.0228 / −0.0222).
Every other family is inconclusive in both blocks; `decoy` swung +0.01417 to
−0.01000, a fair picture of the noise floor.

Limitation carried forward: objective-level contrasts use point estimates only.
The frozen plan should have required paired bootstrap intervals on them and did
not, so the headline rests on two-block agreement rather than an interval.
Pre-registered for the next run rather than added post hoc.

Validation: 358 tests pass; all 59 `report_digest` values reproduce; no existing
experiment JSON or runner modified.

Recommendation: **stop using worst-family selection.**

## Completed — E61, the rugged regression does not replicate

- [x] Add an `endpoint_coinflip` exploitation mode and endpoint-pick accounting
  to `scaled_landscape`, so the surrogate's two effects — narrowing search to
  column endpoints, and using the fit to choose between them — can be separated.
- [x] Pre-register the ablation, a 0.005 minimum effect size, and five
  predictions in `experiments/E61-preregistration.json` (`235d865d…`) before
  running, on seeds 1000–1239 disjoint from E59/E60.
- [x] Run the ablation and grade every prediction, including the three that
  failed.

**The E60 `rugged` regression was a false positive.** On fresh seeds it measured
`−0.00165`, CI `[−0.00843, +0.00503]` — inconclusive, spanning zero, opposite
sign — against E60's `+0.00836`, CI `[+0.00167, +0.01533]`. E60's interval barely
excluded zero across nine families with no multiplicity correction, exactly as
its own pre-registration disclosed. Replication caught it. The earlier
description of it as the most actionable finding in the series was wrong and is
corrected in `REVIEW.md`.

Three of five predictions failed (H1, H2, H5), all because they presupposed a
real effect on rugged.

The two mechanistic predictions held. The fit-following component
(`e60_promoted` minus `endpoint_control`, two arms differing only in whether the
fit or a coin flip picks the endpoint) is `+0.00014`, CI `[−0.00581, +0.00611]`
on rugged — no signal, as expected on a hash-derived surface — and `−0.00261`,
CI `[−0.00445, −0.00074]` on monotone. The positive control passes, so the
ablation measures what it claims to.

Unplanned finding: on monotone, E41's older gate is three times better than
E60's promoted router (`−0.01967` against `−0.00625`). E60's router demands
`variance >= 0.03`, which monotone rarely produces, so it declines to exploit 88%
of the time. Worst-family selection picked a router that is mediocre everywhere
over one that is excellent where signal exists — the promotion objective is worth
revisiting.

The new minimum effect size earned its place immediately, demoting
`endpoint_control` on monotone (`−0.00364`, interval excluding zero) to
negligible rather than reporting a fourth result.

Validation: 340 tests pass; all 58 `report_digest` values reproduce; no existing
experiment JSON or runner modified.

## Completed — E60, the corrected admission gate under a frozen plan

- [x] Add `minimum_policy_disagreement_rate` to `AdmissionCriteria`, checked
  conjunctively with the existing count. Set to 0.2 to mirror the saturation
  bound rather than tuned against observed rates.
- [x] Freeze the criteria, instrument, analysis plan and four falsifiable
  predictions in `experiments/E60-preregistration.json` **before** running,
  content-hashed (`6c7c9aa9…`).
- [x] Make the runner reload the frozen plan, recompute its digest, and fail
  closed on drift, mirroring `recursive_lab/manifest.py`.
- [x] Run E60 and grade every prediction, including any that failed.

Validation: 333 tests pass; all 57 `report_digest` values reproduce; no existing
experiment JSON or runner modified.

The count-based gate was vacuous as suspected. Five of nine families were
rejected, all on the rate criterion: spike 0.033, checkerboard 0.058, plateau
0.067, ridge 0.142, decoy 0.150 — each clearing the old count of 3 while unable
to express any effect.

Primary result (per family, pre-registered as the headline):

| Family | Regret delta | 95% CI | Verdict |
| --- | --- | --- | --- |
| monotone | −0.00732 | [−0.01001, −0.00456] | reduces regret |
| curved | −0.00003 | [−0.00006, −0.00001] | reduces regret |
| rugged | +0.00836 | [+0.00167, +0.01533] | increases regret |
| sinusoidal | −0.00333 | [−0.01334, +0.00667] | inconclusive |

Secondary pooled: −0.00058, CI [−0.00382, +0.00269] — inconclusive. All four
predictions (H1–H4) were supported.

Two caveats recorded rather than smoothed over: the promoted router **harms**
`rugged` on held-out seeds, with an interval excluding zero on the wrong side;
and `curved`'s significant interval covers an effect of −0.00003, which is
statistically real and practically meaningless. A minimum effect size is
pre-registered as the next criterion.

Claim boundary: a synthetic landscape study of one exploitation rule. Not
evidence of scaffold self-improvement or of a recursive effect.

## Completed — fix the benchmark instrument and land E59

Full review in [`REVIEW.md`](REVIEW.md).

- [x] Review the E30–E58 series and locate the stall: E51 returned
  `admitted: false` / "reject and redesign cohort", and the redesign never
  happened. E52–E58 pivoted to governance parity instead of capability.
- [x] Diagnose the root cause quantitatively: the 5×5 grid with a 20-evaluation
  budget meant every run enumerated 80% of the search space, so no policy could
  beat random. Coverage is `(exploration_per_column + 1) / grid_size`.
- [x] Add `recursive_lab/scaled_landscape.py`, generalizing all nine families to
  arbitrary grid size, with cell-for-cell equality against the original E37/E40/E42
  implementations asserted in tests.
- [x] Replace the saturating binary `target_hit` with continuous `regret`.
- [x] Add `recursive_lab/admission.py` — E51's audit as a pre-registration gate
  that runs before a cohort may emit evidence, judged from the random baseline
  only.
- [x] Add `recursive_lab/candidate_diversity.py` — a degenerate proposer stream
  now voids a run. Pins E58's 6-calls/1-unique-candidate collapse.
- [x] Add `verify_capsulang_evidence.py` — governance scenarios cross-checked
  against the experiment JSON they cite; the E51 contradiction now surfaces on
  every run, and a new scenario shows the governor refusing promotion on real
  evidence.
- [x] Run E59 and record the result without tuning it.

Implementation commit: see `E59-scaled-router.json`.

Validation:

- 314 Python tests pass (186 before this work).
- All 56 committed experiment `report_digest` values reproduce exactly; zero
  mismatches. No existing experiment JSON or runner was modified.
- Ruff reports no errors across every new file.
- `verify_capsulang_evidence.py` exits 0 with `contradictions=0 assumptions=1`.

E59 result at grid size 128 (coverage 0.031 against the legacy 0.800): the
pooled paired regret delta is `−0.00453`, CI `[−0.00916, +0.00028]` —
**inconclusive, interval spans zero**. One family shows a clear real effect:
`monotone` at `−0.02372`, CI `[−0.02635, −0.02116]`. The other eight are null.
Per `POC_PLAN.md`, this null pooled result is retained as measured.

Known defect, recorded rather than patched: `plateau` was admitted (8
disagreements over 120 tasks) despite a measured effect of exactly zero.
`minimum_policy_disagreements` is an absolute count and should be a rate.
Changing it after seeing results would be the post-hoc adjustment this review
criticizes, so it is pre-registered for the next run instead.

Claim boundary: E59 is a synthetic landscape study of one exploitation rule. It
is not evidence of scaffold self-improvement or of a recursive effect. Its value
is establishing a benchmark on which such a claim could actually be tested.

## Completed — reconcile recursive research evidence on `main`

Issue: [#2 — Reconcile recursive research evidence and clean main checkout](https://github.com/advatar/NextAI/issues/2)

- [x] Audit the 69-entry checkout and separate intended research source, tests,
  documentation, experiment evidence, and the landing-page pointer from local
  archives and generated/runtime state.
- [x] Verify that NExtAI has no divergent local/remote branch or open pull
  request, and that the nested landing page is clean on its published `main`.
- [x] Review the E6–E29 implementation and immutable evidence chain for
  coherence, reproducibility, and honest claim boundaries.
- [x] Add or refine unit coverage for new archive, deterministic-selection,
  conformance, and Longemma-adapter behavior.
- [x] Exclude the downloaded Namecheap utility archive without deleting it or
  staging any credential, cache, vendor, model, or runtime artifact.
- [x] Run the complete Python test suite plus relevant syntax and evidence
  checks.
- [x] Advance the landing-page gitlink to its clean published `main`, stage
  explicit paths only, commit, and push the verified work to canonical `main`.
- [x] Close issue #2 with exact commit, validation, exclusion, and claim-boundary
  evidence.

Implementation commit: `841ac64`.

Validation:

- 173 Python unit/integration tests pass, including the Docker containment
  suite.
- Ruff reports no errors across every changed Python file, and `compileall`
  succeeds.
- All 31 committed experiment JSON files parse; all 26 reports that carry a
  `report_digest` reproduce that digest exactly.
- The landing page builds successfully and ESLint finishes with no errors
  (six existing Fast Refresh warnings).
- Eleven real-model or model-output analysis entry points fail closed unless
  the operator explicitly acknowledges host execution with
  `--unsafe-local-demo`.

Preserved local exclusions: `GEM1.md` through `GEM4.md` are unreviewed research
source drops, and `namecheap-dnsctl-v0.1.0.zip` is a downloaded utility archive.
They remain untouched locally and are ignored by exact path. No credential,
cache, vendor tree, model artifact, or runtime output was committed.

Evidence boundary: E2 and E6–E25 plus E27–E29 have committed JSON evidence. The
E26 runner and published landing-page summary were recovered, but no standalone
E26 JSON report existed in the checkout, so this reconciliation does not claim
an immutable E26 report. Real-model results remain narrow synthetic probes, not
evidence of general or recursive self-improvement.

## In progress — auditable recursive scaffold optimization POC

- [x] Review `RECURSIVE.md` and audit the preliminary starter against its claims.
- [x] Define the POC boundary, threat model, evidence standard, controls, and
  matched-budget metaproductivity experiment in `POC_PLAN.md`.
- [x] Open [issue #1](https://github.com/advatar/NextAI/issues/1) containing the
  implementation plan and acceptance criteria.
- [x] Harden the local fixture runner and replace forgeable evaluator output.
- [x] Add adversarial evaluator/sandbox regression tests and a fail-closed
  Docker candidate adapter for untrusted-code POC execution.
- [x] Add immutable typed artifacts, budgets, conjunctive promotion decisions,
  and a hash-chained audit ledger.
- [x] Freeze run identity in a durable experiment manifest and reject missing,
  altered, or configuration-drifted manifests on resume.
- [x] Dependency-inject proposer/evaluator/policy/store components and add a
  deterministic no-key replay demo.
- [x] Add staged development evaluation, paired and counterbalanced private
  parent/candidate evaluation, and explicitly authorized, query-limited sealed
  audits that close further search.
- [x] Add public/private/final split plumbing and a matched-budget
  ancestor-versus-descendant metaproductivity report.
- [x] Run the complete 149-test suite and deterministic POC demonstration.
- [x] Update README/handoff documentation with honest claims, limitations, and
  next steps.
- [x] Commit and push only files owned by this task directly to `main`.

Current claim boundary: the no-key fixture run validates laboratory mechanics
only. It does not establish bounded scaffold improvement or a recursive effect.
The next empirical milestone is a pinned live typed-strategy proposer plus
physically separated development/private/sealed manifests for a 20–30 task,
multi-family coding corpus, followed by equal-budget controls and independent
lineages.

## Completed

### Convert `REPORT.md` to polished GitHub-flavored Markdown

- [x] Assess the report structure, formatting defects, repository scope, and validation options.
- [x] Create a GitHub issue documenting the scope, acceptance criteria, and implementation plan.
- [x] Add a semantic heading hierarchy and consistent section structure.
- [x] Convert raw URLs and source references to readable Markdown links.
- [x] Replace both Unicode box-drawing tables with valid GitHub-flavored Markdown tables.
- [x] Normalize lists, emphasis, evidence labels, separators, and typographic artifacts without changing the report's claims.
- [x] Validate Markdown structure and verify that report content was preserved.
- [x] Stage only `NExtAI/REPORT.md` and `NExtAI/STATUS.md`, then commit and push the completed work.

Issue: [#9 — Polish NExtAI research report as GitHub-flavored Markdown](https://github.com/advatar/Evo2Kit/issues/9)
