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
extensions?: map<versioned_extension_id, json_payload>
```

If an assurance provider may mutate the candidate, it MUST advertise `CAP-ASSURE-MAY-MUTATE-CANDIDATE` and return the final candidate identity when changed.

M0 scripted adapters do not advertise `CAP-ASSURE-MAY-MUTATE-CANDIDATE`. The precise interaction between a settled `final_candidate` and the `INV-010` invalidation rule is deferred to a future contract revision and is not exercised by M0 scenarios.

`extensions`, when present, MUST satisfy `CONTRACT-EXTENSIONS`. The generic core records/transports them but MUST NOT inspect their internals to derive the canonical assurance verdict or candidate identity.

A policy that requires a specific assurance extension MUST name the exact extension/version and verify provider support before relying on it.

## Structured findings

Providers advertising `CAP-ASSURE-STRUCTURED-FINDINGS` MAY return registered finding extensions. The first registered schema is `EXT-REVIEW-FINDINGS-V1` (`review-findings/v1`). This schema is optional and does not make code-review fields part of the generic Assurance domain.

## Related invariants

`INV-005` through `INV-010`, `INV-013`, `INV-020`.
