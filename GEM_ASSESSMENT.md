# GEM1–4 assessment and project plan

## Assessment

The notes are valuable as an idea backlog, not as evidence that ASI or an
intelligence explosion is near. Their strongest transferable principles are:

- **Verifier-first generation:** model-written programs must be judged by an
  external executor and hidden tests. This matches the project’s strongest
  existing boundary.
- **Bounded search:** MCTS, mutation, retries, and entropy schedules are useful
  search policies, but they improve a fixed task objective unless the improver
  itself is measured.
- **Quality diversity:** BetaEvolve’s archive idea is directly applicable. It
  prevents greedy search from discarding specialists and transfer-friendly
  variants.
- **Stability controls:** monotonic promotion, rollback, resource limits,
  immutable evaluators, and small deltas are sound engineering controls. They
  are not a Lyapunov proof of intelligence growth.
- **Symbolic verification:** exact checks, property tests, and eventually SMT or
  theorem-prover obligations can strengthen correctness on suitable tasks.

The notes should not be adopted literally in several places. A scalar
“intelligence” state is not an observable universal capability measure;
`1 / intelligence` is not by itself a valid Lyapunov function; and claims that
Tensor Logic or a local 70B model provide a route to ASI are hypotheses, not
results. A 128 GB Mac can be a useful local laboratory, but model throughput,
quantization quality, thermal limits, and task coverage must be measured rather
than inferred from parameter count. The sample subprocess loop in GEM1 is also
not a security sandbox and must not be used for model-written code.

## Where the project stands

We have demonstrated governed typed-strategy search, execution-grounded coding
agents, matched-budget fixture plumbing, transfer measurements, and a live
quality-diversity archive. We have not demonstrated persistent improvement of
the improver. The current executable suite remains small, and performance mode
requires the reviewed container image.

## Staged plan

1. **Stabilize the benchmark boundary.** Install and pin the reviewed container
   image; add at least three independent executable task families; record
   correctness, runtime, tokens, and evaluator hashes separately.
2. **Complete quality-diversity search.** Archive live strategies by task-vector
   utility, worst-task utility, correctness, and cost. Compare greedy selection,
   random mutation, and archive selection under matched budgets.
3. **Add controlled search policies.** Implement a small deterministic MCTS or
   bandit scheduler over archive parents. Keep the evaluator and promotion gate
   immutable; compare policies on identical seeds.
4. **Add verifier-backed tasks.** Introduce property-based tests and, where a
   task has a precise specification, an SMT/Lean-backed check. Treat a verifier
   as an independent gate, never as model-generated feedback.
5. **Run transfer and metaproductivity cohorts.** Freeze a development task
   family, select strategies there, then evaluate unseen tasks and run the
   matched-budget ancestor/descendant tournament. Require multiple cohorts and
   bootstrap intervals before calling a result empirical.
6. **Only then test local models.** Compare the OpenAI proposer with pinned MLX
   or llama.cpp models under equal token/time budgets. This is a provider/model
   comparison, not an assumption that larger local models imply RSI.

## Immediate next action

The highest-value next action is step 1: install the reviewed container runtime
and expand the executable benchmark. Without that, archive diversity and model
comparisons remain interesting plumbing around a narrow, noisy objective.
