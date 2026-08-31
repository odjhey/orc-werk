---
id: EXT-EXECUTOR-IDENTITY-V1-SCHEMA
type: contract
status: current
authority: normative
version: 1
description: Portable schema for executor-identity/v1.
---

# `executor-identity/v1` schema

The extension payload has this conceptual shape:

```text
ExecutorIdentityV1 {
    model?: string
    session_ref?: string
    seat_ref?: string
    role: "ship" | "verify"
}
```

These four names are the complete field set for `executor-identity/v1`; producers MUST NOT add other fields to a v1 payload.

Canonical transport example:

```json
{
  "extensions": {
    "executor-identity/v1": {
      "model": "provider/model-name",
      "session_ref": "session-42",
      "seat_ref": "verify-seat-7",
      "role": "verify"
    }
  }
}
```

The payload transports on an execution attempt's or assurance entry's existing `extensions` slot and on the corresponding settled Fact's `extensions`. It adds no canonical Fact field.

## Required fields

`role` is required and MUST be either `ship` or `verify`.

The extension itself is optional. When present, it identifies one seat in the role stated by `role`.

## Optional fields

`model`, `session_ref`, and `seat_ref` are independently optional strings. Their absence supplies no default or inferred identity. In particular, `seat_ref` remains optional so payloads emitted before per-seat references were introduced remain valid v1 payloads.

The reference `orc record` command includes whichever of `model`, `session_ref`, and `seat_ref` the caller supplies, then adds `role: "verify"`; it emits no `executor-identity/v1` payload if none of those three optional values is supplied. Ship-seat producers use the same shape with `role: "ship"`.

## Field rules

- `model` identifies the model or tool used by the seat.
- `session_ref` identifies the containing provider or orchestrator session.
- `seat_ref` identifies the individual agent/thread/seat within that context. Producers SHOULD make it stable for that seat and distinct from the other seat for the same candidate.
- `role` is the payload discriminator. `ship` describes the seat recording execution provenance; `verify` describes the seat recording assurance provenance.

All three identity values are opaque strings. Their presence is provenance, not proof that two seats were independent.

## Portability

The payload MUST satisfy `EXT-006` and therefore use only portable JSON-compatible values.

## CONF-EXT obligations

- `CONF-EXT-001`: the payload uses only JSON-compatible strings and objects.
- `CONF-EXT-002` and `CONF-EXT-006`: absent or unknown `executor-identity/v1` never changes canonical processing or projection.
- `CONF-EXT-003`: lossless transports preserve the payload unchanged from an execution or assurance observation through the journal.
- `CONF-EXT-004`: no payload value overrides a canonical execution outcome, candidate identity, assurance verdict, or evidence binding.

## Versioning

Adding a field, adding a required field, or changing a field's meaning requires a new extension version (`executor-identity/v2`) rather than a silent change to `v1`.
