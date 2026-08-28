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
