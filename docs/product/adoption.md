---
id: PRODUCT-ADOPTION
type: guide
status: current
authority: informative
description: Operator-facing adoption guide — when to use Orc Werk, prerequisites, and how to tailor-fit it.
---

# Adoption guide

This guide answers three questions an operator asks before adopting Orc Werk: when to use it, what must be true before it can be used, and where it is meant to be shaped to fit a deployment. It complements `PRODUCT-THESIS`, `PRODUCT-PRINCIPLES`, and `PRODUCT-BOUNDARIES` rather than restating them; read those first for the underlying contract. This guide is informative — it cites stable IDs for their normative content instead of duplicating it.

## 1. When to use it

Reach for Orc Werk when three conditions co-occur:

1. **Delegated work whose "done" cannot be taken at face value.** Acceptance must be separated from the executor's own claim and bound to the exact artifact produced (`INV-003`, candidate-bound assurance per `INV-005` through `INV-010`).
2. **Delivery that outlives a sitting.** Attempts, verdicts, and pending states must survive process exits and the operator's attention span, not just live in one terminal session (`P-008`, `PORT-JOURNAL`).
3. **Non-trivial structure.** Dependent work items, bounded retries, or multiple agents that need one authoritative record of what happened (`INV-004`, `INV-018` through `INV-020`, `INV-011`).

One-line positioning: CI verifies code; trackers hold intentions; Orc Werk durably and skeptically holds the delivery in between — attempts, candidates, verdicts.

### When NOT to use it

- A single task you watch to completion and review immediately yourself.
- Executors whose reports you already trust unconditionally — compilers, deterministic scripts, anything where a non-zero exit code is a sufficient verdict.
- Anywhere a TODO list or a CI pipeline already provides the guarantee you need. Orc Werk earns its keep at the seam between "an agent said it's done" and "someone/something independently agrees" — if that seam does not exist in your workflow, the product has nothing to add.

## 2. Prerequisites (the adoption ladder)

Orc Werk has no server, no daemon, no database, and no accounts. Every rung below is reached by adding a real provider behind a port, not by standing up infrastructure. Per run, the only prerequisites are an intent, optionally a plan, a journal directory, and an assurance source — someone or something willing to render a verdict. That last one is the prerequisite adopters most often forget, and the one the product exists to insist on: without it, `INV-003` has nothing to check execution's claim against.

| Rung | What it gives you | What it adds | Status |
|---|---|---|---|
| Simulator / spec-executor | Drives the pure delivery state machine end to end with in-memory/scripted providers; no real work, no real agents. | Python 3.11+ and this repo — nothing else. | Usable today (`M-001` M0 baseline) |
| Durable ledger for real, operator-recorded work | A real multi-work delivery run through `orc dispatch`/`status`/`history`, with the operator recording outcomes as they become known and the run surviving process exits between steps. | Pending/incremental dispatch mode (`TASK-M1-002`) | M1a |
| Multi-agent ledger | Ship and verify subagents record their own settlement, candidate, and assurance observations through the CLI instead of the operator transcribing on their behalf. | The agent CLI usage guidance playbook (`TASK-M1-006`), agents with shell access to the `orc` CLI | M1a+ |
| Autonomous orchestrator | Execution itself is automated — no human in the settlement-recording seat. | A real `PORT-EXECUTION` adapter (`TASK-M1-005`) plus the durability contract that governs what it must persist (`CONTRACT-DURABILITY`) | M1b |

Each rung is strictly additive: nothing on a lower rung is replaced, only the execution/recording seat moves further from the operator's own hands. Stopping at any rung is a legitimate, supported adoption point — there is no rung you are obligated to climb past.

## 3. Tailor-fitting (the customization surfaces)

Orc Werk is customized by *where* you plug into it, not by forking it. The surfaces below are listed in the order most adopters touch them.

### Adapters — the primary surface

Implement the five mandatory ports (`PORTS-INDEX`) against your own systems:

- your issue tracker as `PORT-WORK-GRAPH`;
- your runner or agents as `PORT-EXECUTION`;
- your review process — human or automated — as `PORT-ASSURANCE`;
- your storage as `PORT-JOURNAL`;
- your artifact identity as `PORT-CANDIDATE`.

The conformance suites (`CONF-WORK-001` through `CONF-WORK-004`, `CONF-EXEC-001` through `CONF-EXEC-004`, `CONF-CAND-001` through `CONF-CAND-003`, `CONF-ASSURE-001` through `CONF-ASSURE-004`, `CONF-JOURNAL-001` through `CONF-JOURNAL-003`, and `CONF-EXT-001` through `CONF-EXT-006` where applicable) are the acceptance tests: an adapter is fit for use when the applicable suites pass against it. Reusable, factory-parameterized versions of these suites already exist under `tests/conformance/` for exactly this purpose — a new adapter runs the same suite the reference in-memory/scripted adapters run, not a bespoke one. Provider vocabulary — API shapes, CLI flags, provider-native identifiers — stays inside your adapter and its `docs/adapters/` mapping doc (`INV-014`); it must never leak into core contracts or policy.

### Capability honesty

Advertise only the `CAP-*` capabilities (`CONTRACT-CAPABILITIES`) your adapter genuinely delivers. An unsupported stronger semantic must fail explicitly rather than silently degrade (`INV-013`), and a durability-bearing capability carries a durability obligation — it must not be claimed unless the durable evidence it implies can actually be persisted (`CONTRACT-CAPABILITIES`'s capability-durability rule, `CONTRACT-DURABILITY`).

### Extensions — domain payloads

Specialized semantics that are not required by the generic delivery state machine ride versioned extensions under `docs/extensions/`, per `CONTRACT-EXTENSIONS`. The registered extensions — `EXT-REVIEW-FINDINGS-V1` (`review-findings/v1`) and `EXT-EXECUTION-SESSION-V1` (`execution-session/v1`) — are the worked examples for how to add your own. Extensions never override canonical fields, and unknown extensions must transport losslessly, so independently-tailored deployments can still share a journal and ignore each other's private payloads.

### Durable ownership

If your deployment produces durable information that is not part of the canonical core — reports, provenance, configuration, anything else — give it an explicit owner per `CONTRACT-DURABILITY`. Silent loss of that information is a defect, not an acceptable simplification; `CONTRACT-DURABILITY`'s ownership matrix and Rozoro retirement ledger are the worked template for classifying non-core durable state as canonicalized, delegated, implementation-local, or intentionally dropped.

### Policy configuration

Retry budgets (`max_attempts`), required capability strengths (for example, resume exactness), and assurance requirements are policy inputs you set, not forks of the kernel (`P-007`, `INV-019`).

### Plans

Model your workflow's topology as the portable plan shape: works plus accepted-completion dependencies (`INV-015`, `INV-016`). This is how your dependency graph — whatever tool it lives in upstream — gets expressed to the kernel.

### Composition layer

The reference CLI's config format is explicitly non-normative, CLI-owned composition (`docs/playbooks/cli-usage.md`). Adopters are expected to build their own composition layer — their own CLI or service that wires their adapters into the app orchestrator. The app + core + ports layers (`ARCH-REPOSITORY-STRUCTURE`) are the product; the CLI is a reference consumer of it, not the boundary of what you may build.

### What you must not tailor

The canonical state machine, its invariants, the facts/decisions/effects vocabulary, and the portable record shapes are not customization surfaces. Cross-deployment interoperability and the product's guarantees exist precisely because these stay fixed across every adapter and extension. When one of them does not fit your case, that is a contract-change proposal upstream (`docs/README.md`'s authoring rules), not a local fork.

## Related

- `PRODUCT-THESIS`
- `PRODUCT-PRINCIPLES`
- `PRODUCT-BOUNDARIES`
- `PORTS-INDEX`
- `CONFORMANCE-INDEX`
- `CONTRACT-EXTENSIONS`
- `CONTRACT-DURABILITY`
- `CONTRACT-CAPABILITIES`
- `M-001`
- `ARCH-REPOSITORY-STRUCTURE`
- `PLAYBOOK-CLI-USAGE`
