---
id: TASK-M0-003
type: task-card
status: current
authority: normative
description: Implement scripted Execution, Candidate, and Assurance adapters for deterministic scenarios.
implements:
  - PORT-EXECUTION
  - PORT-CANDIDATE
  - PORT-ASSURANCE
verifies:
  - SCN-002
  - SCN-003
  - SCN-006
---

# TASK-M0-003 — Scripted providers

## Outcome

Implement deterministic scripted adapters with no external integrations.

## Depends on

`TASK-M0-001`, `TASK-M0-006`.

## Acceptance

Pass applicable `CONF-EXEC-*`, `CONF-CAND-*`, and `CONF-ASSURE-*` requirements and prove stale candidate evidence is not reused.
