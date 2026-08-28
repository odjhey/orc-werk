---
id: TASK-M0-001
type: task-card
status: current
authority: normative
description: Implement the pure canonical model and transition engine.
implements:
  - ORCHESTRATION-CONTRACT
  - PROTOCOL-FACTS
  - PROTOCOL-DECISIONS
  - PROTOCOL-EFFECTS
verifies:
  - SCN-001
  - SCN-004
---

# TASK-M0-001 — Pure core

## Outcome

Implement integration-free canonical types, state, reducer/transition function, and deterministic v0 policy.

## Must not change

Provider contracts or adapter mappings.

## Acceptance

- no external runtime/integration dependencies in core;
- `INV-003`, `INV-004`, `INV-011`, `INV-012`, `INV-018`, `INV-019`, `INV-020` covered by unit tests;
- policy can produce Dispatch/Retry/RequestAssurance/Accept/Block decisions from scripted facts.
