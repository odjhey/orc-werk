---
id: PORT-WORK-GRAPH
type: port
status: current
authority: normative
version: 1
description: Canonical work topology/readiness interface.
---

# WorkGraphPort

## Purpose

Expose authoritative logical Work topology and dispatch eligibility without exposing provider-specific work-tracker concepts.

## Operations

### PORT-WORK-001 `create`
Create Work records for a DeliveryRun from an explicit plan or deterministic single-work plan.

Portable plan input shape:

```json
{
  "works": [
    {
      "work_id": "string",
      "deps": [
        {"work_id": "string", "condition": "accepted"}
      ]
    }
  ]
}
```

`condition: "accepted"` is the only v0 dependency condition, consistent with the committed-completion unlock rule in `INV-016`. The deterministic single-work plan is the degenerate one-element form: `works` with a single entry and an empty `deps` list.

A plan MUST be rejected with `ERR-VALIDATION` (see `CONTRACT-ERRORS`) when it contains any of:

- a duplicate `work_id`;
- a `deps` entry naming a work not present in the plan, or naming the work itself;
- an empty `works` list;
- a dependency cycle;
- a `deps` entry whose `condition` is not `"accepted"` (the only v0 condition).

Structurally malformed plans (missing required keys, wrong types — e.g. a non-list `deps`) MUST also be rejected with `ERR-VALIDATION`; plan validation never surfaces implementation-language errors.

### PORT-WORK-002 `snapshot`
Return the current bounded canonical work topology for a DeliveryRun.

Portable v0 snapshot shape:

```json
{
  "works": [
    {
      "work_id": "string",
      "deps": [
        {"work_id": "string", "condition": "accepted"}
      ],
      "completed": true,
      "blocked_reason": null
    }
  ]
}
```

This is the graph topology (mirroring the `PORT-WORK-001` create plan shape) plus the completion/block status the WorkGraph is authoritative for. `blocked_reason` is `null` unless blocked. Bounded to one DeliveryRun.

### PORT-WORK-003 `ready`
Return Work eligible for dispatch now.

Semantics: eligibility is authoritative. The core MUST obey `INV-015` and `INV-016`. `ready` is a discovery surface for claimants: it returns Work that is both eligible (per `INV-015`/`INV-016`) and unclaimed.

### PORT-WORK-004 `claim`
Claim one Work item for orchestration/execution when supported.

A claim is once per Work lineage: the claim holder owns the Work across all retry attempts within that lineage and drives them from journal state. Retries within a lineage MUST NOT re-claim.

`claim` MUST reject with `ERR-CONFLICT` when the named Work is not currently eligible to be claimed — deps not committed-complete (`INV-016`), or the Work is already claimed, completed, or blocked.

Output: a portable mapping `{work_id, claim_ref}`, where `claim_ref` is a provider-issued opaque string.

### PORT-WORK-005 `complete`
Commit the completion condition required to unlock dependents.

`complete` on a Work that is already completed is idempotent: it MUST succeed and MUST NOT re-run completion side effects.

### PORT-WORK-006 `block`
Commit a non-terminal or terminal block reason according to policy/provider capability.

`block` on a Work that is already blocked is idempotent when the given reason matches the recorded block reason; it MUST reject with `ERR-CONFLICT` when the given reason differs from the recorded one.

## Required errors

Use canonical errors from `CONTRACT-ERRORS`. In particular, across all operations on this port: an operation naming an unknown `work_id` MUST reject with `ERR-NOT-FOUND`; a mutation (`claim`, `complete`, `block`) against a Work that is already in a terminal state (completed or blocked) MUST reject with `ERR-CONFLICT`, except for the `complete`-on-completed and matching-reason `block`-on-blocked idempotent cases stated above.

## Explicit non-semantics

This port does not define:
- provider issue types;
- provider labels;
- provider workflow-template vocabulary;
- branch or repository policy;
- executor selection.

## Related invariants

`INV-001`, `INV-015`, `INV-016`, `INV-020`.
