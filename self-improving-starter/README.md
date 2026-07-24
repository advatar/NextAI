# self-improving-starter

An early proof of concept for **auditable recursive scaffold optimization**. It
is deliberately bounded: model weights, evaluation, budgets, permissions, and
promotion remain outside the mutable system. The first mutable artifact is a
small, typed strategy—not arbitrary governor or evaluator code.

The project distinguishes three very different results:

1. **Laboratory validation:** deterministic fixtures prove that the governor,
   gates, budgets, persistence, and reports behave as designed.
2. **Bounded scaffold improvement:** a live descendant strategy performs better
   on held-out tasks under the same budget.
3. **Recursive effect:** a descendant produces better *further descendants* per
   unit cost than its ancestor in a matched-budget experiment.

Only the first result is implemented and demonstrated locally today. Fixture
scores are synthetic and are never evidence of model self-improvement or RSI.
The full design and go/no-go criteria are in
[`../POC_PLAN.md`](../POC_PLAN.md).

## What is built

### Immutable governance plane

- `recursive_lab/artifacts.py` — frozen, schema-validated strategy artifacts,
  conservative forbidden-content rules, canonical JSON, and content hashes.
- `recursive_lab/governance.py` — fixed resource budgets and conjunctive
  capability/correctness/safety/integrity/resource promotion gates.
- `recursive_lab/manifest.py` — a canonical, content-hashed experiment identity
  that freezes the run seed, component and task-manifest digests, policy,
  budgets, mutable schema, and runtime policy. Resume fails closed if it is
  missing, altered, or different from the requested configuration.
- `recursive_lab/ledger.py` — incrementally durable, hash-chained JSONL lineage
  with external-head verification for rollback/tail-truncation detection.
- `recursive_lab/lab.py` — dependency-injected proposer/evaluator loop,
  proposal/evaluation write-ahead accounting, public versus private feedback
  separation, paired parent/candidate private evaluation on the same seed,
  conjunctive promotion, controlled sealed audits, and resume.
- `recursive_lab/metaproductivity.py` — paired ancestor/descendant tournament
  with at least five distinct seed artifacts and random seeds, externally
  evaluated gates, complete per-arm cost vectors, a bootstrap interval, and
  explicit pass/fail/inconclusive/invalid output.
- `recursive_lab/live.py` — opt-in pinned Anthropic proposer and immutable JSON
  task-corpus evaluator. The proposer is metered and digest-bound; the evaluator
  never receives private promotion evidence or model credentials.

### Candidate execution boundaries

- `sandbox.py` — a bounded local runner for **trusted deterministic fixtures
  only**. It sanitizes the environment, caps output, applies a wall timeout, and
  kills the process group, but it is not a security sandbox.
- `container_runner.py` — the untrusted-code POC adapter. It uses a pre-existing
  Docker image by resolved image ID, non-root UID, no network, read-only root,
  no capabilities, `no-new-privileges`, a read-only candidate mount, ephemeral
  tmpfs, and CPU/memory/PID/file/output/time limits. A production deployment
  still needs a reviewed pinned image/runtime and preferably a stronger VM or
  purpose-built seccomp boundary.

### Deterministic demonstration

- `poc.py demo` exercises three persistent accepted generations plus duplicate,
  unsafe-schema, and proposer-error rejection paths.
- It evaluates development first, then compares parent and candidate on a shared
  private seed with counterbalanced arm order. The proposer API receives no
  private evaluation details.
- It writes a frozen experiment manifest, append-only lineage, external head
  anchor, sealed fixture comparison, and matched-budget metaproductivity fixture
  report.
- `poc.py verify-ledger` verifies the complete chain against the saved head.

### Legacy object-level smoke loop

The original `run.py` → `dgm_loop.py` path still evolves a single `solve(n)`
answer. It is useful for testing select/propose/evaluate/archive mechanics, but
it does **not** improve the improver and cannot demonstrate recursion.

The toy evaluator now rejects forged status lines, early exit, imports,
introspection, non-finite metrics, and fixed visible-case tricks. It externally
checks deterministic randomized cases and treats the exact baseline as reward
zero. Timing remains a smoke metric, not promotion-grade evidence.

## Run the no-key POC

```bash
cd self-improving-starter
python3 -m unittest discover -s tests
python3 poc.py demo --out runs/poc-demo
python3 poc.py verify-ledger \
  --ledger runs/poc-demo/lineage.jsonl \
  --anchor runs/poc-demo/ledger.head
```

Run the deterministic three-task search-policy comparison with identical
proposal and task-evaluation budgets for greedy, uniform random-mutation, and
quality-diversity archive selection:

```bash
python3 compare_selection.py --proposals 12 --seeds 5 \
  --out runs/selection-comparison.json
```

The JSON report includes every trajectory, per-policy aggregates, the benchmark
manifest digest, explicit budget counts, and a report digest. Correctness is
execution-verified; fixed baseline/improved/broken quality tiers avoid using
local timing noise as policy evidence, and identical task variants are cached
across arms. It compares object-level search policies on three small fixtures;
it is not evidence of recursive self-improvement.

The follow-up budget-scaling ablation reuses exact prefixes from one maximum-
budget trajectory per policy and seed:

```bash
python3 compare_budget_scaling.py --budgets 3,6,12,24 --seeds 20 \
  --out experiments/E7-budget-scaling.json
```

Diagnose whether QD results depend on the archive discretization:

```bash
python3 compare_qd_resolution.py --proposals 24 --seeds 50 \
  --out experiments/E8-qd-resolution-ablation.json
```

Test a full local AlphaEvolve-style architecture without depending on the older
BetaEvolve codebase: program database, parent/inspiration sampling, explorer and
exploiter proposer roles, whole-program candidates, external multi-metric
evaluation, and evolutionary readmission under matched budgets:

```bash
python3 compare_recombination.py --proposals 24 --seeds 50 \
  --out experiments/E9-alphaevolve-local.json
```

Verify NExtAI against BetaEvolve's exact shared Swift/Python archive contract,
then test search policies on a deliberately deceptive landscape:

```bash
python3 verify_e10_conformance.py \
  --out experiments/E10-three-way-archive-conformance.json
python3 compare_deceptive_search.py --proposals 100 --seeds 100 \
  --out experiments/E11-deceptive-search.json
```

Reproduce the effect with a 1,000-seed cohort and paired bootstrap intervals:

```bash
python3 compare_deceptive_search.py --proposals 100 --seeds 1000 \
  --out experiments/E12-deceptive-cohort.json
python3 analyze_deceptive_evidence.py experiments/E12-deceptive-cohort.json \
  --bootstrap 20000 --out experiments/E12-deceptive-evidence.json
```

Run the Longemma-compatible proposer smoke and record local Gemma availability:

```bash
python3 run_longemma_smoke.py
```

With Longemma's OptiQ MLX server running, run one real Gemma proposal:

```bash
PYTHONPATH=/path/to/NExtAI/self-improving-starter \
  uv run --no-dev python run_gemma_probe.py \
  --unsafe-local-demo \
  --out /path/to/NExtAI/self-improving-starter/experiments/E14-gemma-probe.json
```

The real-model E12 and E14–E29 scripts that evaluate generated Python refuse
host execution unless `--unsafe-local-demo` is supplied. That flag records an
operator decision; it does not create a sandbox. Prefer the reviewed container
runner or a VM for untrusted candidates. The committed JSON reports are
historical evidence with valid content digests, not proof that host execution
is safe.

Expected demo shape:

```text
Deterministic POC plumbing validation complete.
Accepted generations: 3
Attempts logged: 6
...
Fixture metaproductivity verdict: passes_threshold (not empirical RSI evidence)
```

The Docker containment tests run when the reviewed local
`python:3.12-slim` image is already present. Tests skip rather than pulling an
unreviewed mutable image automatically.

The output directory also contains `experiment-manifest.json`, `summary.json`,
and `metaproductivity.json`. The manifest is immutable experiment identity, not
a mutable run configuration: changing the seed, proposer/evaluator digests,
policy, budgets, split manifests, artifact schema, or sealed-query policy causes
resume to fail. A completed demo has consumed its sealed baseline/champion
queries and closed search; `--resume` is for a genuinely interrupted pre-sealed
run, not for extending a completed demonstration. `--rounds` is a total target,
so resuming a two-attempt lineage with `--rounds 6` runs four more attempts.

Normal resume requires `ledger.head` to match the verified ledger exactly. If a
process died after ledger `fsync` but before its head-anchor update, inspect the
extra suffix first and then use the explicit `--recover-unanchored-tail` flag;
the CLI never trusts and advances a stale anchor silently.

## Optional legacy model-backed smoke run

This path still asks an Anthropic model to optimize the toy `solve(n)` function:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
python3 run.py --rounds 15 --env optimize_function
```

It is an object-level optimization experiment. Do not describe a rising score
from this command as recursive self-improvement. The command also refuses to
fall back to host execution: the reviewed `python:3.12-slim` candidate image
must already be present locally.

## Evidence and safety rules

Promotion is a conjunction:

```text
artifact valid
AND capability gain above the declared margin
AND correctness preserved
AND safety preserved
AND evaluator integrity preserved
AND resource budget respected
```

A large score cannot compensate for a failed gate. Every attempted proposal,
including duplicates, invalid artifacts, and proposer failures, consumes budget
and enters the ledger. Evaluations are reserved and stage-logged before the
evaluator call, so a failed call is still charged and visible after resume.
Provider adapters report model calls and tokens on failures through a typed
usage receipt; if an adapter fails without one, the lineage is marked
accounting-incomplete and further search closes rather than silently
undercounting work.
Private details are stored only in the governor-owned audit plane; the next
proposal receives development feedback only. The sealed split requires explicit
milestone authorization, is one-shot per artifact, defaults to two total audit
queries, and closes further search once consumed. A failed sealed call still
consumes its query, records its seed and failure digest, and closes search. Its
evaluation cost is also logged.

## Live adapter status

The live adapter is now protocol-complete but deliberately not run by the test
suite. Select it only with a pinned model, an operator-owned task corpus, and a
separate evaluator process or service in production. A real run must preserve
the raw response digest, provider request ID, model version, token receipt, and
the corpus manifest digest before any promotion decision is considered empirical.

### Local credentials and corpus

Put local credentials in `self-improving-starter/.env` (copied from
`.env.example`). This file is intentionally ignored and must never be committed.
Run commands from `self-improving-starter` after exporting the variables, or
load the file with your shell's dotenv tool. The reviewed starter corpus is at
`self-improving-starter/corpus/strategy_tasks.json`; it is immutable evaluator
input and currently validates strategy-planning behavior, not general coding
ability.

## What is intentionally not ready

- There is no strategy-conditioned coding agent or 20–30 task coding corpus
  yet. The new live adapter proposes typed strategies and scores an immutable
  phrase corpus, but that corpus is an integration harness, not evidence of
  general coding improvement.
- The Docker adapter hardens the legacy toy candidate boundary and is tested in
  isolation; it is not yet wired to a live recursive-lab coding-task harness.
- The deterministic proposer is trusted Python in the governor process. Private
  and sealed separation is an API/protocol boundary today, not a hardened
  process boundary against a malicious proposer; the live adapter must enforce
  that separation outside the candidate plane.
- One lineage is promoted greedily in the current orchestrator; Pareto/archive
  selection across several live lineages is a later milestone.
- The sealed report has statistical plumbing, but no empirical runs or claims.
- The separate fixture metaproductivity tournament writes its own report; its
  protocol configuration and evidence are not yet bound into the lineage
  experiment manifest or ledger.
- The GRPO files under `rl/` remain a historical skeleton. They do not yet have
  disjoint task-level train/validation data, a real verified-trajectory export,
  or an isolated reward service. Do not run model-authored code in a
  credentialed trainer process.
- Longemma and Kline integration is deferred until the local trust seams remain
  green under adversarial testing.

## Next empirical milestone

1. Build 20–30 deterministic local Python repair tasks across independent
   families with physically separated development, private-selection, and
   sealed-OOD manifests.
2. Add a pinned model adapter that both proposes typed `StrategyArtifact` JSON
   and runs the fixed coding agent under that strategy, recording raw response
   identity, tokens, calls, wall/CPU time, and monetary cost.
3. Run at least five independent lineages and three accepted generations.
4. Compare against unchanged, fixed-strategy best-of-N, and neutral-mutation
   controls under equal total budgets.
5. Run the ancestor-versus-descendant tournament once on sealed tasks and report
   the result as pass, fail, or inconclusive.

Only a repeatable improvement in descendant gain-per-cost supports a bounded
recursive-effect claim. Better direct task performance alone supports a bounded
scaffold-improvement claim.
