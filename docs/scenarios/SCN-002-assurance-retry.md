---
id: SCN-002
type: scenario
status: current
authority: normative
description: Assurance rejection produces a new execution/candidate and does not reuse stale evidence.
---

# SCN-002 — Assurance rejection followed by retry

## Given
- Work A is ready.
- max_attempts = 3.
- Execution 1 produces Candidate C1.
- Assurance rejects C1.
- Execution 2 produces Candidate C2.
- Assurance accepts C2.

## Then
1. Two distinct Executions exist.
2. C1 and C2 have different fingerprints.
3. Evidence for C1 remains bound only to C1.
4. Rejection of C1 does not complete Work A.
5. Acceptance of C2 completes Work A.
6. Decision history contains one `DEC-RETRY`.

Verifies: `INV-004`, `INV-007`, `INV-008`, `INV-010`, `INV-018`.
