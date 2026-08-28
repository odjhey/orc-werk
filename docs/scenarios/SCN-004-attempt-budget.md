---
id: SCN-004
type: scenario
status: current
authority: normative
description: Retry budget prevents infinite execution loops.
---

# SCN-004 — Attempt budget exhausted

## Given
- Work A is ready.
- max_attempts = 3.
- All three executions fail or produce rejected candidates.

## Then
- A fourth Execution is not dispatched.
- Work transitions to BLOCKED/FAILED according to v0 policy.
- A `DEC-BLOCK` or `DEC-ESCALATE` is recorded.

Verifies: `INV-018`, `INV-019`.
