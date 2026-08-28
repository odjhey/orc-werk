---
id: TASK-M1-004
type: task-card
status: current
authority: normative
description: Author the durability-responsibilities contract and retirement ledger, register execution-session/v1, and amend CONTRACT-CAPABILITIES with the durability-honesty rule.
implements:
  - CONTRACT-CAPABILITIES
  - CONTRACT-EXTENSIONS
verifies: []
---

# TASK-M1-004 — Durability contract and execution-session/v1

## Outcome

- Author `docs/contracts/durability-responsibilities.md`: the durability-obligations contract plus the Rozoro retirement ledger (source-object → semantic guarantee → Orc disposition → durable owner → contract/schema → verification). Planned rows are allowed for contracts not yet built; every row reaches one of canonicalized/delegated/implementation-local/intentionally-dropped.
- Register `execution-session/v1` under `docs/extensions/`, satisfying `CONTRACT-EXTENSIONS` (`EXT-001` through `EXT-007`): session id, resume strength + ref, `transcript_ref` as a reference only (content never rides the extension, per `PORT-JOURNAL`'s "not an artifact store" boundary), provider/model as opaque strings (`INV-014` — the schema must not enumerate provider/model values). Dispatcher/watchtower/preset/policy provenance is split into its own extension, not a field inside `execution-session/v1`.
- Amend `CONTRACT-CAPABILITIES`: a capability MUST NOT be claimed when its durability obligations are unmet — `CAP-EXEC-RESUME-EXACT` specifically requires durable session provenance (`execution-session/v1`) before an adapter may advertise it.

## Must not change

Core/envelope shape: `execution-session/v1` and its dispatcher-provenance sibling use the existing `extensions` transport slots on execution observations and the journal envelope (`PORT-EXEC-002`, `PORT-JOURNAL-ENVELOPE`); no core contract or envelope field changes.

## Acceptance

- `execution-session/v1` satisfies `EXT-001` through `EXT-007`;
- the `CONTRACT-CAPABILITIES` durability-honesty amendment merges before `TASK-M1-005` begins;
- `docs/contracts/durability-responsibilities.md`'s retirement ledger has zero unclassified rows for `work-spec/v1`, `crew-report/v1`, and `execution-session/v1` (each reaches a disposition, even if "planned" or "deferred — see M1b open gate").
