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

> Our semantics are authoritative. Integrations adapt to Orc Werk; Orc Werk does not inherit provider semantics.

The kernel should be usable and fully testable with no Beads, zxro, ACP/acpx, Claude, Codex, GitHub, Git, or no-mistakes installation.

The first usable product surface is a CLI that can accept an intent, dispatch work through configured ports, monitor canonical facts, make attributable decisions, and drive the delivery loop toward a verified terminal state.

Python 3.11+ is the v0.x reference implementation so the project can dogfood quickly, instrument failures, and experiment with self-healing/recovery. The language is not part of Orc Werk's canonical product semantics; a future implementation in Go or another language must conform to the same contracts and scenarios.

Specialized provider/workflow semantics that are not required by the generic delivery state machine should be carried through `CONTRACT-EXTENSIONS` rather than becoming mandatory core fields.
