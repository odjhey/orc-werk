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

### PORT-WORK-002 `snapshot`
Return the current bounded canonical work topology for a DeliveryRun.

### PORT-WORK-003 `ready`
Return Work eligible for dispatch now.

Semantics: eligibility is authoritative. The core MUST obey `INV-015` and `INV-016`.

### PORT-WORK-004 `claim`
Claim one Work item for orchestration/execution when supported.

### PORT-WORK-005 `complete`
Commit the completion condition required to unlock dependents.

### PORT-WORK-006 `block`
Commit a non-terminal or terminal block reason according to policy/provider capability.

## Required errors

Use canonical errors from `CONTRACT-ERRORS`.

## Explicit non-semantics

This port does not define:
- provider issue types;
- provider labels;
- provider workflow-template vocabulary;
- branch or repository policy;
- executor selection.

## Related invariants

`INV-001`, `INV-015`, `INV-016`, `INV-020`.
