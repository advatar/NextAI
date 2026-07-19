 How can I fine tune an LLM to be better at creating a new self imroving AI?

Good question, and it connects directly to the RSI thread in the report. The most important thing to get right up front: "better at creating self-improving AI" is not mainly a fine-tuning problem — it's an AI-R&D-engineering capability problem plus a self-modification loop. The single biggest recent gain in this exact area (Sakana's Darwin Gödel Machine, 20%→50% on SWE-bench) came from evolving the agent scaffold, not from touching the weights. So fine-tuning is one lever, and often not the highest-ROI one. Here's how I'd think about both.

What the capability actually decomposes into

Three sub-skills, in rough order of how much they bottleneck "building a self-improving AI":

1. ML research engineering — implement architectures, write training loops and CUDA/Triton kernels, run experiments, read results, debug. This is what RE-Bench measures, and where agents already beat human experts 4× at 2-hour budgets.
2. Long-horizon agentic autonomy — plan over many steps, use tools, recover from failure. This is the current bottleneck: RE-Bench showed humans still catch up at 8h+ horizons. If you fine-tune for one thing, tune for this.
3. Meta / self-modification — read and edit its own agent code and prompts, propose improvements, evaluate them. This is the actual "self-improving" loop.

The fine-tuning recipe (weights lever)

Base model. You need open weights — you can't meaningfully fine-tune closed frontier models (Claude, GPT) beyond limited provider offerings. Pick something already strong at code + reasoning: Qwen3-Coder, DeepSeek-R1/V3 distills, or Llama-class. Start from the best code+reasoning base you can afford to run RL on.

Stage 1 — SFT on agentic trajectories. Collect successful multi-step agent transcripts on real AI-R&D tasks (repo PRs, experiment notebooks, kernel implementations, debugging sessions) formatted as tool-use/agent traces. The cheap, effective version is rejection sampling / STaR: have a strong teacher agent attempt tasks, keep only trajectories that verifiably succeeded, and SFT on those. This teaches the format of good agentic research work.

Stage 2 — RL with verifiable rewards (RLVR). This is the one that produces durable gains. Build executable environments where the reward comes from running the code, not a learned judge:
- SWE-bench / SWE-Gym style: patch passes the hidden test suite → reward.
- RE-Bench style: the agent's change actually improves a training run's score.
- Kernel tasks: measured latency speedup.

Use GRPO or PPO (via TRL, verl, or OpenRLHF). The critical design rule: reward must be execution-grounded, never a learned reward model — learned judges get hacked fast, and the report's superalignment survey flagged reward hacking and recursive instability as the core failure modes here.

The data flywheel — this is the practical self-improvement loop at the weight level: model generates solutions → verify by execution → keep winners → SFT/RL on them → repeat. Same shape as the Darwin Gödel Machine, just applied to weights instead of scaffold.

The scaffold lever (don't skip — often higher ROI)

Before or alongside fine-tuning, invest in the harness, because it's where DGM got its gains with zero weight changes:
- Give the model a sandboxed code-execution tool, file editing, an experiment runner, and a benchmark harness.
- Let it edit its own agent code and evaluate the variants, keeping an archive of improvements (the DGM pattern). This is the most direct implementation of "self-improving" and it's cheaper to iterate on than a training run.

Evaluation and honest guardrails

- Evaluate on held-out AI-R&D tasks (unseen SWE-bench splits, RE-Bench environments), and specifically measure long-horizon performance (8h+), since that's the real bottleneck and the easiest thing to fool yourself about.
- Watch for benchmark gaming and reward hacking — hold out test sets the agent never sees during RL, and add adversarial checks.
- Recursive instability is real: training repeatedly on self-generated data collapses diversity. Keep mixing in fresh external data and keep rewards execution-verified.
- Sandbox everything. Self-modifying code that executes is exactly the case where you want hard isolation and a human-review gate on the self-edits — and note the honest context from the research: 20 of 25 leading researchers named automation of AI research the top severity risk, precisely because this loop can compound. Keeping a human in the approval path and logging every self-edit isn't bureaucracy here, it's the difference between a debuggable system and an opaque one.

If I were prioritizing for you: build the sandboxed, self-editing agent scaffold with execution-verified evals first (fast iteration, DGM-proven), then layer RLVR fine-tuning on the trajectories that scaffold produces. Pure weight fine-tuning without the executable-environment flywheel underneath it tends to overfit to benchmarks and not transfer.

Want me to sketch a concrete starter stack — specific base model, an RL framework, and a minimal executable-environment harness — for your setup? I can also pull verified specifics on any one piece (e.g. how DGM structures its self-edit archive, or how RE-Bench environments define reward).
