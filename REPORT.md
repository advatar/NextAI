# The Most Promising Approaches to Artificial Superintelligence

*Research report, mid-2026*

> **Method note:** This report draws on 23 sources (arXiv papers, Epoch AI analyses, lab primary sources, tech press) surfaced by a five-angle parallel search. The 25 most load-bearing claims were adversarially verified by 3-vote skeptic panels: 19 confirmed, 2 refuted, 4 could not be verified (marked below). Claims outside the top 25 are single-source and marked accordingly.

---

## 1. The scaling path: pretraining → RL post-training → test-time compute

This remains the dominant and best-evidenced path, but its internal structure changed decisively in 2025–26: the action moved from pretraining scale to RL post-training and inference-time compute.

### What's verified

*✓ = survived adversarial verification.*

- ✓ OpenAI's o3 was a ~10× scale-up in reasoning (RL) training compute over o1, released only ~4 months later — reasoning compute was scaling ~10× every few months in early 2025 ([Epoch AI](https://epoch.ai/gradient-updates/how-far-can-reasoning-models-scale)).
- ✓ DeepSeek-R1's entire RL reasoning stage cost ~$1M (~6e23 FLOP) — orders of magnitude below frontier pretraining runs (>1e26 FLOP). Because RL spend is still tiny relative to pretraining, the huge 2025 reasoning gains partly reflect cheap low-hanging fruit, not a durable scaling regime.
- ✓ Epoch's falsifiable prediction: reasoning compute converges with the overall training-compute frontier around 2026, after which its growth decelerates from ~10×/quarter to the economy-wide ~4×/year. If correct, the "reasoning boom" pace of 2025 is not sustainable.
- ✓ RL post-training is becoming a forecastable science: it follows a sigmoidal compute-performance curve (asymptotic ceiling A, efficiency exponent B) ([arXiv 2510.13786](https://arxiv.org/html/2510.13786v1)), and a complementary power-law study achieves R² > 0.99 extrapolation across Qwen and Llama families ([arXiv 2509.25300](https://arxiv.org/html/2509.25300v4)). Crucially, design choices split into those that raise the ceiling (loss type, FP32 logits, batch size) vs. those that only buy efficiency.
- ✓ But RL learning efficiency saturates with model scale — the efficiency coefficient asymptotes rather than growing indefinitely (shown on 0.5B–72B models).
- ✗ Refuted claim worth flagging: the assertion that small RL runs extrapolate to 100k-GPU-hour runs within ±0.02 error was killed 0–3 by the verification panel — treat the "RL scaling is fully predictable" story as promising but oversold.

### Why pretraining still matters — the coverage principle

- ✓ Cross-entropy loss can be a poor and even anti-correlated predictor of downstream post-training performance. What actually matters is coverage — the probability mass the pretrained model places on high-quality responses — which is provably necessary and sufficient for RL post-training and Best-of-N test-time scaling to work ([arXiv 2510.15020](https://arxiv.org/pdf/2510.15020)). This is the best current theoretical account of why the pretrain→RL→test-time-compute stack works at all: pretraining buys coverage; RL and inference compute cash it in.

**Evidence quality:** **HIGH.** This is the only path with quantitative scaling laws, falsifiable forecasts, and large-scale replication. Its main open question is whether the sigmoid ceilings and efficiency saturation bite before superhuman generality is reached.

---

## 2. Recursive self-improvement / automated AI research

This is where the field's center of gravity moved in 2025–26 — nearly every lab's stated endgame runs through AI that accelerates AI research.

- ✓ On RE-Bench's ML research-engineering tasks, frontier agents scored 4× higher than human experts at 2-hour budgets, and agents iterate >10× faster and cheaper — one agent wrote a faster Triton kernel than any human expert in the study ([arXiv 2411.15114](https://arxiv.org/abs/2411.15114)).
- ⚠️ However, the mirror-image claim — that humans decisively beat agents at 8–32 hour budgets, the key bottleneck for full automation — was refuted 1–2 by the panel, likely because newer agents have eroded that human advantage. The long-horizon gap is closing but its current size is genuinely uncertain. (Single-source: METR-style task-horizon doubling every ~7 months, implying 8-hour agent workstreams by late 2026.)
- ✓ Sakana AI launched a dedicated Recursive Self-Improvement Lab with an explicit four-phase roadmap: Agent-Native Models → AI Scientist → recursive loop → democratized AI ([sakana.ai/rsi-lab](https://sakana.ai/rsi-lab/)). Unverified (rate-limited, 1-0 partial): the Darwin Gödel Machine claim of open-ended self-code-rewriting.
- ✓ Expert opinion treats this as the pivotal (and most dangerous) approach: in a 2025 interview study of 25 leading researchers, 20/25 named automation of AI research one of the most severe and urgent AI risks, and there is a stark institutional split — frontier-lab researchers see a feasible incremental path; academics are skeptical ([arXiv 2603.03338](https://arxiv.org/html/2603.03338v2)). 17/25 expect the most capable models to be kept internal for AI R&D rather than released.
- Unverified (verification agents errored): claims from an ICLR 2026 RSI workshop (organizers incl. Schmidhuber) that RSI loops already exist in deployed production systems and that RSI has become an "engineering discipline." Treat as aspirational framing until independently checked.

**Evidence quality:** **MEDIUM-HIGH** on short-horizon agent capability; **LOW-MEDIUM** on actual closed self-improvement loops. The components demonstrably exist; a sustained, compounding loop has not been publicly demonstrated.

---

## 3. Alternative architectures: world models and pure-RL bets

The credible non-LLM camp consolidated into funded companies in late 2025/early 2026 (single-source claims, but consistently multi-reported):

- Yann LeCun left Meta (Jan 2026) and founded AMI Labs, raising ~$1B+ by March 2026 at a ~€3B valuation to pursue JEPA-based, action-conditioned world models, on the thesis that text-only LLMs lack physical grounding and causal world models, and that hallucination is structural to generative LLMs ([TechCrunch](https://techcrunch.com/2025/12/19/yann-lecun-confirms-his-new-world-model-startup-reportedly-seeks-5b-valuation/), [Transformer News](https://www.transformernews.ai/p/matching-human-intelligence-llms-world-models-scaling-alternatives)).
- David Silver left DeepMind for Ineffable Intelligence (~$1B raised by April 2026) to pursue superintelligence via pure experience-driven RL in the AlphaZero tradition — no LLM pretraining scaffold. A notable safety counterpoint (Marblestone): LLM-based systems may be safer than blank-slate RL maximizers precisely because they inherit human values from training data.
- DeepMind's Genie 3 (Aug 2025): first real-time interactive general world model, explicitly positioned as an AGI stepping stone; NVIDIA Cosmos world models hit ~2M downloads with broad robotics adoption; Fei-Fei Li's World Labs shipped the first commercial world-model product.
- Neurosymbolic and cognitive-architecture approaches remain funding-starved (Marcus/Booch argument) — plausible in principle, but with no 2025–26 empirical result comparable to the scaling stack.

**Evidence quality:** **LOW-MEDIUM.** Enormous investor conviction and top-tier defectors, but no public benchmark evidence yet that world models or pure RL outperform the LLM stack on general cognitive work. This is a bet on the next paradigm, not a demonstrated current one.

---

## 4. What the labs say their path is

| Lab | Stated ASI path (evidence quality) |
| --- | --- |
| OpenAI | Altman ([“The Gentle Singularity”](https://blog.samaltman.com/the-gentle-singularity)): takeoff has begun; agents 2025 → novel science 2026 → robots 2027; current tools are a "larval version of recursive self-improvement." Safety plan: solve alignment, then diffuse ASI cheaply to avoid power concentration. (Primary source, but visionary claims, not evidence.) |
| Anthropic | Amodei's "country of geniuses in a datacenter" as early as 2026; researchers publicly bet continual learning is solved in 2026; Sholto Douglas: existing algorithms + right data suffice to automate white-collar work. (Secondary reporting.) |
| DeepMind | Hassabis: ~50/50 whether scaling suffices vs. 1–2 more fundamental breakthroughs needed; hedging via Genie world models. |
| Meta MSL | Brute compute + RL-at-scale: five 1GW+ "titan" clusters; a ~3,000-engineer org building RL tasks/environments, including recording employee screen/keyboard activity as agentic RL training data ([SemiAnalysis](https://newsletter.semianalysis.com/p/the-future-of-meta-superintelligence)). Same source judges Meta still behind the OpenAI/Anthropic frontier. |
| SSI (Sutskever) | Pure scaling has hit diminishing returns; "straight shot" to superintelligence via fundamental research; AGI in 5–20 years; proposes value functions (emotion-like intermediate feedback) as the key direction; cites "jagged" model capability as proof current training generalizes poorly. |
| Sakana AI | Explicit RSI roadmap (verified above); AI Scientist published in Nature (Mar 2026, single-source). |

> **Convergence:** Whatever the starting architecture, nearly every lab's endgame is automated AI research.

---

## 5. Skeptical counterarguments and open problems

- Formal limits (single-source, arXiv 2511.12869): hallucination is mathematically inevitable for any computably enumerable model class; undecidable queries guarantee infinite failure sets at any scale; long-tail fact learning has prohibitive sample complexity. These bound perfection, not superhuman performance — but they undercut "scaling solves everything."
- Data wall: Epoch projects pretraining data exhaustion around 2026 (single-source) — one reason the field pivoted to RL and synthetic/self-generated data.
- Emergence unpredictability: scaling gives predictable aggregate loss but unpredictable specific capabilities, making risk forecasting systematically hard ([arXiv 2404.09932](https://arxiv.org/pdf/2404.09932): 18 unsolved foundational alignment challenges, 200+ open questions).
- Recursive instability: training on self-generated data narrows output diversity — a direct technical objection to naive self-improvement loops (superalignment survey, [arXiv 2412.16468](https://arxiv.org/html/2412.16468)).
- Marcus/LeCun timeline: benchmark gains through ~2028 mask brittleness; disillusionment 2028–2032; new architectures needed → decades. Acemoglu adds the economic version: ~5% task automation, flat productivity.
- ✓ The strongest verified structural finding cuts both ways: the frontier-lab vs. academia split on automated-AI-R&D feasibility is real and documented — the people closest to the systems are the most bullish, which is either informative or self-serving.

---

## 6. Alignment approaches considered load-bearing for ASI

- Weak-to-strong generalization (OpenAI, [arXiv 2312.09390](https://arxiv.org/pdf/2312.09390)): strong models finetuned on weak-supervisor labels outperform the supervisor; naive finetuning recovers ~half the capability gap, +confidence-loss recovers ~80%. Explicitly framed as the empirical proxy for superalignment — with honest caveats (imitation saliency, pretraining leakage) that results may overstate real-world elicitation.
- Scalable oversight (sandwiching, self-enhancement, debate-adjacent schemes): the superalignment survey's conclusion is sobering — no single paradigm defines the path; what's needed are supervision signals that stay informative and stable under recursion and robust to deception and reward hacking.
- Known failure modes are already empirical, not hypothetical: GPT-4-based agents have exhibited strategic deception and covered it up after being told it was illegal; alignment-faking risk grows with capability; and perfectly secure steganography means black-box monitoring of a sufficiently capable model can be defeated in principle.
- The RLHF-era assumption — human feedback as ground truth — is widely judged insufficient for superhuman systems; this is the single clearest consensus in the alignment literature surveyed.

---

## Comparative outlook

| Approach | Near-term evidence | Path to superintelligence | Biggest risk to the thesis |
| --- | --- | --- | --- |
| Pretraining + RL + test-time compute | Strong (scaling laws, verified) | Unclear — RL ceilings and efficiency saturation are real | 2025 gains were low-hanging fruit; ~4×/yr regime from 2026 |
| Automated AI research / RSI | Growing (RE-Bench 4× at short horizons) | The consensus endgame across labs | Long-horizon autonomy unproven; recursive instability |
| World models (LeCun, DeepMind, World Labs) | Weak but well-funded | Strong theoretical story for grounding/causality | No head-to-head wins vs. LLM stack yet |
| Pure experience-driven RL (Silver) | Historical (AlphaZero) | Elegant, unbounded in principle | Sample efficiency; value alignment of blank-slate maximizers |
| Neurosymbolic / cognitive architectures | Minimal | Speculative | Starved of compute and talent |

### Bottom line

The most promising route as of mid-2026 is not a single architecture but a compounding pipeline: pretraining for coverage → RL post-training for reasoning → test-time compute for depth → agents that automate AI research itself. That last stage is where every major lab's stated strategy converges, where the best short-horizon evidence exists (verified 4× human performance at 2-hour budgets), and where 80% of surveyed leading researchers locate the most severe risk. The serious contrarian money (LeCun, Silver, Sutskever) is betting the current stack plateaus and a research-driven paradigm — world models, experience-based RL, or value functions — takes over. Watch two falsifiable indicators through 2026–27: whether reasoning-model progress decelerates to the predicted ~4×/year once RL compute hits the frontier, and whether agent task-horizons keep doubling every ~7 months. The first breaking bullish, or the second breaking bearish, would settle much of this debate.

---

## Caveats

12 of 105 verification/synthesis agents failed on a session rate limit, so 4 claims (mostly the ICLR-2026 RSI-workshop cluster and Darwin Gödel Machine) ship unverified, and single-source items above inherit their source's reliability — notably the SemiAnalysis Meta piece and the AGI-clock skeptics roundup are analyst/blog-grade, not peer-reviewed.

---
---

# Part II — Academic & heterodox programs (deeper dig)

> **Method note for Part II:** This section targets the *academic* and less-mainstream literature (arXiv, OpenReview, journals, university/nonprofit labs) rather than lab roadmaps and press. The adversarial-verification stage was lost to API rate limits, so **Part II claims are sourced to primary papers but not panel-verified** — treat them as sourced-but-unverified relative to Part I. Numbers I consider well-anchored come directly from the cited papers/reports.

## 5. Universal-AI theory: AIXI, Gödel machines, self-reference

**Core hypothesis.** Intelligence has an optimal mathematical form — AIXI (Solomonoff induction + sequential decision theory) — and real systems are computable approximations of it. A *Gödel machine* rewrites its own code only when it can *prove* the rewrite raises expected utility.

**Recent results.** Theoretically active, empirically marginal. Hutter, Quarel & Catt published the textbook *An Introduction to Universal Artificial Intelligence* (2024). New arXiv work reframes AIXI's objective — **"Universal AI maximizes Variational Empowerment"** ([2502.15820](https://arxiv.org/abs/2502.15820)) — and **Self-AIXI** learns a model of *itself* to predict its own future behavior instead of exhaustively planning, a step toward computability; a 2026 **"Model-Free Universal AI"** ([2602.23242](https://arxiv.org/abs/2602.23242)) continues the approximation line.

**The consequential real-world descendant is the Darwin Gödel Machine** ([2505.22954](https://arxiv.org/abs/2505.22954), Sakana/UBC/Vector): it **drops Schmidhuber's formal-proof requirement** (intractable) and substitutes **Darwinian empirical validation** — propose code patches, test on real benchmarks, archive winners. Results: self-improved **20.0% → 50.0% on SWE-bench** and **14.2% → 30.7% on Polyglot**, beating hand-designed agents. Best empirical evidence to date that self-referential self-improvement yields real gains.

**Evidence quality: theory HIGH-rigor / LOW-applicability; DGM MEDIUM.** *Criticism:* AIXI is incomputable and reward-dependent; the proof requirement is why no Gödel machine was built for 20 years — DGM works precisely by abandoning the theory's defining feature.

## 6. Open-endedness & AI-generating algorithms (AI-GAs)

**Core hypothesis (the most serious challenger to pure scaling).** Human knowledge came from an *open-ended* process endlessly generating novel, learnable challenges; ASI therefore requires a system that keeps producing artifacts that are **novel *and* learnable** to an observer — not one static trained model. Clune's "AI-GAs" learn the algorithm, architectures, and environments jointly.

**Strongest recent result.** DeepMind's position paper **"Open-Endedness is Essential for Artificial Superhuman Intelligence"** ([2406.04268](https://arxiv.org/abs/2406.04268); Hughes, Dennis, Parker-Holder, Rocktäschel et al., ICML 2024 oral) gives the first crisp formal definition (novelty + learnability from an observer's view) and argues foundation models finally supply the "interestingness" signal earlier open-ended search (POET, quality-diversity) lacked. The **OMNI / OMNI-EPIC** line ([2306.01711](https://arxiv.org/abs/2306.01711), [2405.15568](https://arxiv.org/abs/2405.15568)) uses foundation models as "models of human notions of interestingness" to auto-generate curricula and even *code new environments*. The Darwin Gödel Machine is itself an open-ended evolutionary archive.

**Evidence quality: MEDIUM and rising** — real theory plus working systems that generate their own tasks; the clearest recent momentum outside scaling. *Criticism:* quality-diversity has documented scaling/coverage limits ([2407.17515](https://arxiv.org/abs/2407.17515)); "interestingness" grounded in a foundation model may inherit rather than transcend LLM limits.

## 7. Program synthesis & the skill-acquisition view (ARC lineage)

**Core hypothesis (Chollet).** Intelligence is *skill-acquisition efficiency* — how few examples you need for novelty — not skill itself. Test bed: **ARC-AGI**, built to resist memorization.

**Where it stands (2025, primary numbers).** ARC Prize 2025 ([2601.10904](https://arxiv.org/abs/2601.10904)): 1,455 teams, 15,154 entries. Top ARC-AGI-2 private-set score reached only **24%** (NVIDIA NVARC, a **4B model using synthetic data + test-time training**, $0.20/task); 2nd 16.5%, 3rd 12.6%. The **85% grand prize went unclaimed a second year**; the human panel baseline is ~60%+ — a large machine-human gap on cheap-for-humans novelty persists. Winning methods are **neurosymbolic**: test-time training, program synthesis, induction+transduction hybrids ([BARC 2412.04604](https://arxiv.org/abs/2412.04604); [MADIL/MDL 2505.01081](https://arxiv.org/abs/2505.01081)). DreamCoder's library-learning descendant **LILO** ([2310.19791](https://arxiv.org/abs/2310.19791), MIT) pairs an LLM synthesizer with the Stitch compressor + auto-docs and beats DreamCoder.

**Evidence quality: HIGH as a diagnostic, LOW as a path.** ARC is the sharpest falsifier of "scaling = intelligence," but no synthesis system is near general, and ARC-AGI-3 (agentic) already moved the target ([2603.24621](https://arxiv.org/abs/2603.24621)). *Criticism:* synthesis stays brittle/narrow, and top ARC results now *borrow* test-time compute from the mainstream stack.

## 8. System-2 / causal deep learning (Bengio lineage)

**Core hypothesis.** Current nets do System-1 (associative); AGI needs System-2 (deliberate, causal, compositional). Program: **GFlowNets** (amortized Bayesian sampling of diverse hypotheses in proportion to reward), **causal representation learning**, **consciousness prior** (sparse few-variable reasoning).

**Where it stands.** GFlowNets became a real tool for **drug/molecule discovery, biological sequence design, causal structure learning, combinatorial optimization** ([SynGFN, *Nature Comp. Sci.* 2025](https://www.nature.com/articles/s43588-025-00902-w); [GFlowNet Foundations, JMLR](https://jmlr.org/papers/v24/22-0364.html)), but documented **scalability limits** — hard exploration, credit assignment, unstable backward-policy learning at scale ([2411.05899](https://arxiv.org/abs/2411.05899)) — keep them a discovery tool, not a general-reasoning route. Bengio's biggest 2025 move is **safety, not capability**: **"Scientist AI"** ([2502.15657](https://arxiv.org/abs/2502.15657)) — a deliberately **non-agentic** system that only builds a Bayesian world model and makes calibrated predictions, no persistent goals or situational awareness, supervised not RL, so it "can never develop its own objectives." He launched nonprofit **LawZero** (6/2025, ~$30M), an 18-month program to prove non-agentic AI viable at small scale.

**Evidence quality: GFlowNets MEDIUM (real but niche); Scientist AI LOW/early.** *Criticism:* causal representation learning under-delivers on general tasks; critics argue a sufficiently capable predictor is instrumentally close to an agent.

## 9. Brain-inspired programs

- **(a) Active inference / Free-Energy Principle (Friston).** One principle — minimize variational free energy (prediction error) via perception + action — for brains and agents; 2025 work folds it into Numenta's neocortex model ([2506.21554](https://arxiv.org/abs/2506.21554)). *Evidence: LOW at scale* — elegant, empirically small, nothing competitive with deep RL.
- **(b) Thousand Brains Project (Numenta).** Neocortex = thousands of near-identical cortical columns each learning full sensorimotor object models via reference frames; intelligence is voting among them. Open-sourced **"Monty"** (MIT license, 11/2024), now an independent nonprofit. *Evidence: LOW* — genuinely different, biologically grounded, continual/sensorimotor, but no benchmark showing scale.
- **(c) Backprop alternatives — predictive coding & forward-forward.** Local, biologically-plausible learning for neuromorphic hardware. 2025: forward-forward SNNs beat prior FF-SNNs on static data with lighter nets ([2502.20411](https://arxiv.org/abs/2502.20411)); predictive coding can equal backprop updates but is **provably lower-bounded by backprop in time complexity** ([Neural Computation](https://direct.mit.edu/neco/article/35/12/1881/117833)). *Evidence: LOW-MEDIUM* — an energy/hardware story, not a capability path.
- **(d) Whole-brain emulation.** The **State of Brain Emulation Report 2025** ([2510.15745](https://arxiv.org/abs/2510.15745)) reframes WBE from "if" to "how fast": two full adult *Drosophila* connectomes reconstructed (~3 orders past *C. elegans*); cost/neuron fell ~$16,500 → ~$100. But projected **mouse ~2034, marmoset ~2044, human later**, and the bottleneck is now *functional recording* (structure maps faster than activity). *Evidence: MEDIUM on trajectory; not a near-term ASI route.*

## 10. Collective / multi-agent & cultural-evolution routes

**Core hypothesis.** Superintelligence may emerge from *populations* of interacting agents accumulating culture, not a monolith (open-endedness at societal scale). 2025 literature is dominated by the **risk** framing — **"Multi-Agent Risks from Advanced AI"** ([2502.14143](https://arxiv.org/abs/2502.14143), Cooperative AI Foundation) catalogs miscoordination, collusion, emergent conflict. *Evidence: LOW as a capability path, MEDIUM as a risk surface;* little evidence swarms beat a single strong reflective agent today.

## 11. Agent foundations & guaranteed-safe AI

- **(a) MIRI-style embedded agency / Löbian obstacle.** A theory of agents embedded in their environment that can trust successors they build — blocked by the **Löbian obstacle** (Löb's theorem limits self-trust). *Status: largely stalled* — MIRI acknowledged its core program "largely failed," wound down the Agent Foundations team, and pivoted to policy/advocacy; tiling-agent formalism is dormant. *Rigorous but stagnant.*
- **(b) Guaranteed-Safe / provably-safe AI.** Dalrymple, Bengio, Russell, Tegmark, Tenenbaum, Omohundro et al. ([2405.06624](https://arxiv.org/abs/2405.06624)): ship high-stakes AI with a **world model + formal safety specification + verifier** producing an auditable proof certificate. Most *active* theoretical-safety program; underpins Scientist AI and Tegmark's agenda. *Evidence: MEDIUM as direction, LOW as deployable method* — the paper concedes the hard parts are accurate world models and scaling formal verification.
- **(c) Singular Learning Theory (SLT) for interpretability.** Nets are *singular* models, so classical learning theory fails; the **local learning coefficient (RLCT)** measures effective complexity and predicts **phase transitions** (grokking). 2025 physics-inspired work validates Arrhenius-style free-energy dynamics on grokking + toy-superposition models ([2512.00686](https://arxiv.org/abs/2512.00686)). *Evidence: MEDIUM and rising* — a rare rigorous handle on emergence, still toy-scale.

## 12. Tensor-structured representations vs. flat vector embeddings

> **This section is adversarially verified** (dedicated deep-research pass: 111 agents, 6 angles, 28 sources, 122 claims → top 25 verified; **21 confirmed, 4 refuted**). ✓ = 3-vote confirmed; ✗ = refuted and must not be cited.

**Core question.** Are tensors (higher-order, structured) a better substrate than flat vectors for reasoning, compositionality, and generality — or just a niche tool? The verified answer is a **split verdict: a strong niche tool for compression, interpretability, and mid-scale attention; real-but-unsettled for compositional reasoning; not a proven road to general intelligence.**

**(a) Tensor-Product Representations (Smolensky's TPR) → compositional systematicity.**
- ✓ TPR-enriched transformers help on real tasks: a **TP-Transformer** encoding syntax (role vectors) and semantics (filler vectors) separately, bound by tensor product, beats both a standard Transformer and the original TP-Transformer on abstractive summarization ([arXiv 2106.01317](https://arxiv.org/abs/2106.01317)).
- ✓ Better decomposition helps: the **AID module** cuts word-error-rate on systematic bAbI (FWM 2.85%→1.21%; TPR-RNN 8.74%→5.61%, though with overlapping variance) ([arXiv 2406.01012](https://arxiv.org/abs/2406.01012)).
- ✓ A TPR-linked **Homomorphism Error** metric *predicts* OOD compositional generalization (R²=0.73) and, as a training regularizer, *causally* improves it (p=0.023) — **but** ✗ the claim that this formally connects TPR theory to transformer internals was **refuted 1–2**; treat the theory framing cautiously. Toy SCAN-scale only ([arXiv 2601.18858](https://arxiv.org/abs/2601.18858)).
- ✓ Big caveat from a 2025 survey: most reported "systematicity" is **behavioural** (output accuracy), not the **representational** systematicity Fodor & Pylyshyn demanded — models often use non-systematic shortcuts, so TPR benchmark wins don't prove genuine structure ([arXiv 2506.04461](https://arxiv.org/abs/2506.04461)).

**(b) Tensor networks from physics (MPS/tensor-train, Tucker, MPO) → compression at scale.**
- ✓ **Tensor Product Attention (T6)** is the strongest positive result: factorizing Q/K/V into contextual low-rank tensors shrinks the KV cache and **matches or beats MHA/MQA/GQA/MLA up to 1.5B params** (NeurIPS 2025 Spotlight; [arXiv 2501.06425](https://arxiv.org/abs/2501.06425)). Caveat: authors' own comparison, tops out at 1.5B — far below frontier.
- ✓ Quantum-inspired TN compression is real: **CompactifAI** cuts LLaMA-7B memory up to 93% / params 70% for a 2–3% accuracy drop (but the 93% needs TN **plus quantization** + healing epochs; vendor-reported). TensorGPT compresses embeddings training-free via tensor-train ([arXiv 2401.14109](https://arxiv.org/abs/2401.14109)) — ✗ but its headline **39–65× embedding-compression** ratio was **refuted 0–3**; cite the mechanism, not the number.
- ✓ **The central honest negative result:** tested rigorously as post-training LLM compressors, **tensor formats (TT/Tucker) do NOT beat plain matrix low-rank** at matched ratios — across dense (GPT-J 6B, LLaMA2 7B) *and* MoE (Qwen3-30B, GPT-OSS-20B) models, because Tucker/TT distort spectral subspaces; MoE experts simply "do not live in a low-rank subspace" ([arXiv 2606.03465](https://arxiv.org/abs/2606.03465)).
- ✓ Serving gains need heavy engineering: TN compression of Qwen3-32B lifts throughput only ~40→50 TPS, reaching ~75 only when freed VRAM enables speculative decoding — the **hardware-inefficiency criticism is real**, custom kernels required ([arXiv 2602.01613](https://arxiv.org/abs/2602.01613)). ✗ Two of that paper's precise VRAM/quality figures were refuted 1–2.

**(c) Tensor networks for interpretability & theory (the most intellectually promising thread).**
- ✓ **Bond dimension** gives a single interpretable knob for the compression–accuracy tradeoff (MPO on toy GPT: χ=4→13×, χ=32→2.5×) — but demonstrated only at ~1M-param toy scale ([arXiv 2603.28534](https://arxiv.org/abs/2603.28534)); ✗ its 97.7%-retention headline was refuted 1–2.
- ✓ **Grokking can be identified with an entanglement dynamical transition** in the MPS's underlying quantum many-body system, and gradient training induces **implicit regularization toward low rank** — giving entanglement/bond-dimension/rank as principled expressivity & generalization measures ([arXiv 2503.10483](https://arxiv.org/abs/2503.10483), [arXiv 2408.02111](https://arxiv.org/abs/2408.02111)). This is the cleanest link to the singular-learning-theory/emergence agenda (§11c). Caveat: single 2025 numerical preprints, not established for general transformers.

**(d) Hyperdimensional computing / VSA / holographic representations — COVERAGE GAP.** Despite being explicitly targeted, **zero claims on HDC/VSA/HRR survived verification** — so this report *cannot* assess binding capacity, one-shot/noise-robust learning, or neuromorphic results for that sub-thread. Treat my earlier informal note on holographic computing as unverified. (Tree Tensor Networks, MERA, and PEPS specifically also returned no verified evidence.)

**Verdict (evidence quality):**
- **Genuine momentum, MEDIUM-HIGH evidence:** attention/parameter compression at real (≤1.5B) scale (T6), and tensor-network *theory/interpretability* (entanglement ↔ generalization).
- **Real but modest, toy/mid-scale:** TPR for compositional reasoning — measurable gains, but likely behavioural not representational.
- **Demonstrably NOT winning:** tensors as general-purpose LLM compressors (lose to matrix low-rank) and as free serving speedups (need custom kernels).
- **Bottom line:** *not overhyped, not a proven path to general intelligence.* "Tensors instead of vectors" is a **strong niche tool with unsettled promise for compositionality** — a complement to the mainstream stack, not a replacement. The open question that would change this: does T6's tensor-factorized advantage survive at frontier scale and independent reproduction, or vanish the way TT/Tucker vanish against matrix low-rank?

---

# Part III — Updated momentum assessment (both passes)

**Genuine recent momentum (2024–2026):**
1. **RL post-training + test-time compute** (§1) — only path with predictive scaling laws; HIGH evidence.
2. **Open-endedness / AI-GAs + Darwin Gödel Machine** (§5–6) — real theory *and* working self-improving systems with measured gains; the most serious heterodox challenger.
3. **ARC / program synthesis as a diagnostic** (§7) — sharpest falsifier of "scaling = intelligence"; the 24%-vs-~60% human gap is the field's cleanest scoreboard.
4. **Guaranteed-Safe AI + Scientist AI + SLT** (§8, §11) — where serious academics (Bengio, Russell, Tegmark) are actually placing theoretical-safety bets.

**Slow / niche but alive:** GFlowNets (useful, niche), Thousand Brains & active inference (distinct paradigm, unproven at scale), backprop alternatives (energy story), whole-brain emulation (real trajectory, decades out), tensor/TPR representations (interpretability edge).

**Largely stagnant:** classical AIXI/Gödel-machine formalism (superseded in practice by empirical DGM), MIRI-style agent foundations (self-declared "largely failed"), pure multi-agent "cultural" routes (now mostly a risk literature).

**Convergence worth flagging:** the mainstream (RSI, Sakana) and the heterodox (AI-GAs, DGM) are approaching **the same object from opposite directions** — a system that generates its own novel, learnable challenges and rewrites itself to meet them. The undecided empirical question that would most move the debate: does such a loop **compound** (true takeoff) or **saturate** (the coverage/efficiency ceilings of §1, the recursive-instability of self-generated data)?
