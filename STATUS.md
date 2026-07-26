# Status

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
