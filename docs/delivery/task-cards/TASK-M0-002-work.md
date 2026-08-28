---
id: TASK-M0-002
type: task-card
status: current
authority: normative
description: Implement the in-memory WorkGraphPort adapter and its conformance tests.
implements:
  - PORT-WORK-GRAPH
verifies:
  - SCN-005
---

# TASK-M0-002 — Memory work graph

## Outcome

Provide an in-memory WorkGraphPort supporting create/snapshot/ready/claim/complete/block.

## Acceptance

Pass `CONF-WORK-001` through `CONF-WORK-004` for advertised capabilities and enforce `INV-015`/`INV-016`.
