---
id: PORT-CANDIDATE
type: port
status: current
authority: normative
version: 1
description: Exact candidate identity and comparison interface.
---

# CandidatePort

## Purpose

Translate provider artifacts/results into an exact canonical Candidate suitable for assurance freshness checks.

## Candidate shape

```text
Candidate {
  id
  work_id
  execution_id
  subject_identity
  fingerprint
}
```

Provider-native subject fields are opaque to the core. The adapter must produce a deterministic canonical fingerprint.

## Operations

### PORT-CAND-001 `identify`
Identify the candidate produced by one execution/artifact set. May return no candidate when the execution produced no assurable subject.

### PORT-CAND-002 `current`
Return the current candidate for Work when the provider can determine one safely. When the current candidate cannot be determined safely, the port MUST return an explicit empty/none result — never a stale or guessed candidate.

### PORT-CAND-003 `compare`
Return `same` or `different` according to canonical fingerprint equality.

## Related invariants

`INV-005`, `INV-006`, `INV-010`.
