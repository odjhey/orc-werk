---
id: PRODUCT-BOUNDARIES
type: product
status: current
authority: normative
description: Product ownership and explicit non-goals.
---

# Product boundaries

## The kernel owns

- canonical orchestration identities and semantics;
- state machines and invariants;
- facts, decisions, and effects;
- capability requirements;
- retry/terminal rules;
- provider conformance contracts;
- canonical monitoring projections.

## The kernel does not inherently own

- model execution or subagents;
- conversation/session persistence;
- work tracker implementation;
- Git implementation;
- branch/worktree policy;
- test or review framework implementation;
- CI implementation;
- merge implementation;
- artifact storage implementation;
- provider-native lifecycle schemas;
- provider-specific UI or terminal hosting.

Those capabilities enter through adapters.

## Explicit non-goals

- Orc Werk never pull-observes another process's lifecycle. Executors are
  always external and push their observations in — `orc record`,
  merge-only config edits, or a re-dispatch that replays the journal — and
  the kernel only ever reacts to what was pushed. It does not poll, scrape,
  or infer liveness/settlement from a session, stream, or daemon it does
  not own (`ADR-0005`).
