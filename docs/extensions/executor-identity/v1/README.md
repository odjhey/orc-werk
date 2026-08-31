---
id: EXT-EXECUTOR-IDENTITY-V1
type: extension
status: current
authority: normative
version: 1
description: Ship- and verify-seat executor provenance extension.
---

# `executor-identity/v1`

`executor-identity/v1` is an optional extension carrying the identity and role of a ship or verify seat when no adapter journals that seat. It travels in an execution attempt's or assurance entry's existing `extensions` slot and unchanged on the corresponding settled Fact's `extensions`; it is not a canonical Fact field.

The payload is observational provenance for the no-self-assurance audit trail. It does not establish that the seats were independent, and the generic kernel does not inspect or enforce the recorded identity.

## Purpose

Make ship and verify seats distinguishable in durable journal history, including when they share one orchestrating session, without changing settlement, assurance, candidate binding, or delivery state.

## Scope rules

- **Seat provenance.** `role` identifies whether the payload describes a `ship` or `verify` seat. The other fields preserve available executor references.
- **Per-seat distinction.** Producers SHOULD provide `seat_ref`. Seats sharing one `session_ref` use distinct `seat_ref` values so the journal can distinguish them, per the issue #182 rationale.
- **Observational only.** Per `EXT-002` and `EXT-005`, the generic kernel MUST NOT branch on this payload. Presence, absence, or contents do not enforce no-self-assurance.
- **No canonical override.** Per `EXT-003` and `EXT-007`, this extension neither overrides nor replaces canonical execution outcomes, candidates, assurance verdicts, or evidence.

## Files

- [Schema](schema.md)
- [Semantics](semantics.md)
- [Examples](examples.md)

## Related

- `CONTRACT-EXTENSIONS`
- `PLAYBOOK-AGENT-CLI`
- `FACT-EXEC-SETTLED`
- `FACT-ASSURE-SETTLED`
- `CONF-EXT-003`
