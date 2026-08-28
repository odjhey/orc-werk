---
id: PRODUCT-PRINCIPLES
type: product
status: current
authority: normative
description: Stable product principles.
---

# Product principles

## P-001 — Providers are replaceable

Provider selection is implementation policy, not domain identity.

## P-002 — Kernel semantics are authoritative

Adapters translate provider behavior into canonical contracts. Provider-specific behavior must not redefine core semantics.

## P-003 — Execution is not acceptance

A successful execution does not prove that work satisfies its contract. See `INV-003`.

## P-004 — Assurance is candidate-bound

Evidence applies to the exact candidate it evaluated. See `INV-007` through `INV-010`.

## P-005 — Stronger semantics never silently degrade

If a required capability is unavailable, fail explicitly or select another provider. See `INV-013`.

## P-006 — The core has no integration dependencies

Core state transitions, policy, and tests must run with in-memory/scripted providers only.

## P-007 — Judgment and mechanics are separate

Policy decides what should happen. The kernel validates and records decisions. Adapters perform effects.

## P-008 — Durable history is append-preserving

Attempts, facts, decisions, and evidence are retained rather than overwritten.

## P-009 — Implementation languages are replaceable

Orc Werk's canonical domain, protocol, journal, port, scenario, and conformance semantics must not depend on implementation-language-specific behavior. Python is the initial reference implementation, not a product semantic; a future implementation language must conform to the same contracts rather than redefine them.
