# Recursive self-improvement: state of the field

**Assessment as of July 19, 2026:** bounded forms of self-improvement are now experimentally real. Systems can improve their outputs, memories, prompts, training data, tool use, agent scaffolds, and sometimes their own source code. Some can also conduct portions of AI research that might contribute to building better successors.

What has **not** been publicly demonstrated is strong, open-ended recursive self-improvement: a system repeatedly improving the machinery that produces its next improvement, transferring those gains broadly, preserving its objectives and evaluator integrity, and continuing to accelerate without substantial human redesign.

The most defensible summary is therefore:

> **Weak or bounded RSI exists. Open-ended RSI and an intelligence explosion remain unproven.**

This distinction is consistent with the strongest scaffold-editing work, the latest automated-research systems, and recent surveys of self-evolving agents.  [oai_citation:0‡arxiv.org](https://arxiv.org/html/2505.22954v3)

---

## 1. What should count as recursive self-improvement?

Let the deployed system be

\[
S_t=(\theta_t,H_t,M_t,T_t,E_t,R_t)
\]

where:

- \(\theta\) represents model weights,
- \(H\) the agent harness and prompts,
- \(M\) persistent memory,
- \(T\) tools and execution environments,
- \(E\) evaluators and acceptance tests,
- \(R\) the resource-allocation or search strategy.

A system performs **persistent self-improvement** when it proposes a candidate \(S_{t+1}\) and that candidate performs better on held-out evaluations under comparable resource limits:

\[
U(S_{t+1};B)>U(S_t;B)
\]

where \(B\) is a fixed compute, time, data, or monetary budget.

But this alone is not necessarily *recursive*. A stricter definition asks whether the successor is better at producing subsequent successors. Define its improvement productivity as:

\[
M(S_t)=
\mathbb{E}
\left[
\frac{U(S'_t)-U(S_t)}
{\operatorname{cost}(S_t\rightarrow S'_t)}
\right].
\]

A genuinely recursive step should produce:

\[
M(S_{t+1})>M(S_t),
\]

not merely \(U(S_{t+1})>U(S_t)\).

This quantity is sometimes described as **metaproductivity**: performance on the task of making future improvements. Recent work such as the Huxley-Gödel Machine explicitly argues that ordinary benchmark performance can be a poor proxy for this quantity.  [oai_citation:1‡arxiv.org](https://arxiv.org/abs/2510.21614)

Three distinctions prevent most confusion in this field:

1. **Self-correction is not necessarily self-improvement.** Revising one answer leaves the system unchanged.
2. **Self-modification is not necessarily improvement.** A system can rewrite itself and become worse.
3. **Repeated improvement is not necessarily recursive improvement.** A fixed external optimizer can produce several better versions without the improvement process itself getting better.

The boundary of the “self” also matters. For an LLM agent, treating only the weights as the system is usually too narrow. Its prompts, tools, memory, search procedures, code-execution environment, and evaluators can determine as much of its behavior as the weights. Modern RSI research increasingly treats the entire agent architecture as the mutable cognitive system.  [oai_citation:2‡arxiv.org](https://arxiv.org/html/2505.22954v3)

---

## 2. A practical taxonomy

| Level | What changes persistently? | Representative work | Current interpretation |
|---|---|---|---|
| **0. Output refinement** | Nothing beyond the current trajectory | Self-Refine, Reflexion | Useful self-correction, but not persistent RSI.  [oai_citation:3‡arxiv.org](https://arxiv.org/abs/2303.17651) |
| **1. Memory, prompts or tools** | Memories, instructions, tool-selection policies | Promptbreeder and related prompt evolution | Bounded adaptation inside a human-designed framework.  [oai_citation:4‡openreview.net](https://openreview.net/forum?id=HKkiX32Zw1) |
| **2. Weights or learned policy** | Model parameters through self-generated data, self-play or self-reward | STaR, self-rewarding language models, SPIN | Genuine learning from the system’s own outputs, but normally under fixed objectives and training algorithms.  [oai_citation:5‡arxiv.org](https://arxiv.org/abs/2203.14465) |
| **3. Agent scaffold or source code** | Planning logic, tools, prompts, workflow and agent implementation | STOP, Gödel Agent, SICA, Darwin Gödel Machine | Strongest current evidence for bounded, self-referential improvement.  [oai_citation:6‡arxiv.org](https://arxiv.org/abs/2310.02304) |
| **4. The improvement procedure** | Search strategy, modifier, evaluator or research process | Huxley-Gödel Machine, Hyperagents, Red Queen Gödel Machine, AIDE² | Promising but early; much of the evidence is from preprints or developer-authored reports.  [oai_citation:7‡arxiv.org](https://arxiv.org/abs/2510.21614) |
| **5. Open-ended RSI** | Broad successor-design capability, including increasingly effective improvement mechanisms | No convincing public example | Remains an open empirical question. Recent surveys likewise describe fully autonomous, open-ended evolution as aspirational.  [oai_citation:8‡arxiv.org](https://arxiv.org/abs/2607.07663) |

This taxonomy is more informative than a binary label. A system may be highly capable at Level 3 while making no progress toward Level 5.

---

## 3. Intellectual history

### Good’s intelligence explosion

I. J. Good’s 1965 argument was conditional: if an “ultraintelligent machine” could design still better machines, human intelligence might be left behind in a positive feedback process. The argument identifies a possibility but does not establish that improvement returns would remain positive, transferable, or accelerating.  [oai_citation:9‡ScienceDirect](https://www.sciencedirect.com/science/chapter/bookseries/pii/S0065245808604180)

### Gödel machines

Jürgen Schmidhuber’s Gödel machine framework proposed a self-referential system that rewrites itself only after finding a proof that the rewrite improves its expected utility. It is an important theoretical ideal because it joins self-reference, utility preservation, and proof-carrying modification. In practice, general proof search is extraordinarily difficult, and today’s empirical systems substitute benchmarks, tests, experiments, or learned judges for formal proof.  [oai_citation:10‡people.idsia.ch](https://people.idsia.ch/~juergen/goedelmachine.html)

### The modern empirical turn

From roughly 2022 onward, research shifted from proof-oriented universal self-improvers toward narrower loops that can be tested:

- generating and training on verified reasoning traces,
- critiquing and revising model outputs,
- evolving prompts,
- rewriting agent programs,
- searching archives of candidate agents,
- automating portions of machine-learning research.

This makes empirical progress possible, but it also transfers the central burden from theorem proving to **evaluation integrity**.

---

## 4. What has actually been demonstrated?

### 4.1 Inference-time self-refinement

Self-Refine showed that a language model can generate feedback and iteratively revise its own answer without changing its parameters. Reflexion stores verbal feedback from previous attempts and uses it in later trajectories. These methods can improve performance, but they are closer to structured search or episodic learning than recursive self-improvement.  [oai_citation:11‡arxiv.org](https://arxiv.org/abs/2303.17651)

More importantly, intrinsic self-correction is unreliable when the model has no stronger external signal. Studies find that models may preserve an incorrect answer, invent flaws in a correct one, or degrade performance after being asked to reconsider. A critic generated by the same fallible system is not automatically an independent source of truth.  [oai_citation:12‡arxiv.org](https://arxiv.org/abs/2310.01798)

### 4.2 Self-training and weight-level improvement

STaR generates reasoning traces, retains those associated with correct answers, fine-tunes on them, and repeats. Self-rewarding language models use the model’s own judgments to construct preference data. Self-play methods such as SPIN train a new model against outputs from an earlier version. These approaches demonstrate that a model can contribute materially to producing its own training signal.  [oai_citation:13‡arxiv.org](https://arxiv.org/abs/2203.14465)

They nevertheless remain bounded in several ways:

- humans generally choose the task distribution,
- the training algorithm is fixed,
- the objective or verifier is external,
- the base data provides an anchor,
- the system usually cannot redesign the training infrastructure itself.

Recursive synthetic-data training also has a known failure mode. Indiscriminately training successive generations on generated data can narrow the represented distribution and produce “model collapse.” This does **not** mean all synthetic data is harmful: verified, filtered or deliberately diverse synthetic data mixed with fresh external data can be effective. The danger is uncontrolled recursive replacement of the underlying distribution.  [oai_citation:14‡Nature](https://www.nature.com/articles/s41586-024-07566-y)

### 4.3 Prompt and scaffold evolution

Promptbreeder evolves both task prompts and the prompts used to mutate those prompts, giving it a limited self-referential structure. STOP lets a language-model-driven scaffold improve the program that invokes it, although its authors explicitly distinguish this from full RSI because the underlying language model remains fixed.  [oai_citation:15‡openreview.net](https://openreview.net/forum?id=HKkiX32Zw1)

This category is important because scaffold changes are:

- much cheaper than retraining weights,
- easier to inspect and revert,
- naturally evaluated through execution,
- capable of reorganizing planning, memory and tool use.

For current systems, scaffold improvement often offers higher experimental leverage than fine-tuning.

### 4.4 Agents that edit their own implementation

Gödel Agent allows an agent to modify its own logic and behavior rather than merely choosing from a fixed library of prompts. SICA similarly explores agents that edit their own code and evaluates the result on software-engineering tasks. These are meaningful steps toward self-reference, although their evidence is still benchmark-bound and often based on limited experimental settings.  [oai_citation:16‡aclanthology.org](https://aclanthology.org/2025.acl-long.1354/)

The **Darwin Gödel Machine** is one of the clearest public demonstrations in this category. It maintains an archive of agent variants, lets agents propose modifications to their own code and workflows, evaluates the variants, and preserves useful stepping stones rather than following only one lineage. With frozen foundation models, it reported an increase from 20.0 to 50.0 on a SWE-bench evaluation and from 14.2 to 30.7 on a multilingual software-engineering benchmark.  [oai_citation:17‡arxiv.org](https://arxiv.org/html/2505.22954v3)

That is substantial evidence that an agent scaffold can improve itself. It is not yet evidence of an intelligence explosion because:

- the foundation models remained fixed,
- the evaluation domains were selected in advance,
- the acceptance signal was externally supplied,
- improvement on coding tasks was used as a proxy for improvement ability,
- the process was not shown to accelerate indefinitely or generalize to unrestricted research.

The DGM architecture’s archive is nevertheless a significant contribution. Maintaining diverse lineages reduces the risk that greedy optimization gets trapped at a local optimum and resembles ideas from open-ended evolution.

### 4.5 Improving the improver

A newer group of systems directly targets the outer loop.

The **Huxley-Gödel Machine** introduces metaproductivity-oriented selection: it seeks agents that are useful not only because they score well now, but because they are promising parents for future improvement. **Hyperagents** make the meta-level modification procedure itself editable. The **Red Queen Gödel Machine** investigates co-evolving agents and evaluators rather than leaving the test distribution entirely static. These are conceptually closer to recursion, but the evidence remains early and largely comes from recent preprints.  [oai_citation:18‡arxiv.org](https://arxiv.org/abs/2510.21614)

Co-evolving the evaluator is particularly delicate. It may combat overfitting to a static benchmark, but it can also produce a self-confirming system in which the solver and judge gradually agree with each other while drifting away from the external objective. A changing evaluator therefore needs an immutable external reference, hidden audits or periodic human grounding.

### 4.6 AIDE² and the latest “net-positive RSI” claim

On July 14, 2026, Weco described **AIDE²**, a two-level system in which an outer agent modifies an inner AI-research agent. Weco reports 100 unattended outer-loop iterations, seven successive improved versions, held-out task evaluation, better transfer to several additional benchmarks, and a reduction in detected reward-hacking behavior.  [oai_citation:19‡Weco AI](https://www.weco.ai/blog/first-evidence-of-recursive-self-improvement)

The most important detail is Weco’s own classification. It claims **Level 1: net-positive RSI**, not **Level 2: ignition**. Its ignition test did not establish a statistically significant higher asymptotic ceiling; the improved system reached a similar ceiling faster. The developer also reports that evolved code became difficult to understand and accumulated dead or defective components.  [oai_citation:20‡Weco AI](https://www.weco.ai/blog/first-evidence-of-recursive-self-improvement)

This makes AIDE² an important result to watch, but not yet a settled finding. As of July 19, its detailed technical report and public agent release were still pending, so the claims were not yet independently assessable.

---

## 5. Automated AI research is adjacent to—but not identical with—RSI

The most plausible route to consequential RSI is automation of AI research itself. An agent that can reliably invent algorithms, implement experiments, interpret results, and modify training systems could contribute to creating a stronger successor.

### RE-Bench

RE-Bench evaluates agents on seven open-ended machine-learning research-engineering environments. In the reported experiments, the best AI system achieved approximately four times the human-expert score at a two-hour budget. Humans narrowly recovered the lead at eight hours and achieved about twice the AI score at 32 hours.  [oai_citation:21‡arxiv.org](https://arxiv.org/abs/2411.15114)

This result suggests a characteristic current profile:

- high speed on short, executable tasks,
- rapid generation and testing of variants,
- weaker performance on long-horizon prioritization,
- difficulty accumulating a coherent research program over many hours.

That gap matters because RSI requires more than fast local coding. It requires choosing worthwhile directions, diagnosing misleading results, managing dependencies, and preserving coherent objectives across long sequences of changes.

### The AI Scientist

The AI Scientist work demonstrates a pipeline spanning idea generation, coding, experiments, manuscript production and automated review. In the Nature-reported evaluation, humans still filtered promising outputs; one of three selected submissions was judged likely to clear a relatively high-acceptance workshop, while none reached the standard expected for a main conference. Common problems included naive research ideas, hallucinated claims and incorrect implementations.  [oai_citation:22‡Nature](https://www.nature.com/articles/s41586-026-10265-5)

This is meaningful automation of scientific workflow, but it becomes RSI only when the research system successfully improves its **own research machinery**.

### Human bottlenecks

Anthropic’s internal account of AI-assisted AI development describes rapidly increasing automation of implementation work, while identifying direction-setting, research taste and review as persistent human bottlenecks. Because these are company-reported observations rather than neutral measurement, they should be treated cautiously, but they align with the longer-horizon pattern in RE-Bench. Anthropic’s own capability framework also distinguishes current AI-research assistance from a level that would cause dramatic research acceleration.  [oai_citation:23‡Anthropic](https://www.anthropic.com/institute/recursive-self-improvement)

---

## 6. Why current progress does not establish an intelligence explosion

Suppose capability evolves as:

\[
C_{t+1}=C_t+g(C_t,E_t,R_t)-K_t,
\]

where \(g\) is the improvement generated by the current system and \(K\) represents growing difficulty, evaluation cost, compute cost and accumulated errors.

Repeated positive gains require only:

\[
g>K.
\]

An intelligence explosion requires something stronger: improving capability must increase the effectiveness of the improvement process rapidly enough to outrun increasing costs and diminishing returns.

Current demonstrations usually show one of the following:

- a jump from a weak scaffold to a better scaffold,
- faster search within a fixed space,
- better performance on a fixed benchmark,
- transfer to a small collection of related tasks,
- several generations of improvement followed by a plateau.

None of these establishes unbounded acceleration.

The principal limiting factors are:

### Evaluator quality

A system cannot reliably improve beyond what its acceptance process can distinguish. Deterministic tests work well for code, games and formal mathematics. Many research questions, strategic decisions and real-world objectives do not have cheap deterministic verifiers.

### Research taste and problem selection

Generating solutions to supplied problems is easier than identifying which problems are important, tractable and informative. An agent can become extremely efficient at optimizing a poorly chosen research agenda.

### Long-horizon coherence

Improvements that look good after a short trial may create maintenance debt, brittleness or delayed regressions. Current agents remain much weaker at long, ambiguous projects than on short executable tasks.  [oai_citation:24‡arxiv.org](https://arxiv.org/abs/2411.15114)

### Open-endedness

A fixed benchmark defines a ceiling. Open-ended RSI would need to generate increasingly difficult, meaningful and externally grounded challenges while preserving diversity and avoiding cycles of self-confirmation.

### Resource and physical constraints

Training runs, chip fabrication, experiments, data collection and organizational deployment impose latency that cannot necessarily be compressed in proportion to reasoning speed.

### Stability

Repeated self-modification can accumulate software debt, specification drift, security vulnerabilities and changes that interact unpredictably. The finding that evolved AIDE² code became harder to understand is a small but concrete example of this general problem.  [oai_citation:25‡Weco AI](https://www.weco.ai/blog/first-evidence-of-recursive-self-improvement)

---

## 7. The evaluator is the central technical and safety problem

A useful verification hierarchy is:

1. **Formal proof**, where feasible.
2. **Deterministic programmatic verification**, such as tests, theorem checkers or measured physical quantities.
3. **Hidden empirical evaluation**, including private test sets and controlled experiments.
4. **Independent human or model panels**, calibrated against known cases.
5. **Self-critique by the candidate itself**, used as a weak signal rather than ground truth.

Execution-grounded rewards are preferable when they genuinely represent the objective. But “never use a learned judge” is too categorical. Many open-ended domains have no complete programmatic verifier. In those cases, learned evaluators may be necessary, but they should be treated as fallible measurement instruments and supplemented with hidden tests, disagreement detection, adversarial audits and external review.

The most dangerous design is one in which the candidate can modify both its behavior and the sole mechanism that decides whether the modification was successful.

---

## 8. What a convincing RSI experiment would need to show

A serious claim should satisfy substantially more than “the agent edited its code and its score went up.”

| Criterion | Minimum convincing evidence |
|---|---|
| **Persistence** | The accepted change remains part of future system state. |
| **Causal self-reference** | The system itself materially generated the change, rather than merely selecting a human-authored option. |
| **Real improvement** | Gains appear on hidden evaluations rather than only the development benchmark. |
| **Metaproductivity** | Descendants generate better or cheaper further improvements than ancestors under the same budget. |
| **Transfer** | Gains extend to unseen tasks, domains, base models or resource regimes. |
| **Multiple generations** | Improvement persists over enough iterations to distinguish a trend from harvesting easy fixes. |
| **Resource accounting** | Compute, data, wall-clock time and human labor are included in the comparison. |
| **Evaluator integrity** | The candidate cannot silently alter, leak or game the decisive evaluation. |
| **Stability** | Capabilities do not come with unacceptable regressions, goal drift or security degradation. |
| **Independent replication** | A separate group can reproduce the claimed recursive effect. |

Using these criteria, I did not find a public system that establishes open-ended RSI.

### A decisive “ignition” test

A particularly useful experiment would compare an ancestor and descendant as **improvers**, not merely as task solvers:

1. Give both the same starting agent, tasks, tools and fixed resource budget.
2. Allow each to construct a successor.
3. Evaluate the successors on hidden and out-of-distribution tasks.
4. Repeat the process over multiple generations.
5. Compare improvement per unit of compute, ceiling performance, transfer and safety.
6. Conduct causal ablations to determine which self-generated changes were responsible.

Evidence for ignition would require the descendant’s improvement curve to have a reliably greater slope or higher asymptote—not simply reach the same plateau sooner.

---

## 9. A safe experimental architecture

A well-designed RSI laboratory would separate the mutable system from an external governance plane:

```text
Immutable governor
    │
    ├── resource and permission limits
    ├── hidden evaluator suite
    ├── safety constraints and tripwires
    └── signed audit log
             │
             ▼
      Current agent / improver
             │
       proposes candidate
             ▼
       Isolated sandbox
             │
       capability + safety
          evaluation
             │
      accept / reject / roll back
             │
       lineage archive
```

The candidate should not be able to modify:

- the root acceptance gate,
- private evaluation data,
- audit records,
- network or credential permissions,
- deployment controls,
- shutdown mechanisms.

Additional controls should include reproducible builds, cryptographic artifact lineage, fixed compute budgets, staged deployment, independent red-team evaluations and immediate rollback. DGM used isolated execution, limited networking and auditable modification lineages; AIDE² used public/private task separation and fixed budgets, illustrating parts of this design.  [oai_citation:26‡arxiv.org](https://arxiv.org/html/2505.22954v3)

The safety evaluation must be conjunctive rather than averaged into one score:

\[
\text{accept}
=
\text{capability gain}
\land
\text{safety preserved}
\land
\text{evaluator integrity}
\land
\text{resource compliance}.
\]

A large capability improvement should not compensate numerically for a severe security or alignment regression.

---

## 10. Most important research directions

### 1. Measuring metaproductivity

The field needs benchmarks that evaluate how effectively an agent creates future improvers, rather than treating coding performance as a proxy. This requires ancestral comparisons, fixed budgets, causal analysis and long lineages.

### 2. Robust, adaptive evaluation

Static benchmarks are eventually optimized into irrelevance. Purely self-generated evaluators risk drift. The promising middle ground is adaptive challenge generation combined with an immutable external anchor and periodically refreshed hidden ground truth.

### 3. Long-horizon AI research agents

Progress on experiment design, result interpretation, strategic prioritization and recovery from misleading evidence is more important to strong RSI than additional speed on isolated coding problems.

### 4. Joint scaffold-and-weight improvement

Fast outer loops could alter prompts, memory, tools and agent code, while slower, more carefully governed loops update model weights from verified trajectories. These layers should be evaluated separately so that apparent gains can be attributed correctly.

### 5. Open-ended diversity

Archives, novelty mechanisms and diverse lineages may prevent premature convergence. But novelty must remain externally meaningful; generating endless unusual artifacts is not equivalent to improving intelligence.

### 6. Alignment under self-modification

Research is needed on invariant objectives, tamper-resistant supervision, interpretability across versions, corrigibility and proof- or test-carrying changes. Any system capable of changing its own improvement process changes the assumptions under which its earlier safety evaluation was conducted.

### 7. Reproducible evidence

Recent RSI claims vary substantially in evidence quality: peer-reviewed studies, preprints, limited benchmark demonstrations and company-authored announcements are often discussed together. Public code, full cost accounting, hidden third-party tests and replication should be prerequisites for strong claims.

---

## 11. Assessment of your attached memo

Your memo correctly identifies several central points:

- “building self-improving AI” is not only a fine-tuning problem;
- ML research engineering, long-horizon autonomy and meta-modification are different bottlenecks;
- scaffold improvement can currently have a better cost-to-information ratio than weight training;
- executable, held-out evaluation is crucial;
- self-modifying code should be sandboxed, logged and reviewed.  [oai_citation:27‡SELFIMPROVE.md](sediment://file_0000000021ec820a9d7373c5a6bd9e54)

I would revise four aspects.

**First, weaken “reward must be execution-grounded, never a learned reward model.”** Deterministic verification is the strongest option when available, but many research outputs cannot be reduced to a test suite. A better rule is: use the highest-integrity verifier available, and never allow an uncalibrated learned judge to be the sole acceptance authority.

**Second, qualify the synthetic-data warning.** Recursive use of generated data can cause distributional collapse, but verified synthetic data, self-play and generated examples mixed with fresh external data can produce real gains. The danger is unfiltered replacement, not synthetic data in itself.  [oai_citation:28‡Nature](https://www.nature.com/articles/s41586-024-07566-y)

**Third, interpret DGM narrowly.** Its reported gain is strong evidence for scaffold optimization with frozen foundation models, not evidence that model intelligence has entered a general, accelerating recursive loop.  [oai_citation:29‡arxiv.org](https://arxiv.org/html/2505.22954v3)

**Fourth, remove or source the “20 of 25 leading researchers” statistic.** The memo does not provide a traceable primary source for that number, so it should not support a research conclusion until one is supplied.

The memo would be strongest if reframed as a **layered research roadmap**:

1. build an auditable self-editing scaffold;
2. establish private and out-of-distribution evaluations;
3. measure metaproductivity, not only task performance;
4. add verified trajectory training;
5. investigate weight-level updates only after the outer evaluation loop is trustworthy;
6. keep the acceptance and governance layer outside the system’s modification boundary.

---

## Bottom line

Recursive self-improvement is no longer purely philosophical. The field now contains working systems that:

- learn from their own successful outputs,
- evolve prompts and mutation strategies,
- rewrite their own agent code,
- search archives of successor designs,
- automate meaningful portions of AI research.

The leap from those results to open-ended RSI remains large. The missing ingredient is not simply more self-editing. It is a demonstrably stable increase in **future improvement productivity**, validated by external evidence across many generations and domains.

The strongest near-term research strategy is therefore a hybrid one: **fast, auditable scaffold evolution; slower verified weight updates; hidden external evaluation; fixed resource accounting; and an immutable safety and acceptance layer.** Under that standard, bounded RSI is an active engineering field, while intelligence explosion remains a hypothesis rather than an observed phenomenon.
