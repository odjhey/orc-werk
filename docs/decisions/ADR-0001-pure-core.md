---
id: ADR-0001
type: decision
status: current
authority: informative
description: Keep the semantic kernel integration-free and effect-driven.
---

# ADR-0001 — Pure effect-driven core

## Context

The product must remain stable while work trackers, runtimes, assurance systems, and agent harnesses change rapidly.

## Decision

Core transition/policy code has no integration dependencies and never performs provider I/O directly. It consumes canonical facts and emits decisions/effects. Adapters execute effects through ports.

## Consequences

- provider-free tests become the architectural baseline;
- adapters can be replaced independently;
- integration details cannot silently become product semantics.

Related: `P-006`, `INV-014`, `INV-020`.
