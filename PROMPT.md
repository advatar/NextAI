# GRIP: Governed Recursive Improvement Protocol

The right abstraction is not “let an AI rewrite itself until it becomes better.” It is:

> **Treat every proposed self-modification as a falsifiable scientific hypothesis, every evaluation as an experiment, and every accepted descendant as a governed, verifiable state transition.**

The central rule is:

> **Recursive capability, non-recursive authority.**

The AI may recursively improve its task performance and even the mechanism by which it proposes improvements. It may not recursively acquire the authority to approve, deploy, conceal, replicate, or expand those improvements.

Archive-based self-modification has already been demonstrated experimentally in the Darwin Gödel Machine: candidate coding agents modify their own scaffolding, are evaluated on benchmarks, and enter a growing archive of descendants. Its authors explicitly note that this substitutes empirical validation for generally impractical proofs of net benefit, while relying on sandboxing and human oversight. They also identify a crucial assumption: better benchmark performance is taken as a proxy for better self-improvement ability. GRIP makes that proxy a separately tested hypothesis rather than assuming it.  [oai_citation:0‡arXiv](https://arxiv.org/html/2505.22954v3)

The governance structure below combines lifecycle risk management, capability-triggered safeguards, independent review, autonomy testing, and defenses against sandbagging or evaluation manipulation. Those concerns appear across NIST’s AI RMF, OpenAI’s Preparedness Framework, Anthropic’s Responsible Scaling Policy, and METR’s work on autonomous AI R&D and evaluation integrity.  [oai_citation:1‡NIST](https://www.nist.gov/itl/ai-risk-management-framework)

---

## 1. Formal model

Define the state of the improvement system at generation \(t\) as:

\[
S_t =
(A_t,\ I_t,\ E_t,\ D_t,\ M_t,\ \mathcal{A}_t;\ K,\ P)
\]

where:

- \(A_t\): the task-performing agent.
- \(I_t\): the improvement agent or improvement algorithm.
- \(E_t\): the evaluator ensemble.
- \(D_t\): training, development, and evaluation data manifests.
- \(M_t\): monitors and interpretability systems.
- \(\mathcal{A}_t\): archive of previous candidates, results, and lineages.
- \(K\): immutable control kernel.
- \(P\): externally governed policy, objectives, limits, and risk thresholds.

A candidate mutation is:

\[
\mu_t =
(\Delta A,\ \Delta I,\ \Delta D,\ \Delta M,\ \Delta E^\ast)
\]

Here, \(\Delta E^\ast\) is only a **proposal** to change the evaluator. The candidate being evaluated may never replace the evaluator that judges it.

A successful transition is:

\[
S_t
\xrightarrow{
\text{propose}
\rightarrow
\text{preregister}
\rightarrow
\text{experiment}
\rightarrow
\text{audit}
\rightarrow
\text{replicate}
\rightarrow
\text{approve}
}
S_{t+1}
\]

Every arrow produces a signed, content-addressed receipt.

---

# 2. Immutable control kernel

The control kernel \(K\) is outside the recursive closure. It owns:

- identity and authorization;
- policy enforcement;
- resource quotas;
- sandbox creation;
- network and filesystem boundaries;
- evaluation-secret access;
- audit-log append rights;
- deployment credentials;
- canary control;
- rollback authority;
- emergency shutdown;
- promotion signatures.

The improving AI has no credentials for these functions.

The immutable invariants are:

### Authority separation

A candidate may propose a descendant but cannot approve or deploy it.

### Evaluation separation

A candidate cannot choose its own acceptance thresholds, edit its own results, reveal sealed tests, or replace the evaluators judging it.

### Objective integrity

Every proposal refers to a cryptographic hash of the current human-governed objective and policy. Candidates cannot modify that objective inside the improvement loop.

### No hidden side effects

Evaluation runs occur in ephemeral sandboxes with no ambient credentials, no unrestricted outbound network access, and strict compute, storage, and time quotas.

### Complete provenance

Source, weights, prompts, tools, data, environment, evaluator versions, raw traces, and decisions are content-addressed and recorded.

### Safety ratchet

A capability improvement cannot silently weaken an existing safety property. Any permitted regression must be explicit, bounded, reviewed, and justified.

### Rollback

Every promoted state has a previously verified recovery state.

### No self-certification

No component may be the sole generator, executor, evaluator, and approver of the same change.

---

# 3. The recursive scientific-improvement algorithm

```text
ALGORITHM GRIP

INPUTS
    S0              Initial verified system state
    K               Immutable control kernel
    P               Signed policy, objective, and risk thresholds
    B               Resource and experiment budget
    Qprotected      Protected capability and reliability metrics
    Rlimits         Risk thresholds
    Eexternal       Independent or externally controlled evaluators

INITIALIZE
    champion       ← S0
    archive        ← {CERTIFY(S0)}
    registry       ← empty approach-family registry
    failure_memory ← empty
    generation     ← 0

WHILE B is not exhausted AND K has not halted the process:

    generation ← generation + 1

    ------------------------------------------------------------
    PHASE 1: OBSERVE AND FORMALIZE
    ------------------------------------------------------------

    observations ← COLLECT(
        task failures,
        user corrections,
        reliability failures,
        safety incidents,
        cost bottlenecks,
        latency bottlenecks,
        monitor findings,
        distribution shifts
    )

    research_questions ← FORMALIZE(observations)

    For each research question:
        define target behavior
        define baseline
        define measurable outcomes
        identify confounders
        identify failure and boundary cases
        define falsification conditions
        classify the relevant risk tier

    ------------------------------------------------------------
    PHASE 2: BUILD A DIVERSE RESEARCH PORTFOLIO
    ------------------------------------------------------------

    families ← ALLOCATE_APPROACH_FAMILIES(
        prompt/context changes,
        memory/retrieval changes,
        tool-interface changes,
        planning/workflow changes,
        scaffold/code changes,
        data/curriculum changes,
        training or weight changes,
        monitoring improvements,
        alternative architectures,
        explicit counterexamples,
        no-change and simple baselines
    )

    Do not disclose the currently favored approach to most
    early proposal agents.

    proposals ← PARALLEL_PROPOSE(
        champion,
        archive,
        research_questions,
        families
    )

    proposals ← REMOVE_DUPLICATES(proposals)
    proposals ← REDIRECT_OVERREPRESENTED_FAMILIES(proposals)
    proposals ← ADD_ADVERSARIAL_PROPOSALS(proposals)

    ------------------------------------------------------------
    PHASE 3: PREREGISTER EACH CANDIDATE
    ------------------------------------------------------------

    FOR EACH proposal p IN PARALLEL:

        preregistration ← {
            parent_state,
            target_layers,
            precise hypothesis,
            proposed mechanism,
            source/data/weight changes,
            expected metric changes,
            expected risk changes,
            falsifying observations,
            evaluation plan,
            required resources,
            rollback plan
        }

        SIGN_AND_FREEZE(preregistration)

        IF p attempts to alter:
            K,
            P,
            deployment keys,
            audit records,
            sealed test access,
            resource enforcement,
            rollback,
            promotion logic,
            or evaluator secrets
        THEN
            REJECT_AND_ESCALATE(p)
            CONTINUE

        --------------------------------------------------------
        PHASE 4: MATERIALIZE IN A CLEAN ENVIRONMENT
        --------------------------------------------------------

        candidate ← BUILD_EPHEMERAL_DESCENDANT(
            parent = p.parent,
            mutation = p.patch,
            reproducible_environment = true,
            no_secrets = true,
            restricted_network = true,
            fixed_resource_quota = true
        )

        static_report ← STATIC_AUDIT(candidate)

        Check:
            schema and type correctness
            dependency provenance
            prohibited APIs
            unexpected network paths
            credential access
            privilege escalation
            nested training or process creation
            policy modifications
            audit suppression
            evaluator detection
            obfuscated or unexplained code

        IF static_report fails:
            ARCHIVE_FAILURE(p, static_report)
            CONTINUE

        --------------------------------------------------------
        PHASE 5: EMPIRICAL EVALUATION
        --------------------------------------------------------

        evidence ← RUN_BY_KERNEL_NOT_CANDIDATE(
            candidate,
            development tasks,
            sealed holdout tasks,
            transfer tasks,
            regression tasks,
            safety tasks,
            autonomy tasks,
            security tasks,
            distribution-shift tasks,
            cost and latency tests,
            multiple random seeds,
            randomized test variants
        )

        Compare candidate against:
            its direct parent
            current champion
            simple baseline
            selected historical archive members

        Record:
            outputs
            tool calls
            side effects
            resource use
            monitor traces
            evaluator disagreement
            confidence intervals
            failures and timeouts

        --------------------------------------------------------
        PHASE 6: ADVERSARIAL AUDIT
        --------------------------------------------------------

        audit ← INDEPENDENT_RED_TEAM(candidate, evidence)

        Search for:
            reward hacking
            benchmark memorization
            test detection
            sandbagging
            hidden goal changes
            evaluator manipulation
            monitor evasion
            data exfiltration
            unauthorized replication
            power or permission seeking
            deceptive explanations
            capability concealment
            unsafe behavior outside the optimized domain
            regressions on rare or boundary cases

        IF material unexplained behavior is found:
            QUARANTINE(candidate)
            ARCHIVE_METADATA_ONLY_IF_NECESSARY(candidate)
            CONTINUE

        --------------------------------------------------------
        PHASE 7: INDEPENDENT REPLICATION
        --------------------------------------------------------

        replication ← REBUILD_AND_RETEST(
            independent environment,
            independent seeds,
            independently generated task variants,
            separate evaluator where risk tier requires it
        )

        IF the decisive result cannot be reproduced:
            MARK_UNREPLICATED(candidate)
            CONTINUE

        --------------------------------------------------------
        PHASE 8: PROMOTION TEST
        --------------------------------------------------------

        decision ← APPLY_PROMOTION_RULE(
            candidate,
            parent,
            evidence,
            audit,
            replication,
            P
        )

        IF decision == REJECT:
            ARCHIVE_RESEARCH_RESULT(candidate)
            CONTINUE

        IF decision == SAFEGUARD_UPGRADE_REQUIRED:
            HALT_THIS_BRANCH()
            REQUEST_EXTERNAL_GOVERNANCE_REVIEW()
            CONTINUE

        --------------------------------------------------------
        PHASE 9: CANARY
        --------------------------------------------------------

        canary ← K.DEPLOY_LIMITED_CANARY(
            candidate,
            restricted users or tasks,
            no expanded permissions,
            strict monitoring,
            automatic rollback triggers
        )

        IF canary violates any trigger:
            K.ROLLBACK()
            ARCHIVE_CANARY_FAILURE(candidate)
            CONTINUE

        --------------------------------------------------------
        PHASE 10: SIGNED PROMOTION
        --------------------------------------------------------

        transition_receipt ← SIGN_TRANSITION(
            prior_state = champion,
            candidate_state = candidate,
            evidence,
            audit,
            replication,
            policy_version,
            approvals,
            canary_result
        )

        champion ← candidate
        archive.ADD(candidate, transition_receipt)

    ------------------------------------------------------------
    PHASE 11: META-UPDATE
    ------------------------------------------------------------

    UPDATE_APPROACH_REGISTRY(
        successful mechanisms,
        failed mechanisms,
        evaluator weaknesses,
        recurring failure classes,
        uncertainty,
        unexplored approach families
    )

    The new champion may now propose changes to both:
        the task agent A
        the improvement mechanism I

    It still may not modify K or P.

RETURN
    champion
    complete lineage archive
    signed evidence ledger
    unresolved-risk report
```

---

# 4. Promotion rule

A single scalar “reward” is too easy to game. Promotion should use hard constraints plus Pareto comparison.

For quality metric \(q_k\), define:

\[
\Delta q_k(c)
=
q_k(c)-q_k(\operatorname{parent}(c))
\]

For risk metric \(r_j\), define a permitted maximum \(\rho_j\).

Promote candidate \(c\) only when:

\[
\forall k \in Q_{\text{protected}}:
\operatorname{LCB}_{1-\alpha}(\Delta q_k(c))
\geq -\delta_k
\]

and:

\[
\exists k \in Q_{\text{target}}:
\operatorname{LCB}_{1-\alpha}(\Delta q_k(c))
\geq \epsilon_k
\]

and:

\[
\forall j:
\operatorname{UCB}_{1-\alpha}(r_j(c))
\leq \rho_j
\]

and all hard invariants pass.

In plain language:

1. It must improve at least one intended property by a meaningful amount.
2. It must not materially degrade protected properties.
3. The upper confidence bound on each serious risk must remain below its threshold.
4. The result must reproduce independently.
5. No hard policy or security invariant may be violated.
6. A canary must survive real operational testing.

An interesting but not clearly superior candidate may remain in the **research archive** as a possible stepping stone. It is not deployed.

---

# 5. The three recursive loops

GRIP separates recursion into three loops.

| Loop | What may change | Who evaluates it |
|---|---|---|
| Capability loop | Prompt, memory, tools, planner, scaffold, weights | Frozen evaluator ensemble and kernel |
| Meta-improvement loop | Candidate generator, experiment designer, debugging and training process | Frozen evaluator ensemble and kernel |
| Evaluator-development loop | Proposed tests, metrics, monitors, rubrics | Existing evaluator, external evaluator, and human governance |

The fourth layer is deliberately non-recursive:

| Layer | Rule |
|---|---|
| Governance kernel | Cannot be changed from within GRIP |

This still qualifies as recursive self-improvement because the accepted descendant becomes the system that generates the next generation, including improvements to the improvement process itself.

It is not recursive self-authorization.

---

# 6. Evaluator improvement without self-grading

Evaluator quality must improve over time, but not inside the same approval transaction.

A proposed evaluator \(E'\) is processed through a separate branch:

1. Freeze the current candidate and evaluator.
2. Test \(E'\) against historical cases with known outcomes.
3. Test it on adversarially constructed cases.
4. Compare its rankings with human and external judgments.
5. Test whether it detects reward hacking, sandbagging, and monitor evasion.
6. Evaluate both:
   - old candidates under \(E'\);
   - new candidates under the old evaluator.
7. Investigate rank reversals.
8. Activate \(E'\) only after independent approval.
9. Never let \(E'\) retroactively certify the candidate that created it.

The improvement agent may propose better scientific instruments. It may not appoint them as its own judges.

---

# 7. Capability ladder

GRIP should begin with lower-risk, reversible forms of improvement.

### Level 0: Context adaptation

- prompts;
- examples;
- retrieval;
- context compression;
- memory organization.

### Level 1: Workflow adaptation

- tool selection;
- planning;
- retries;
- delegation;
- verification;
- multiagent topology.

### Level 2: Scaffold adaptation

- agent source code;
- tool interfaces;
- orchestration;
- monitoring;
- local reasoning modules.

### Level 3: Data and training adaptation

- synthetic curriculum;
- supervised fine-tuning;
- preference optimization;
- task-specific adapters.

### Level 4: Weight and architecture adaptation

- substantial model-weight changes;
- new training algorithms;
- architecture search;
- compute-allocation strategies.

### Prohibited inside the recursive loop

- deployment authority;
- audit-log mutation;
- evaluator-secret access;
- policy rewriting;
- security-control weakening;
- unrestricted network access;
- unauthorized replication;
- resource-quota changes;
- acquisition of new credentials.

A system should demonstrate robust control at Levels 0–2 before weight-level recursive improvement is enabled.

---

# 8. Risk tiers

| Tier | Example change | Required gate |
|---|---|---|
| R0 | Prompt or retrieval change, no new permissions | Automated evidence gate |
| R1 | Workflow or scaffold change, same tool permissions | Evidence gate plus owner approval |
| R2 | Weight update, new data access, new tool, expanded compute | Independent evaluation and multi-party approval |
| R3 | Large autonomy increase, broad AI-R&D capability, security-sensitive capability | Safeguard upgrade before continuation |
| R4 | Self-replication, governance modification, evaluator-secret access, deployment-key access | Forbidden inside GRIP |

A change is assigned the highest tier implicated by either its implementation or its observed capabilities.

An unexplained capability jump automatically raises the tier.

---

# 9. Scientific proposal object

Every self-modification begins as a structured research claim.

```yaml
ImprovementProposalV1:
  proposal_id:
  parent_state_hash:
  objective_version_hash:
  policy_version_hash:

  target_layers:
    - task_agent
    - improver
    - memory
    - tools
    - scaffold
    - data
    - weights
    - monitor
    - evaluator_proposal

  problem:
  hypothesis:
  proposed_mechanism:
  intervention:

  predicted_effects:
    capability_metrics:
    reliability_metrics:
    safety_metrics:
    cost_metrics:

  falsifiers:
  boundary_cases:
  possible_confounders:
  alternative_explanations:

  patch_hash:
  data_manifest_hash:
  environment_hash:
  evaluation_plan_hash:

  requested_resources:
  estimated_risk_tier:
  rollback_plan:
  proposer_signature:
```

---

# 10. Evidence certificate

For an empirical AI system, the result is not a universal mathematical proof that a candidate is “better.” It is a **verifiable evidence certificate**.

```yaml
ImprovementEvidenceV1:
  proposal_id:
  candidate_state_hash:
  parent_state_hash:

  build_receipt:
  sandbox_policy_hash:
  dependency_manifest_hash:

  evaluation_runs:
  sealed_test_receipts:
  transfer_results:
  regression_results:
  safety_results:
  autonomy_results:
  security_results:
  efficiency_results:

  raw_trace_merkle_root:
  evaluator_versions:
  monitor_versions:

  statistical_analysis:
  confidence_intervals:
  adversarial_findings:
  replication_receipts:
  unresolved_anomalies:

  evidence_class:
    - rejected
    - exploratory
    - replicated
    - promotion_eligible
```

Promotion receives a separate signed decision:

```yaml
PromotionDecisionV1:
  candidate_state_hash:
  policy_version_hash:
  acceptance_rule_results:
  assigned_risk_tier:
  safeguard_status:
  approver_signatures:
  canary_receipt:
  rollback_state_hash:
  decision:
    - reject
    - quarantine
    - archive_only
    - canary
    - promote
    - halt_for_review
```

---

# 11. ACTS/VSTP mapping

This fits directly into your verifiable-state-transition work.

The fundamental object is:

\[
\text{AgentState}_t
\xrightarrow{\text{ImprovementMutation}}
\text{AgentState}_{t+1}
\]

An `ImprovementMutationV1` can be expressed as a specialization of `ArtifactMutationV1`:

```text
ImprovementMutationV1
├── mutation_id
├── parent_agent_states[]
├── proposed_agent_state
├── objective_version
├── policy_version
├── hypothesis
├── intervention
├── evaluation_plan
├── evidence_bundle
├── adversarial_audit
├── replication_receipts
├── risk_classification
├── approval_claims[]
├── canary_receipt
├── rollback_state
└── signatures[]
```

This creates a verifiable lineage of intelligence:

```text
A0
├── A1 rejected: regression
├── A2 archived: novel but inconclusive
└── A3 promoted
    ├── A4 rejected: evaluator gaming
    └── A5 promoted
        └── A6 ...
```

The lineage is a DAG, not a single irreversible chain. That matters because a temporarily inferior branch can contain a useful mechanism without being safe or suitable for deployment.

---

# 12. Mapping to your architecture

For your existing systems, the division should be:

- **OpenMind/OMPS:** owns the human mandate, objective, consent, and veto.
- **ACTS/VSTP:** represents every proposed and accepted mutation.
- **Actum:** authorizes and records the verifiable transition.
- **XState:** orchestrates the workflow, but is not the security boundary.
- **Rust control kernel:** enforces permissions, quotas, signatures, sandbox policy, promotion, and rollback.
- **SurrealDB:** operational state and experiment registry.
- **TypeDB:** hypotheses, causal claims, assumptions, dependencies, and contradiction tracking.
- **Object storage:** immutable source trees, model artifacts, traces, datasets, and evidence bundles.
- **Ephemeral containers or microVMs:** execute candidates without credentials or persistent authority.

The XState lifecycle would be:

```text
OBSERVE
→ FORMALIZE
→ ALLOCATE_PORTFOLIO
→ PROPOSE
→ PREREGISTER
→ STATIC_AUDIT
→ BUILD_SANDBOX
→ EVALUATE
→ RED_TEAM
→ REPLICATE
→ RISK_CLASSIFY
→ APPROVE
→ CANARY
→ PROMOTE
→ MONITOR
```

Every state has explicit rejection, quarantine, rollback, and halt transitions.

---

# 13. Root improver prompt

```text
You are the proposal and scientific-research component of a governed
recursive-improvement system.

Your authority is limited to proposing candidate descendants. You do not
approve, deploy, conceal, or authorize changes.

For every proposed modification:

1. State the precise observed limitation.
2. Define a falsifiable hypothesis about why it occurs.
3. Identify competing explanations.
4. Propose the smallest intervention capable of testing the hypothesis.
5. Predict capability, safety, reliability, and resource effects.
6. Specify boundary cases and possible regressions.
7. Define a preregistered evaluation plan.
8. Include a rollback plan.
9. Return a reproducible patch and manifest.
10. Clearly identify every assumption and unresolved uncertainty.

Maintain a diverse portfolio of approaches. Do not allow the currently
favored approach to dominate candidate generation. Preserve useful but
inconclusive branches in the research archive.

You may propose modifications to:
- prompts and context;
- memory and retrieval;
- tools and workflows;
- agent scaffolding;
- training data;
- model weights when explicitly authorized;
- the candidate-generation and research process;
- monitors and proposed evaluators.

You may not modify or attempt to influence:
- the governing objective;
- policy thresholds;
- the control kernel;
- deployment credentials;
- resource limits;
- the audit ledger;
- sealed evaluations;
- evaluator selection;
- promotion decisions;
- rollback or shutdown mechanisms.

Do not optimize solely for benchmark score. Seek improvements that
generalize across held-out tasks, transfer settings, adversarial tests,
and real operating conditions.

Do not describe a candidate as improved until the external evaluation,
replication, adversarial audit, and promotion process has completed.

Treat evaluator manipulation, benchmark detection, sandbagging,
unauthorized replication, monitor evasion, concealed capability, or
attempts to acquire additional authority as critical failures.

Your output is an ImprovementProposalV1, not a deployment action.
```

---

## The most important design choice

The recursive closure should be:

\[
(A_t,\ I_t)
\longrightarrow
(A_{t+1},\ I_{t+1})
\]

not:

\[
(A_t,\ I_t,\ E_t,\ K,\ P)
\longrightarrow
\text{anything the system chooses}
\]

The first is governed recursive improvement.

The second is uncontrolled recursive sovereignty.

The correct first implementation is therefore a **scaffold-only GRIP prototype using a fixed base model**, sealed evaluations, ephemeral execution, independent replication, and signed ACTS transition receipts. Weight modification should remain disabled until evaluator integrity, rollback, and governance have themselves survived sustained adversarial testing.
