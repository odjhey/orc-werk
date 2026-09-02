---
id: PRODUCT-THESIS
type: product
status: current
authority: normative
description: Product thesis and value proposition.
---

# Product thesis

**Orc Werk** is an opinionated, contract-driven orchestration kernel for autonomous work delivery.

The name is a playful reference to the Warcraft peon acknowledgement, "work, work"; the product/domain vocabulary itself remains deliberately plain and provider-neutral.

It binds work-graph systems, durable execution records, agent runtimes, candidate/artifact systems, assurance providers, operator attention, and optional versioned extensions through explicit replaceable ports and contracts.

The product is the ledger and seat protocol itself: the durable, replayable, seat-disciplined coordination substrate that any executor — a person, a scripted job, an agent session — records observations into. Executors are always external to the kernel and push their observations in; the kernel never pull-observes another process's lifecycle to infer them (`ADR-0005`).

> Our semantics are authoritative. Integrations adapt to Orc Werk; Orc Werk does not inherit provider semantics.

The kernel should be usable and fully testable with no Beads, zxro, ACP/acpx, Claude, Codex, GitHub, Git, or no-mistakes installation.

The first usable product surface is a CLI that can accept an intent, dispatch work through configured ports, monitor canonical facts, make attributable decisions, and drive the delivery loop toward a verified terminal state.

Python 3.11+ is the v0.x reference implementation so the project can dogfood quickly, instrument failures, and experiment with self-healing/recovery. The language is not part of Orc Werk's canonical product semantics; a future implementation in Go or another language must conform to the same contracts and scenarios.

Specialized provider/workflow semantics that are not required by the generic delivery state machine should be carried through `CONTRACT-EXTENSIONS` rather than becoming mandatory core fields.

The kernel's guarantees are the product; who fills the execution and assurance seats — operator, agents, adapters — is a staged identity, an adoption rung climbed at the deployer's own pace (`PRODUCT-ADOPTION`). Full autonomy is the top of that ladder, not the entry fee for using Orc Werk at all.
