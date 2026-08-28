---
id: PRODUCT-THESIS
type: product
status: current
authority: normative
description: Product thesis and value proposition.
---

# Product thesis

**Orc Werk** is an opinionated, contract-driven orchestration kernel for autonomous work delivery.

It binds work-graph systems, durable execution records, agent runtimes, candidate/artifact systems, assurance providers, and operator attention through explicit replaceable ports.

> Our semantics are authoritative. Integrations adapt to Orc Werk; Orc Werk does not inherit provider semantics.

The product name is a playful reference to the Warcraft III peon acknowledgement “work, work.” The branding does not change the domain vocabulary: the canonical concepts remain Work, Execution, Candidate, Evidence, Decision, Fact, Effect, and the published ports.

The kernel must be usable and fully testable with no Beads, zxro, ACP/acpx, Claude, Codex, GitHub, Git, or no-mistakes installation.

The first usable product surface is a CLI that can accept an intent, dispatch work through configured ports, monitor canonical facts, make attributable decisions, and drive the delivery loop toward a verified terminal state.

Python 3.11+ is the initial reference implementation for the dogfood phase. The language is not part of this product thesis or the canonical contracts. A future implementation in Go or another language must be able to implement the same domain, protocol, journal, port, scenario, and conformance semantics without redefining Orc Werk.
