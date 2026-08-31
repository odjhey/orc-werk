---
id: CONFORMANCE-INDEX
type: index
status: current
authority: normative
description: Provider-independent conformance requirements.
---

# Conformance

Every real adapter must pass the same conformance requirements as its in-memory counterpart for each capability it advertises.

## Initial requirements

### Work graph
- `CONF-WORK-001`: ready excludes blocked dependencies.
- `CONF-WORK-002`: completion unlocks dependents only after required completion is committed.
- `CONF-WORK-003`: duplicate completion is idempotent or deterministically conflicting.
- `CONF-WORK-004`: atomic claim is tested when `CAP-WORK-ATOMIC-CLAIM` is advertised.

### Execution
- `CONF-EXEC-001`: start returns a stable logical execution identity.
- `CONF-EXEC-002`: repeated start with the same effect/idempotency key does not create two logical executions.
- `CONF-EXEC-003`: inspect distinguishes running from terminal settlement.
- `CONF-EXEC-004`: unsupported resume strength fails explicitly.

### Candidate
- `CONF-CAND-001`: same exact subject yields the same fingerprint.
- `CONF-CAND-002`: changed subject yields a different fingerprint.
- `CONF-CAND-003`: current() must not silently return a known-stale candidate.

### Assurance
- `CONF-ASSURE-001`: settled evidence names the candidate fingerprint.
- `CONF-ASSURE-002`: rejected never normalizes to accepted.
- `CONF-ASSURE-003`: evidence from a different fingerprint is rejected by the kernel.
- `CONF-ASSURE-004`: inconclusive remains distinct from rejected/accepted.
- `CONF-ASSURE-005`: at scripted-assurance ingestion, a recorded verdict carrying `derived_identity` that fails subset-equality against the bound candidate's durable `subject_identity` MUST be rejected with `ERR-CONFLICT` before any Fact is journaled; an assurance entry without `derived_identity` binds exactly as before. See `SCN-013` and issue #180.

### Extensions
See [extension conformance](extensions.md) for `CONF-EXT-001` through `CONF-EXT-007`.

### Journal
- `CONF-JOURNAL-001`: append order is deterministic.
- `CONF-JOURNAL-002`: history is immutable/append-preserving.
- `CONF-JOURNAL-003`: replay reconstructs the same canonical projection, folding under the run's own durably recorded retry budget (`FX-CREATE-WORK` effect record `data.max_attempts`, `PORT-JOURNAL-005`) rather than an adapter default — including when the run's terminal state is `BLOCKED` (retry-budget exhaustion) and when replaying a legacy journal that predates the recorded budget (falls back to the reducer's schema default). See `SCN-008`.
- `CONF-JOURNAL-004`: replay of operator cancellation deterministically reconstructs a clean, confirmed terminal `CANCELLED` projection; cancellation is rejected from every terminal state and never emits a port Effect or fabricates an assurance verdict. See `SCN-011`.
