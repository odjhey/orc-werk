---
id: PORT-ASSURANCE
type: port
status: current
authority: normative
version: 1
description: Candidate-bound assurance interface.
---

# AssurancePort

## Purpose

Request and observe independent evaluation of one exact Candidate.

## Operations

### PORT-ASSURE-001 `request`
Input: Candidate, assurance requirements, idempotency key.
Output: AssuranceRun reference.

### PORT-ASSURE-002 `inspect`
Output:

```text
state: requested | running | settled
verdict?: accepted | rejected | inconclusive
candidate_fingerprint: required when settled
evidence_refs: zero or more
final_candidate?: Candidate when provider may mutate the subject
```

If an assurance provider may mutate the candidate, it MUST advertise `CAP-ASSURE-MAY-MUTATE-CANDIDATE` and return the final candidate identity when changed.

## Related invariants

`INV-005` through `INV-010`, `INV-013`, `INV-020`.
