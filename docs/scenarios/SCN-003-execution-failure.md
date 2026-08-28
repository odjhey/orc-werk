---
id: SCN-003
type: scenario
status: current
authority: normative
description: Execution failure is retried without overwriting attempt history.
---

# SCN-003 — Execution failure

## Given
- Work A is ready.
- max_attempts = 3.
- Execution 1 fails.
- Execution 2 completes and produces an accepted candidate.

## Then
- Execution 1 remains immutable history.
- Execution 2 has a new identity.
- Work acceptance occurs only after assurance of Execution 2's candidate.

Verifies: `INV-003`, `INV-004`, `INV-018`.
