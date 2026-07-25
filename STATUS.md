# Status

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
