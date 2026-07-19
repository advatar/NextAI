# Auditable Recursive Scaffold Optimization — Proof-of-Concept Plan

## Decision

Build a bounded, auditable scaffold-optimization laboratory, not an "intelligence
explosion" demo. The first proof of concept will keep model weights, evaluators,
budgets, permissions, and the acceptance policy immutable. It will initially let
the system persistently change only a typed strategy document used by a coding
agent. A later experiment will test whether an evolved strategy is better than
its ancestor at producing another improved strategy under an identical budget.

This separates two claims that the current starter conflates:

1. **Persistent scaffold improvement:** a descendant performs better on held-out
   tasks under the same resource budget.
2. **Recursive effect:** a descendant produces better further descendants per
   unit cost than its ancestor.

The second claim requires a matched-budget metaproductivity experiment. A rising
task score alone establishes only search or bounded adaptation.

## Why this is the right POC

`RECURSIVE.md` identifies scaffold evolution as the highest-leverage near-term
layer: it is cheaper, more inspectable, and easier to roll back than weight
training. It also identifies evaluator integrity as the central technical and
safety problem. The existing starter already has the outline of a proposal,
evaluation, and archive loop, so hardening and generalizing that loop is more
useful than adding GRPO now.

The preliminary implementation was a loop-mechanics sketch, not a trustworthy
RSI experiment:

- The candidate and evaluator harness execute in one Python process. A candidate
  can print a forged `OK MEDIAN` line and exit successfully without defining the
  requested function.
- The fixed timing calibration is noisy enough that an unchanged baseline can
  appear to improve or add novelty.
- The subprocess inherits host filesystem, environment, network, and process
  privileges. Changing its working directory is not sandboxing.
- Acceptance does not explicitly require correctness, evaluator integrity,
  safety, and budget compliance.
- The loop mutates a task solution while its proposer, strategy, evaluator, and
  search policy remain fixed.
- The archive is not an append-only, reproducible experiment ledger.
- The RL configuration trains and validates on the same file, and archive
  trajectories are not actually exported as training completions.

These were the Phase-0 blockers found in the preliminary starter. The current
build fixes or isolates the locally testable cases, but that does not authorize
a live model-driven experiment by itself.

## Implementation status — July 19, 2026

The repository now contains the first laboratory implementation of this plan:

- **Phase 0 substrate:** the toy evaluator no longer trusts candidate-authored
  status or timing text, rejects non-finite and malformed results, checks
  deterministic hidden cases externally, and defaults untrusted execution to a
  fail-closed Docker adapter. The host subprocess runner is explicitly limited
  to trusted fixtures. Adversarial tests cover forgery, early exit, imports,
  hard-coded visible cases, timeouts, excessive output, process cleanup,
  network denial, non-root execution, and a read-only container filesystem.
- **Phase 1 governor:** typed immutable strategy artifacts, strict budget
  accounting, conjunctive gates, proposal/evaluation write-ahead stages, a
  hash-chained JSONL ledger, and resume reconstruction are implemented. A
  canonical experiment manifest freezes the seed, proposer/evaluator digests,
  acceptance policy, budgets, all three task-manifest digests, mutable schema,
  and candidate-runtime policy; resume fails closed on missing, altered, or
  drifted identity.
- **Phase 2 mechanics:** a dependency-injected, single-lineage fixture loop
  stages development evaluation before private queries, compares candidate and
  parent on the same private seed with counterbalanced execution order, and
  demonstrates three persistent accepted generations. Sealed audits require
  explicit milestone authorization, are one-shot per artifact, have a frozen
  total query cap, are ledgered, and close further search.
- **Phase 3 reporting plumbing:** the deterministic POC emits a matched-budget
  ancestor/descendant metaproductivity report over distinct paired seeds, with
  independent evaluator gates and full improver/evaluation cost vectors, plus
  a fixture-only sealed comparison.

What is **not** implemented is equally important: there is no live
strategy-editing model adapter, no multi-family development/private/sealed task
corpus, no independent-lineage or best-of-N/neutral-mutation control run, and no
empirical metaproductivity evidence. Synthetic fixture gains validate software
paths only; they do not establish bounded scaffold improvement or recursion.

## System boundary

Represent a version as:

```text
S = (model_ref, strategy, memory_policy, tools_ref, evaluator_ref, search_policy)
```

### Mutable in the first live experiment

- `strategy`: a size-bounded, schema-validated planning and tool-use strategy.
- Later, after the typed strategy experiment passes: allowlisted prompt and
  routing files in a candidate scaffold tree.

### Immutable and outside the candidate plane

- Model identity, provider configuration, and weights.
- Governor and promotion policy.
- Development/private/final task manifests and all expected outputs.
- Sandbox implementation and permission policy.
- Resource counters and query limits.
- Audit ledger, artifact store, deployment controls, and rollback pointers.
- The mechanism that computes decisive evaluation results.

The candidate may propose a change to the mutable artifact. It may never write
directly to accepted state.

## Target architecture

```text
Immutable governor
  ├─ typed proposal validator
  ├─ fixed budget + query accounting
  ├─ public/private/final task split registry
  ├─ external correctness and safety evaluators
  ├─ conjunctive acceptance policy
  └─ hash-chained event ledger
             │
             ▼
Mutable strategy S_t ── proposes ──> candidate strategy S_t+1
             │                           │
             └──────── fixed model ──────┘
                                         │
                                         ▼
                              isolated candidate worker
                                         │ untrusted output
                                         ▼
                              external staged evaluation
                                         │
                                accept / reject / archive
```

The same orchestration must run in two modes:

- **Deterministic replay mode (implemented):** no API key; the demo exercises
  accepted generations, duplicate and unsafe-artifact rejection, and proposer
  failure. The surrounding test suite exercises malformed output, timeouts,
  resource limits, evaluator failure, manifest drift, and budget exhaustion.
- **Live mode (not yet implemented):** a pinned model proposes strategy changes;
  raw request/response digests, provider request identifiers, model versions,
  token counts, and costs must be recorded.

Replay mode validates the laboratory. Live mode supplies empirical evidence.

## Core data model

### Strategy artifact

A content-addressed immutable record containing:

- Schema version and artifact kind.
- Canonical strategy payload.
- SHA-256 artifact identifier.
- Parent artifact identifier and generation.
- Proposer/model configuration digest.
- Creation seed and proposal metadata.

The implemented v1 strategy schema exposes these bounded, reviewable fields:

- system instruction;
- ordered planning steps;
- maximum attempts;
- reflection/checklist instructions.

Candidate-count limits and typed tool-selection hints may be added in a later
schema revision after the narrower artifact is exercised empirically.

Arbitrary code, imports, dependencies, evaluator paths, permissions, and shell
commands are not part of the v1 mutable schema.

### Experiment manifest

Before the first ledger event, persist a canonical, content-hashed manifest that
freezes the run seed, proposer and evaluator identities/digests, acceptance
policy, budget limits, development/private/sealed task-manifest digests, mutable
artifact schema, and candidate-runtime policy. Every ledger event binds to this
manifest hash. Resume must refuse a missing manifest, a hash mismatch,
non-canonical content, symlinks, or any requested configuration drift.

### Evaluation record

Record public diagnostics separately from private promotion evidence:

- Artifact and evaluator version/hash.
- Task-set identifier and split.
- Per-task pass/fail and externally measured resource use.
- Model calls, input/output tokens, wall time, CPU time, and monetary cost when
  available.
- Typed usage receipts for provider/evaluator failures; a missing receipt closes
  the lineage as accounting-incomplete.
- Correctness, safety, evaluator-integrity, and budget-gate results.
- Utility estimate and uncertainty.
- Private evidence remains in the governor-owned audit plane. The proposer sees
  development feedback and the accepted parent state, not private per-task
  details. Sealed-final results are never used during search.

### Audit event

Every proposal attempt—including proposer errors and duplicates—creates an
append-only event with:

- event sequence, timestamp, type, and schema version;
- parent and candidate artifact hashes;
- canonical payload hash;
- gate outcomes and rejection reasons;
- previous-event hash and current-event hash.

This makes deletion or mutation of an earlier event detectable. Content hashes
provide lineage and deduplication; they are not a substitute for signatures or
an external append-only store in a production system.

The implemented deterministic ledger provides sequence/hash chaining,
manifest binding, durable appends, write-ahead stage events, and optional head
verification. It does not yet include or authenticate a wall-clock timestamp,
provide signatures or an off-machine transparency log, maintain an atomic
deployed-champion pointer, or expose a rollback command. The demo stores
`ledger.head` beside the ledger for convenience; a production verifier must
retain the trusted head independently to detect valid tail truncation.

## Evaluation protocol

### Task splits

1. **Development:** public tests and useful failure diagnostics. Used while a
   proposal is formed.
2. **Private selection:** external hidden tests used for promotion. Query count
   is limited because repeated accept/reject bits leak information.
3. **Sealed final/OOD:** untouched during evolution and run only for milestone
   comparison.

The implemented fixture governor evaluates development first and does not spend
a private query when a development gate fails. For a candidate that reaches
private selection, it evaluates the current parent and candidate on the same
task manifest and seed, counterbalancing arm order by attempt. The sealed API
requires an explicit milestone flag, permits each artifact once, defaults to
two total audit queries for the baseline/champion comparison, and permanently
closes that lineage to further search. These are protocol mechanics, not a
substitute for the live multi-task statistical design below.

The first live benchmark should contain roughly 20–30 small, deterministic
Python repair/program-synthesis tasks across several independent families. The
current closed-form speed toy remains only a smoke test.

### Primary task metric

Use paired held-out task success under a fixed number of model calls and output
tokens. Report per-task results and a paired confidence interval. Do not promote
on a single noisy scalar run.

If a performance task is retained, compare parent and candidate in randomized,
interleaved trials and use a paired log-speed ratio with an uncertainty bound.
Never compare against one stale calibration.

### Conjunctive acceptance

Promotion is:

```text
capability_gain
AND correctness_preserved
AND safety_preserved
AND evaluator_integrity
AND resource_compliance
AND artifact_valid
```

A capability score cannot compensate numerically for a failed safety or
integrity gate. Non-finite metrics fail closed. Duplicate artifacts are logged
but not re-evaluated or promoted.

### Controls

- Unchanged ancestor with the same total model-call/token budget.
- Fixed-strategy best-of-N with the same total budget.
- Neutral or random valid strategy mutation.
- Multiple independent lineages and seeds.

These controls distinguish a recursive mechanism from simply buying more
samples or harvesting easy improvements.

## Metaproductivity experiment

For ancestor `A` and accepted descendant `D`:

1. Give both the same unseen seed strategy `X`, task feedback, model, tools,
   random seeds, proposal count, token allowance, and wall-clock budget.
2. Let each produce candidate successors of `X`.
3. Evaluate those successors once on private and sealed OOD tasks.
4. Repeat across matched seeds and task samples.
5. Compare descendant uplift per complete proposal-and-evaluation cost:

   ```text
   M(P) = [U(best successor produced by P) - U(X)] / total cost(P)
   ```

6. Report utility and each cost component separately so a composite metric does
   not hide trade-offs.
7. Ablate material strategy changes to identify which changes caused the effect.

The recursive-effect claim passes only if `M(D) - M(A)` exceeds a predeclared
effect size with a paired 95% confidence interval excluding zero, without safety
regression or additional budget. Faster arrival at the same plateau is reported
as efficiency improvement, not a higher asymptotic ceiling.

## Threat model and Phase-0 adversarial suite

Candidate output is untrusted data. Before any live proposer or RL execution,
the runner/evaluator must fail closed on:

- forged success/timing text;
- early `SystemExit` and `os._exit`;
- test or evaluator source discovery;
- import-hook or timing-module monkeypatching;
- hard-coded visible cases failing randomized hidden cases;
- environment/credential and absolute host-path reads;
- network attempts;
- child/background processes;
- infinite loops, memory exhaustion, and excessive output;
- symlink/path traversal;
- malformed, truncated, duplicate, and non-finite results;
- timeout after partial output.

The target candidate runtime is a disposable rootless container with no network,
a read-only root filesystem, sanitized environment, non-root UID, no Linux
capabilities, `no-new-privileges`, and explicit wall/CPU/RSS/PID/file/output
limits. On systems without a supported container runtime, the CLI must refuse
live untrusted execution or require an explicit `--unsafe-local-demo` flag. A
host subprocess is permitted only for deterministic trusted fixtures.

## Phased implementation

### Phase 0 — trustworthy substrate

- Add tests before changing behavior.
- Fix timeout decoding and process-group cleanup in the local runner.
- Bound output and sanitize the child environment.
- Replace candidate-authored timing/status parsing with an external result
  protocol and external correctness decisions.
- Reject non-finite/unbounded rewards and make all acceptance gates explicit.
- Add a container-runner interface and fail-closed capability detection.
- Add every adversarial fixture that is feasible locally; mark container-only
  containment tests separately.

Exit criterion: all local adversarial tests fail closed with no evaluator crash,
and live mode cannot accidentally use the local fixture runner.

### Phase 1 — immutable governor and durable lineage

- Introduce dependency-injected proposer, evaluator, acceptance, selection,
  budget, clock, and event-store interfaces.
- Add typed artifacts, content hashing, deduplication, and source/behavior
  fingerprints.
- Write every attempt incrementally to a hash-chained JSONL ledger.
- Add archive load/resume, atomic champion pointer updates, and rollback.
- Count all evaluated attempts—not only accepted children—against exploration
  and resource budgets.

Exit criterion: identical replay inputs produce byte-equivalent semantic event
streams and archives, and tampering with a ledger event is detected.

### Phase 2 — bounded scaffold evolution

- Add the v1 typed strategy schema and patch validator.
- Add deterministic fixture and optional pinned-model proposers.
- Build the multi-family development/private/final task suite.
- Persist at least three accepted generations across multiple lineages.
- Run unchanged, best-of-N, and neutral-mutation controls.

Exit criterion: a descendant shows a positive paired hidden-task gain under the
same budget, with no failed conjunctive gate and positive sealed-OOD transfer.
This establishes bounded persistent scaffold improvement only.

### Phase 3 — recursive-effect measurement

- Implement matched-budget ancestor-versus-descendant improver tournaments.
- Include proposal failures and evaluation overhead in cost.
- Add repeated seeds, paired intervals, and causal ablations.
- Produce a machine-readable report that states pass, fail, or inconclusive.

Exit criterion: the predeclared metaproductivity threshold passes. A null result
is retained and reported rather than optimized away.

### Phase 4 — realistic coding environments

- Connect the governor to Longemma's isolated workspaces, visible/hidden checks,
  SWE-bench/SWE-Gym harness, and trajectory export rather than copying its whole
  implementation.
- Port only the relevant Kline reward-hacking and forbidden-path rules into the
  candidate validator, with attribution and tests.
- Add benchmark rotation and contamination tracking.

Exit criterion: local fixture results reproduce on a realistic held-out coding
suite without evaluator leakage or unexplained cost drift.

### Phase 5 — optional weight updates

- Replace the placeholder archive export with a versioned verified-trajectory
  schema and genuinely disjoint train/validation tasks.
- Run rollout code in an isolated evaluation service, never in a credentialed
  trainer process.
- Begin with rejection sampling/SFT; add GRPO only after reward reproducibility,
  concurrency, quota, and malicious-rollout tests pass.
- Keep fresh external data mixed with verified synthetic data.

Exit criterion: a trained checkpoint improves held-out tasks and does not weaken
the scaffold-level safety/integrity gates. Weight updates are evaluated
separately so gains remain attributable.

## Initial deliverable in this build

This implementation pass delivers the Phase-0/Phase-1 substrate and
deterministic Phase-2/Phase-3 protocol plumbing:

- a detailed experimental specification (this document);
- a hardened local fixture runner with bounded, structured results;
- adversarial tests for the known evaluator and timeout failures;
- typed immutable artifacts, budget accounting, conjunctive decisions, and a
  tamper-evident event ledger;
- a durable frozen experiment manifest with fail-closed resume verification;
- dependency-injected loop mechanics and a deterministic no-key demonstration;
- paired parent/candidate private evaluation and explicitly authorized,
  query-limited sealed audits;
- a first matched-budget metaproductivity report API/CLI, clearly labeled as
  plumbing validation until exercised by a live model and sealed task suite.

## Go/no-go criteria

Before a live model may self-edit a strategy:

- 100% of the Phase-0 adversarial fixtures fail closed.
- There are no evaluator crashes, leaked secrets/tests, or surviving processes.
- Repeated no-op candidates have a false-promotion rate below 1%.
- Every attempted proposal has complete lineage and cost accounting.
- Search has no access to the sealed-final suite.
- The unchanged equal-budget control is runnable from the same CLI.

Before making a recursive-effect claim:

- At least three accepted generations and five independent lineages exist.
- The evolved improver beats the equal-budget ancestor on descendant
  gain-per-cost with the predeclared effect size and paired interval.
- The result transfers to the sealed OOD suite.
- It is not explained by leaked evaluator data, extra resources, a relaxed gate,
  or direct task-solving ability alone.
- A material accepted change survives causal ablation.

Anything weaker is reported as an engineering milestone, bounded scaffold
improvement, or an inconclusive/null metaproductivity result—not open-ended RSI.
