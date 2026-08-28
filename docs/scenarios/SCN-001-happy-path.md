---
id: SCN-001
type: scenario
status: current
authority: normative
description: Happy-path delivery from ready work to accepted completion.
---

# SCN-001 — Happy path

## Given
- Work A is ready.
- Execution produces Candidate C1.
- Assurance for C1 returns accepted.

## When
The DeliveryRun advances until terminal state.

## Then
1. Work A is dispatched once.
2. One Execution is retained.
3. Candidate C1 has an exact fingerprint.
4. Assurance evidence references C1's fingerprint.
5. Work A completes only after assurance acceptance.
6. Facts, Decisions, and Effects are present in the Journal.

Verifies: `INV-003`, `INV-005`, `INV-007`, `INV-011`, `INV-020`.
