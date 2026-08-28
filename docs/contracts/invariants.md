---
id: CONTRACT-INVARIANTS
type: contract
status: current
authority: normative
description: Canonical invariant registry.
---

# Invariant registry

## INV-001 — Work identity independence

Logical Work identity MUST be independent from execution, runtime, provider session, process, cwd, branch, pane, or provider-native identity.

## INV-002 — Provider IDs are opaque

The core MUST treat provider-native identifiers as opaque references.

## INV-003 — Execution settlement is not acceptance

An Execution reaching a successful terminal outcome MUST NOT by itself mark Work accepted.

## INV-004 — Retry preserves history

A retry MUST create a new Execution identity. Historical Executions MUST NOT be overwritten.

## INV-005 — Assurance requires an identifiable candidate

Work MUST NOT enter assurance without an identifiable Candidate.

## INV-006 — Candidate identity is exact

Candidate identity MUST support deterministic equality/freshness comparison at the level required by the acceptance contract.

## INV-007 — Evidence is candidate-bound

Evidence MUST identify the exact Candidate fingerprint it evaluates.

## INV-008 — Evidence is non-transferable across candidates

Evidence for Candidate A MUST NOT satisfy assurance requirements for Candidate B unless A and B have the same canonical fingerprint.

## INV-009 — Rejected/inconclusive assurance is not acceptance

`rejected` and `inconclusive` MUST NOT satisfy an acceptance requirement.

## INV-010 — Candidate change invalidates affected assurance

A candidate-changing mutation MUST invalidate all prior assurance whose subject fingerprint no longer matches.

## INV-011 — State-changing orchestration is attributable

Every orchestrator-directed state-changing action MUST have an attributable Decision.

Mechanical orchestrator steps that translate a prior fact into canonical state without a policy choice — for example `FX-CREATE-WORK` from a submitted intent, or `FX-IDENTIFY-CANDIDATE` — are mechanics per `P-007`, not policy choices, and MAY emit facts/effects without an accompanying Decision. A Decision is required only for policy-driven state transitions (the `DEC-*` choices in `PROTOCOL-DECISIONS`).

## INV-012 — Decisions cite their basis

A Decision MUST record the canonical facts or state snapshot on which it was based.

## INV-013 — Unsupported stronger semantics fail explicitly

An adapter MUST NOT silently emulate a stronger semantic with a weaker one. It MUST fail with `ERR-UNSUPPORTED-CAPABILITY`, expose the weaker capability, or allow policy to select another provider.

## INV-014 — Provider vocabulary stays outside the core

Provider-specific concepts MUST NOT appear in core domain logic or normative core contracts except in clearly marked adapter examples.

## INV-015 — Only eligible work dispatches

Work MUST be dispatched only when the authoritative WorkGraphPort reports it eligible under the canonical readiness contract.

## INV-016 — Dependencies unlock on committed completion conditions

Downstream Work MUST NOT become eligible merely because an upstream Execution settled. Required upstream completion/acceptance conditions must be committed first.

## INV-017 — Observed, handled, and accepted remain distinct

Where persistent attention is enabled, observing an event, handling that event, and accepting the related Work MUST remain distinct operations.

## INV-018 — Retry budget is cumulative

Retry history and attempt counts MUST be cumulative for one Work lineage.

`attempt_number` is the cumulative per-Work-lineage attempt index; the first execution attempt is `1`. It MUST be deterministically reconstructable from the journal as the count of execution-start records for that Work in the DeliveryRun history.

## INV-019 — Retry is bounded

Policy MUST define a finite retry budget or an equivalent terminal/escalation condition.

## INV-020 — Effects are idempotency-addressable

State-changing Effects MUST carry a stable idempotency key or effect identity so crash/retry behavior can be deterministic.

Idempotency keys MUST be deterministically derivable from durable canonical state: the standard tuple `(delivery_run_id, work_id, attempt_number, effect_id)`, with `attempt_number` as defined by `INV-018`. Idempotency keys MUST NOT be derived from randomness, wall-clock time, or process/runtime identity, so that journal replay (`PORT-JOURNAL-005`) reproduces identical keys.

Key form per effect:

- `FX-CREATE-WORK` precedes any attempt and creates all Work records for one plan, so it is keyed on `(delivery_run_id, effect_id)`. This is valid because v0 permits exactly one plan creation per DeliveryRun.
- `FX-CLAIM-WORK` uses the standard tuple with `attempt_number` set to the upcoming attempt's index.
- `FX-START-EXECUTION`, `FX-SEND-EXECUTION`, `FX-CANCEL-EXECUTION`, `FX-IDENTIFY-CANDIDATE`, `FX-COMPLETE-WORK`, and `FX-BLOCK-WORK` use the standard tuple.
- `FX-START-ASSURANCE` (assurance-targeting) uses the standard tuple plus `candidate_fingerprint`.
