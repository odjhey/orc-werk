---
id: ADR-0003
type: decision
status: current
authority: informative
description: Use Python 3.11+ as the initial reference implementation while keeping Orc Werk language-independent.
---

# ADR-0003 — Python-first reference implementation

**Status:** accepted

## Context

Orc Werk is still discovering its durable orchestration semantics through dogfooding. The immediate need is fast iteration on the pure core, adapters, fault injection, replay/reconciliation behavior, and self-healing experiments—not maximum runtime performance or a distributed deployment architecture.

Python 3.11+ offers a low-friction environment for this phase: the standard library is sufficient for M0, subprocess-based adapters are cheap to develop, fake/scripted providers are easy to construct, and agents can modify and test the reference implementation quickly.

At the same time, Orc Werk's value is its opinionated contracts and delivery semantics rather than its implementation language. Baking Python-specific persistence or behavior into the product would make a later implementation in Go or another language unnecessarily risky.

## Options

1. Start in Go now and optimize for a likely long-term systems implementation.
2. Start in Python and treat Python behavior as the product contract.
3. Start in Python as a reference implementation while keeping canonical contracts and serialized shapes language-independent.

## Decision

Choose option 3.

Python 3.11+ is the Orc Werk v0.x reference implementation. Python is not a canonical product semantic.

The reference implementation MUST preserve these boundaries:

- canonical domain/protocol records use portable explicit data shapes;
- canonical persisted/interchange records MUST NOT depend on pickle, Python class names, exception objects, arbitrary object graphs, or importable implementation classes;
- core semantics remain defined by `docs/contracts/`, `docs/domain/`, `docs/protocol/`, golden scenarios, and conformance requirements;
- self-healing semantics are expressed as replay, reconciliation, idempotent effects, bounded retries/replans, and capability-aware fallback rather than Python-specific recovery tricks;
- adapter implementations may use Python conveniences internally but MUST expose the canonical port semantics;
- the pure core remains standard-library-only through M0 unless a separately accepted decision changes that boundary.

## Consequences

- Dogfood iteration and adapter development stay cheap while the architecture is moving.
- Portable JSON-compatible shapes and explicit versions become important earlier than they otherwise might.
- A future Go implementation should be treated as another conforming implementation, not as an architectural rewrite.
- Orc Werk should not schedule a Go rewrite by calendar. Reimplementation should be considered only after dogfooding shows stable domain/port/journal/recovery semantics and a concrete operational reason to change languages.

## Future implementation-language gate

A Go implementation becomes worth evaluating when the evidence shows most of the following:

- several real adapters have been dogfooded successfully;
- core primitives and port shapes have remained stable across releases;
- canonical journal/serialization formats are explicitly versioned and stable;
- crash recovery, replay, reconciliation, and effect idempotency are proven in real use;
- the golden scenarios and conformance suites are mature enough to validate another implementation;
- deployment, concurrency, distribution, memory, startup, packaging, or operational constraints create a measurable reason to move beyond Python.

## Related

- `P-006`
- `P-009`
- `M-000`
- `ADR-0001`
