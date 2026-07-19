# RESUME — auditable recursive scaffold POC

_Updated July 19, 2026._

## Current result

The starter has moved from a forgeable object-level optimization sketch to the
first implementation pass of an **auditable recursive scaffold optimization
laboratory**.

The current demonstrated result is laboratory plumbing only:

- Typed, immutable, content-addressed strategy artifacts.
- Fixed budgets and conjunctive promotion gates.
- A canonical experiment manifest freezing the seed, proposer/evaluator and
  split-task digests, policy, budgets, artifact schema, and runtime policy;
  altered, missing, or drifted identity blocks resume.
- Development-first evaluation, followed by paired parent/candidate private
  evaluation on the same seed with counterbalanced arm order.
- Proposal/evaluation write-ahead accounting and an incremental hash-chained
  attempt/audit ledger with resume.
- Deterministic no-key fixture proposer/evaluator covering three accepted
  generations, duplicate rejection, unsafe-strategy rejection, and proposer
  failure.
- Matched-budget ancestor/descendant metaproductivity report with a paired
  bootstrap interval.
- Explicitly authorized, one-shot, query-limited sealed audits that close
  further search after use.
- Hardened local trusted-fixture runner and a Docker untrusted-code adapter.
- Adversarial tests for the known reward-forgery, non-finite, early-exit,
  hard-coded-case, timeout, process cleanup, output-limit, network, non-root, and
  read-only-filesystem paths.

The fixture's passing metaproductivity threshold is synthetic. It validates the
report path; it is not evidence of model RSI.

## Start here

```bash
cd self-improving-starter
python3 -m unittest discover -s tests
python3 poc.py demo --out runs/poc-demo
python3 poc.py verify-ledger \
  --ledger runs/poc-demo/lineage.jsonl \
  --anchor runs/poc-demo/ledger.head
```

The output includes `experiment-manifest.json`, `lineage.jsonl`, `ledger.head`,
`summary.json`, and `metaproductivity.json`. A completed demo has already used
its two sealed baseline/champion audits and cannot be extended with more search;
`--resume` is only meaningful for an interrupted pre-sealed run with its
manifest and trusted head anchor intact.

Resume requires an exact anchor match by default. If inspection confirms that
the ledger contains a legitimate fully verified suffix written just before an
anchor-update crash, `--recover-unanchored-tail` is the explicit operator
recovery path.

`--rounds` means the target total number of attempts, not additional attempts,
so recovery cannot silently repeat an already completed search segment.

Read `../POC_PLAN.md` for the full architecture, threat model, controls, success
criteria, and phased roadmap.

## Important boundaries

- `sandbox.py` is for trusted fixtures only; it is not a security sandbox.
- `container_runner.py` is the POC candidate plane. It uses a locally present
  image by resolved image ID and applies non-root/no-network/read-only/capability
  and resource controls. Production still needs reviewed image/runtime pinning
  and preferably a stronger VM or dedicated seccomp policy.
- The container adapter is exercised by the legacy toy environment and its own
  adversarial tests; it is not yet connected to a live strategy-conditioned
  coding-task evaluator.
- The deterministic proposer runs as trusted Python beside the governor. The
  split API withholds private details, but physical process/data separation from
  a hostile live proposer is still a next-milestone requirement.
- `run.py` is the legacy object-level solution optimizer. It does not edit or
  evaluate the improver.
- `rl/` is not ready to train. It lacks a real isolated reward service,
  task-level train/validation separation, and verified completion export.

## Next implementation milestone

1. Build 20–30 small Python repair/program-synthesis fixtures across independent
   task families.
2. Keep development, private selection, and sealed OOD manifests physically
   separate from the candidate plane.
3. Add a pinned model adapter that can only propose typed strategy JSON, plus a
   fixed coding-agent adapter that actually applies each strategy to the task
   corpus under the container boundary.
4. Run at least five independent lineages plus unchanged, equal-budget best-of-N,
   and neutral-mutation controls.
5. Require at least three accepted generations with positive private and sealed
   transfer and no failed safety/integrity/resource gate.
6. Run the matched-budget ancestor-versus-descendant tournament on the sealed
   suite and report pass, fail, or inconclusive.

Only after that should the lab connect to Longemma/Kline realistic coding
evaluation. GRPO or other weight updates remain a later stage after evaluator
isolation and trajectory integrity are independently convincing.

## Known limitations to preserve honestly

- The current evaluator/proposer used by `poc.py demo` is synthetic.
- Fixture utilities are direct keyword-feature scores; no model currently acts
  under the evolved strategy to solve a task.
- The current governed orchestrator follows one promoted lineage; diverse
  Pareto/archive selection is not implemented yet.
- The fixture metaproductivity report is separate from the lineage manifest and
  ledger; a live tournament must predeclare and bind its protocol and evidence.
- The tournament requires at least five distinct seed artifacts and unique
  random seeds; its validity, safety, and integrity decisions come from the
  injected external evaluator rather than the improver result. The report also
  records seed artifact IDs and the bootstrap seed/sample count.
- A hash chain detects edits/reordering/internal deletion. Detecting deletion of
  a complete tail requires retaining `ledger.head` outside the ledger; the demo
  writes that anchor beside it for convenience, not production-grade separation.
- Docker containment reduces risk but is not a formal isolation proof.
- The toy speed environment has a one-line ceiling and is only a smoke test.
