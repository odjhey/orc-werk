---
id: SCN-013
type: scenario
status: current
authority: normative
description: Scripted assurance corroborates the bound candidate with an optional independently derived identity before recording a verdict.
---

# SCN-013 — Scripted assurance derived-identity binding

## Purpose

Prove the optional scripted-assurance `derived_identity` closes issue #180's stale-candidate detection gap at verdict ingestion without changing canonical facts, reducer behavior, or backward compatibility (`CONF-ASSURE-005`). Detection is bounded by the identity fields the verifier asserts: omitted fields are not compared, while asserting the full identity provides full-payload corroboration.

## Given

- A run is resting at `ASSURING` with candidate C1 bound to the current attempt.
- C1's durable `subject_identity`, read from the run's `FX-IDENTIFY-CANDIDATE` effect record, is portable JSON `{"head_sha": "current", "pr": 180}`.
- The scripted assurance entry is the CLI-owned `attempts.<work>[n].assurance` config object.
- Comparison is pure CLI-layer subset-equality against that durable identity: every asserted key must exist in C1's `subject_identity` and have equal uninterpreted JSON value. No adapter is invoked and no identity is re-derived during ingestion.
- `derived_identity` must be a non-empty identity object. A payload containing an `extensions` key is rejected with `ERR-VALIDATION`.

## Then

### Mismatch leg

1. Recording a verdict with `derived_identity = {"head_sha": "stale"}` fails subset-equality and is rejected with `ERR-CONFLICT`, canonical error JSON, both the asserted and bound identity payloads in its `next` affordances, and exit `2` (`CONF-ASSURE-005`).
2. Rejection occurs at verdict-binding time before any Fact is journaled. The verdict does not bind.
3. The run remains pending at the legal `ASSURING` resting point and can be re-dispatched after correcting the entry. For a genuinely stale bound candidate, the operator may instead use `DEC-ABANDON-ATTEMPT`.
4. The mismatch has no ledger-durable evidence record; issue #180 deliberately defers one unless practice shows the stderr-only record is insufficient.

### Match leg

1. Recording the same verdict with `derived_identity = {"head_sha": "current"}` satisfies subset-equality and binds normally.
2. The resulting `FACT-ASSURE-SETTLED` is exactly the record produced without corroboration: no provenance echo, new context version, or `derived_identity` field is added. Its `candidate_fingerprint` remains independently corroborated by construction.

### Absent leg

1. Recording the verdict without `derived_identity` follows the pre-issue-#180 behavior unchanged; every existing config remains legal and the verdict binds normally.

## Replay determinism

A rejected mismatch leaves the journal byte-for-byte untouched. Replaying that journal therefore reconstructs the same pending `ASSURING` projection as before the rejected recording; there is no rejected Fact for the reducer to encounter.

## Mutation check

Binding the mismatched verdict, appending any Fact before returning the conflict, comparing fields not asserted by the verifier, interpreting JSON values, consulting an adapter, changing the success Fact, or rejecting an entry with no `derived_identity` makes this scenario fail.

## Executable coverage

The executable `tests/scenarios/test_scn_013_*.py` coverage lands with issue #180's implementation card, after this scenario merges, per the repository's scenario-before-implementation rule.

Verifies: `CONF-ASSURE-005`, `ERR-CONFLICT`, `ERR-VALIDATION`, `FX-IDENTIFY-CANDIDATE`, `FACT-ASSURE-SETTLED`, `DEC-ABANDON-ATTEMPT`.
