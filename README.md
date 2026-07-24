# NextAI

Research and an implementation starter for bounded, auditable recursive
scaffold optimization.

The current result is a **deterministic laboratory proof of concept**, not
evidence of model self-improvement. It demonstrates a frozen governor, typed
strategy artifacts, staged development and paired private evaluation, durable
experiment identity and lineage, constrained candidate execution, sealed-audit
controls, and matched-budget metaproductivity reporting using synthetic
fixtures. A live strategy-editing model and a multi-family held-out task corpus
are the next empirical milestone.

- [`RECURSIVE.md`](RECURSIVE.md) — state-of-the-field research and evidence
  standard.
- [`POC_PLAN.md`](POC_PLAN.md) — detailed POC architecture, threat model,
  controls, phases, and go/no-go criteria.
- [`self-improving-starter/`](self-improving-starter/) — the implementation,
  adversarial tests, deterministic no-key demo, immutable governor, and
  metaproductivity experiment plumbing.

## Run the deterministic POC

```bash
cd self-improving-starter
python3 -m unittest discover -s tests
python3 poc.py demo --out runs/poc-demo
python3 poc.py verify-ledger \
  --ledger runs/poc-demo/lineage.jsonl \
  --anchor runs/poc-demo/ledger.head
```

The demo writes a frozen experiment manifest, hash-chained ledger, separate head
anchor, fixture-only sealed comparison, summary, and metaproductivity report.
See the starter README for the exact claim boundary, Docker requirements, and
known limitations.

## Real Gemma integration probe

With Longemma's OptiQ MLX server running against a local Gemma 4 E2B model:

```bash
PYTHONPATH=/path/to/NExtAI/self-improving-starter \
  uv run --no-dev python self-improving-starter/run_gemma_probe.py \
  --unsafe-local-demo \
  --out self-improving-starter/experiments/E14-gemma-probe.json
```

E14 produced and executed a correct `solve(n) = n + 1` proposal, with a
verified hash-chained receipt. This is an integration probe for one proposal,
not evidence of general self-improvement. The explicit flag acknowledges that
this historical probe executes model-authored Python on the host; use the
reviewed container runner or a VM for untrusted candidates.
