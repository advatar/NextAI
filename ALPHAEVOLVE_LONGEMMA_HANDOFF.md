# AlphaEvolve ↔ Longemma integration handoff

## Goal

Reuse NExtAI's AlphaEvolve-style orchestration with Longemma's local Gemma
backend. Keep model inference, evolutionary search, and evaluation as separate
auditable boundaries.

## Ownership split

- **Longemma** owns Gemma inference, backend selection, runtime policy, and model
  usage receipts.
- **NExtAI** owns evolutionary search, the program database, archive selection,
  budgets, and promotion.
- **The evaluator** remains independent of the model adapter and owns decisive
  correctness evidence.

The reusable engine is:

`self-improving-starter/recursive_lab/alphaevolve.py`

Its main entry point is `evolve_programs(...)`. Do not copy Longemma's agent loop
into NExtAI. Add a thin `ProgramProposer` adapter instead.

## Proposer adapter

The adapter should satisfy this shape:

```python
class LongemmaProposer:
    name = "gemma-4-local"

    def __init__(self, backend, task_prompt):
        self.backend = backend
        self.task_prompt = task_prompt

    def propose(self, sample, rng):
        messages = render_alphaevolve_prompt(
            task=self.task_prompt,
            parent=sample.parent.candidate,
            inspirations=[item.candidate for item in sample.inspirations],
            feedback=sample.feedback,
        )

        response = self.backend.generate(
            messages,
            temperature=0.7,
            top_p=0.95,
            seed=rng.randrange(2**63),
            max_tokens=4096,
        )

        return parse_complete_program(response.text)
```

The adapter receives a parent program, inspiration programs, and public
evaluator feedback. It returns one complete candidate program. It must not see
hidden tests, private promotion evidence, credentials, or evaluator internals.

Model-authored programs are untrusted. The historical local-Gemma experiments
require an explicit `--unsafe-local-demo` acknowledgement when they execute on
the host, but that switch is not an isolation boundary. New empirical runs
should use the reviewed container runner or a VM and keep private evaluation
outside the proposer process.

## Required receipts

Persist one receipt for every proposer call, including failures and retries:

- model name and backend name;
- backend implementation version;
- generation seed;
- prompt and response digests;
- prompt, completion, and total token counts;
- latency;
- parser status and failure detail;
- candidate/program digest.

An unmetered or unparseable model call must be charged and must not silently
enter the archive.

## Local backend path

Use Longemma's backend protocol as the seam:

`../Longemma/src/gemma_agent_lab/backends/base.py`

The OpenAI-compatible local backend is the simplest integration path:

`../Longemma/src/gemma_agent_lab/backends/openai_compatible.py`

The local Gemma runtime and validated model information are documented in:

`../Longemma/STATUS.md`

Start with Longemma's deterministic mock backend and then use the local MLX
endpoint configured around `127.0.0.1:12345`. SwiftLM is a useful macOS/runtime
control plane, but it should not be a direct dependency of the evolution engine.

## Verification sequence

1. Instantiate `LongemmaProposer` with Longemma's mock backend.
2. Assert deterministic prompt rendering and complete-program parsing.
3. Run a tiny one-task `evolve_programs` cohort.
4. Verify exact proposal, model-call, token, and task-evaluation budgets.
5. Verify every `ProgramRecord` has parent/inspiration IDs and receipts.
6. Repeat against the local Gemma endpoint with a small fixture cohort.
7. Only then run the three-task benchmark or a held-out coding suite.

Suggested Longemma smoke commands:

```bash
cd ../Longemma
uv run gemma-lab run --config configs/mock.yaml --mode baseline
uv run gemma-lab run --config configs/mock.yaml --mode best-of-n
uv run gemma-lab run --config configs/mock.yaml --mode self-fusion
```

## Licensing and evidence boundary

Do not use hosted-model outputs as Gemma training data without explicit provider
permission. A local Gemma run is a separate experiment from the deterministic
E6–E12 reports and must preserve its own manifest, receipts, evaluator digest,
and report. Do not describe a successful local pilot as recursive
self-improvement without a matched ancestor/descendant improver tournament.
