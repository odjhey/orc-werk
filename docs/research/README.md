---
id: RESEARCH-LINEAGE
type: reference
status: current
authority: informative
description: Research and project lineage that informed Orc Werk's contracts and product boundaries.
---

# Research lineage

Orc Werk did not begin from a blank-slate orchestration design. Its contracts emerged from research discussions about graph engineering, autonomous delivery loops, evaluator-driven work, long-running agent harnesses, and from operational lessons in Beads, zxro, Rozoro, no-mistakes, ACP/acpx, and related systems.

This document preserves that lineage so future maintainers can revisit the source ideas instead of treating the current contracts as unexplained local convention.

**These sources are informative, not normative.** Orc Werk's current contracts, invariants, scenarios, and accepted ADRs remain authoritative when a source evolves or disagrees with the product.

## Core research threads

### Autoresearch and bounded improvement loops

- Andrej Karpathy, **autoresearch** — <https://github.com/karpathy/autoresearch>

Why it matters: a deliberately constrained mutable surface, repeated experiments, an objective evaluator, comparable runs, and keep/revert iteration provide a minimal useful model for autonomous improvement. Orc Werk generalizes this idea from one optimization loop into work graphs containing bounded execution/assurance/recovery loops.

### Graph engineering

- Feng et al., **Graph Engineering in the Era of LLM Agents: From Individual Intelligence to System Intelligence**, arXiv:2608.21156 — <https://arxiv.org/abs/2608.21156>

Why it matters: complex autonomous work benefits from explicit task, coordination, and state graphs rather than relying on one agent's context as the system of record. This supports Orc Werk's WorkGraphPort, explicit fan-out/fan-in semantics, persistent state, and separation between system topology and individual executors.

### Loop engineering

- Lulla et al., **Loop Engineering: Building Blocks, Adoption, and Impact**, arXiv:2608.21884 — <https://arxiv.org/abs/2608.21884>

Why it matters: the study identifies recurring loop building blocks such as machine-checkable stop conditions, persistent state, verifier roles, budgets, and explicit human escalation. These ideas inform Orc Werk's bounded retry/replan posture, assurance separation, terminal conditions, and future self-healing model.

### Explicit state-driven workflows

- Wu et al., **StateFlow: Enhancing LLM Task-Solving through State-Driven Workflows**, arXiv:2403.11322 — <https://arxiv.org/abs/2403.11322>
- Reference implementation — <https://github.com/yiranwu0/StateFlow>

Why it matters: explicit states and transitions can be more reliable and cheaper to reason about than letting an agent improvise the entire workflow. Orc Werk therefore treats state transitions, facts, decisions, and effects as first-class contracts.

### Search over trajectories and workflows

- Zhou et al., **Language Agent Tree Search Unifies Reasoning Acting and Planning in Language Models**, arXiv:2310.04406 — <https://arxiv.org/abs/2310.04406>
- Zhang et al., **AFlow: Automating Agentic Workflow Generation**, arXiv:2410.10762 — <https://arxiv.org/abs/2410.10762>
- Hu, Lu, Clune, **Automated Design of Agentic Systems**, arXiv:2408.08435 — <https://arxiv.org/abs/2408.08435>
- Agrawal et al., **GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning**, arXiv:2507.19457 — <https://arxiv.org/abs/2507.19457>

Why they matter: retries need not mean repeating the same trajectory. These systems explore alternative trajectories, workflows, or agent designs and use execution feedback to select or evolve them. Orc Werk keeps retry, replan, graph mutation, and future meta-optimization as distinct seams so these strategies can evolve without changing execution providers.

## Harness and evaluation engineering

### Long-running harnesses and structured handoff

- Anthropic, **Effective harnesses for long-running agents** — <https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents>
- Anthropic, **Harness design for long-running application development** — <https://www.anthropic.com/engineering/harness-design-long-running-apps>

Why they matter: long-running work benefits from tractable decomposition, structured artifacts, independent evaluation, and careful testing of which harness assumptions remain load-bearing as models improve. Orc Werk keeps harness behavior outside the kernel and makes work/evidence state durable and explicit.

### Stable interfaces as harnesses change

- Anthropic, **Scaling Managed Agents: Decoupling the brain from the hands** — <https://www.anthropic.com/engineering/managed-agents>

Why it matters: model/harness behavior can improve quickly while stable interfaces remain valuable. This closely matches Orc Werk's rule that provider behavior is translated through stable ports and explicit capabilities rather than becoming core semantics.

### Outcome-oriented evaluation

- Anthropic, **Demystifying evals for AI agents** — <https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents>

Why it matters: the final environment or artifact state is a stronger source of truth than an agent saying it succeeded. This supports `P-003`, candidate-bound assurance, independent evidence, and the distinction between execution settlement and work acceptance.

### Structured code-review finding evaluation

Earlier Orc Werk research discussions surveyed code-review finding classification and converged on independent dimensions for **severity**, **disposition**, **category**, **confidence**, **lifecycle status**, **location**, and **evidence**.

The important lesson was not merely the enum values. It was the separation of concerns: severity describes consequence, disposition describes whether delivery may proceed, confidence describes reviewer certainty, and status describes lifecycle. Those dimensions must not be mechanically collapsed into one score or inferred from one another.

Orc Werk preserves this research result as the optional `EXT-REVIEW-FINDINGS-V1` (`review-findings/v1`) extension. This keeps structured review/routing information available without making code-review-specific fields mandatory in generic Assurance/Evidence.

## Operational/product lineage

### Beads / Gas City

- Beads documentation — <https://beads.gascity.com/>

Key lesson: durable dependency-aware work graphs, readiness, claiming, fan-out/fan-in, workflow templates, gates, and event journals are useful substrate and should not be rebuilt inside Orc Werk. Beads is an initial WorkGraphPort candidate, not a product dependency.

### zxro

- zxro — <https://github.com/odjhey/zxro>

Key lessons: stable logical work identity must outlive runtime/session churn; a turn is one delegated execution; execution outcome and work-facing verdict are distinct; attention delivery/read/handled/acceptance are different coordinates; durable artifacts should be progressively disclosed; provider composition is preferable to a mandatory storage/runtime stack.

### Rozoro

- Rozoro — <https://github.com/odjhey/rozoro>

Key lessons: do not rebuild harness-native subagents; task/session transport and active runtime control are different from planning/routing; exact candidate provenance matters; stale assurance must not be relabeled as current; planner, reviewer/tester, gate runner, merger, and watchtower responsibilities benefit from explicit authority boundaries; bounded attempts and replanning prevent endless repair loops.

### no-mistakes

- no-mistakes — <https://github.com/kunchenguid/no-mistakes>

Key lesson: assurance can be an external provider with its own internal pipeline. Orc Werk should normalize its verdict/evidence and exact candidate identity rather than recreate the review/test/lint/CI pipeline.

### ACP and acpx

- Agent Client Protocol — <https://github.com/agentclientprotocol/agent-client-protocol>
- acpx — <https://github.com/openclaw/acpx>

Key lesson: session transport, messaging, cancellation, persistence, and resume semantics should be reused through adapters when upstream protocols/clients can satisfy Orc Werk's ExecutionPort capabilities. Stronger semantics such as exact resume must be advertised and tested rather than assumed.

## Design conclusions carried into Orc Werk

The recurring pattern across these sources is a **graph of bounded, measurable loops** rather than one monolithic autonomous agent:

```text
intent
  -> explicit work topology
  -> replaceable execution
  -> exact candidate
  -> independent assurance
  -> accept | retry | replan | escalate
  -> verified terminal outcome
```

The product therefore tries to own the stable semantics around that flow while delegating the mechanics to replaceable providers.

When revisiting an Orc Werk contract, use this document to find the deeper literature/project history, then update the canonical contract or ADR explicitly rather than importing a source's vocabulary directly into the core.
