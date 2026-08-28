---
id: TASK-M0-004
type: task-card
status: current
authority: normative
description: Implement canonical journal persistence and replay.
implements:
  - PORT-JOURNAL
verifies:
  - SCN-001
---

# TASK-M0-004 — Journal

## Outcome

Implement MemoryJournal first, with a simple JSONL provider optional in the same card if it does not contaminate the pure core.

## Acceptance

Pass `CONF-JOURNAL-001` through `CONF-JOURNAL-003`; preserve facts, decisions, and effect records in order.
