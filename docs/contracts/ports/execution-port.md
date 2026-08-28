---
id: PORT-EXECUTION
type: port
status: current
authority: normative
version: 1
description: Canonical external execution interface.
---

# ExecutionPort

## Purpose

Start, inspect, communicate with, and cancel external work-producing executions without modeling provider-native agent internals.

## Operations

### PORT-EXEC-001 `start`
Input: Work reference, execution request, idempotency key.
Output: stable Execution reference.

### PORT-EXEC-002 `inspect`
Output canonical execution observation:

```text
state: requested | running | settled
outcome?: completed | failed | cancelled
artifact_refs?: opaque references
extensions?: map<versioned_extension_id, json_payload>
```

`extensions`, when present, MUST satisfy `CONTRACT-EXTENSIONS`. The generic core records/transports them but MUST NOT inspect their internals to derive the canonical execution state or outcome.

### PORT-EXEC-003 `send`
Optional capability `CAP-EXEC-SEND`.

### PORT-EXEC-004 `cancel`
Optional/required according to adapter profile; capability `CAP-EXEC-CANCEL`.

### PORT-EXEC-005 `resume`
Optional. Adapter MUST distinguish best-effort from exact resume. See `INV-013`.

The caller expresses the required resume strength via a `capability` field on the resume request, valued `CAP-EXEC-RESUME-BEST-EFFORT` or `CAP-EXEC-RESUME-EXACT`. A resume request with a missing or unknown `capability` value MUST be rejected with `ERR-VALIDATION`. An adapter MUST NOT silently substitute a weaker resume strength than the one requested — an adapter that cannot meet the requested strength MUST fail per `INV-013` rather than default down.

## Explicit non-semantics

The port does not promise:
- model identity;
- subagent visibility;
- transcript access;
- provider tool-call events;
- terminal/pane identity.

## Related invariants

`INV-001` through `INV-004`, `INV-013`, `INV-020`.
