---
id: EXT-CREW-REPORT-V1-SCHEMA
type: contract
status: current
authority: normative
version: 1
description: Portable schema for crew-report/v1.
---

# `crew-report/v1` schema

The extension payload has this conceptual shape:

```text
CrewReportV1 {
    turn: integer
    claimed_verdict: "done" | "waiting" | "needs-action" | "failed" | "blocked"
    reason?: string
    did?: string
    pending?: string
    inputs_needed?: [string]    # opaque, ref-only — see semantics.md
    artifact_refs?: [string]    # opaque, ref-only — see semantics.md
}
```

Canonical transport example (as a snapshot riding an execution observation's or journal record's `extensions` slot):

```json
{
  "extensions": {
    "crew-report/v1": {
      "turn": 3,
      "claimed_verdict": "waiting",
      "reason": "blocked on operator input",
      "did": "opened the migration draft PR",
      "pending": "awaiting review sign-off",
      "inputs_needed": ["opaque-input-ref-1"],
      "artifact_refs": ["opaque-artifact-ref-1"]
    }
  }
}
```

This transports on the existing `extensions` slots already defined by `PORT-EXEC-002`'s execution observation and `PORT-JOURNAL-ENVELOPE`'s journal record envelope when a report rides one as a snapshot; no core or envelope field changes. The adapter-owned append-only log (`docs/extensions/crew-report/README.md`'s "Durable ownership" section) is a distinct durable structure from this transport shape — the log's own record envelope is an adapter/reference-implementation concern (`TASK-M1-007`), not restated here; each of its records carries at minimum this payload plus `delivery_run_id` and `execution_id`.

## Required fields

The payload MUST contain:

- `turn`;
- `claimed_verdict`.

These two fields identify which turn this report describes and what its producer currently claims about it; everything else is present only when the producer has it and chooses to report it.

`reason`, `did`, `pending`, `inputs_needed`, and `artifact_refs` are each independently optional. A producer that has nothing to say for one of them simply omits it (`EXT-005`); omission is not an error.

## Field rules

### `turn`

A non-negative integer, monotonically non-decreasing within one execution's report sequence as understood by the producer. `turn` is the producer's own turn counter, distinct from `PORT-JOURNAL-ENVELOPE`'s `seq` (which is a JournalPort-assigned, per-`delivery_run_id` ordering key) and from the adapter-owned log's own append order — a consumer MUST NOT assume `turn` values are contiguous or globally unique across executions; they are only meaningful within the reports of one execution.

### `claimed_verdict`

MUST be exactly one of `"done"`, `"waiting"`, `"needs-action"`, `"failed"`, or `"blocked"`; no other value is valid. See the "`claimed_verdict`, not `verdict`" rationale below for why this field is not named `verdict`.

A `claimed_verdict` of `"done"` is a claim that the producer believes its work is complete — it is not, and MUST NOT be treated as, Work acceptance (`INV-003`) or a canonical execution outcome (`PORT-EXEC-002`). See [Semantics](semantics.md).

### `reason`, `did`, `pending`

Independently optional, free-form strings describing, respectively: why the producer holds this `claimed_verdict` (`reason`), what the producer did this turn (`did`), and what the producer considers still pending (`pending`). None of these three fields is opaque in the `INV-014` sense — they are free-text narration, not provider-identifier vocabulary — but none of them carries canonical meaning either; they are informative content only.

### `inputs_needed`, `artifact_refs`

Each an independently optional array of opaque, ref-only strings. `inputs_needed` names inputs the producer believes it is waiting on; `artifact_refs` names artifacts the producer produced or points to. Neither array MUST carry inlined content — every element is a reference only. See the ref-only rule below.

## `claimed_verdict`, not `verdict`

This schema deliberately does not use the field name `verdict` that issue #12's original proposal used. The field is `claimed_verdict` so that no consumer — human or automated — can mistake a crew's self-report for `PORT-ASSURANCE`'s canonical verdict vocabulary. This is a direct application of two existing rules, not a new one:

- `EXT-003` ("no canonical override"): an extension MUST NOT redefine, contradict, or override canonical fields such as assurance verdict.
- `INV-003` ("done is a claim, not a fact"): execution completion/reporting is not equivalent to Work acceptance.

A field literally named `verdict` sitting next to `PORT-ASSURANCE`'s canonical verdict values is an ambient invitation to violate both. `claimed_verdict` closes that gap lexically, not just procedurally.

## Ref-only rule (`inputs_needed`, `artifact_refs`)

Every element of `inputs_needed` and `artifact_refs` is a reference, never a content payload — mirroring `execution-session/v1`'s `transcript_ref` rule and `PORT-JOURNAL`'s "not an artifact store" boundary. A component that persists a `crew-report/v1` payload (the adapter-owned log, or a `JournalPort`/execution-observation snapshot) MUST persist each reference string unchanged and MUST NOT dereference, fetch, or inline the referenced content as part of that persistence. Resolving a reference into actual content is the concern of whatever artifact/input store the reference names, outside any Orc Werk contract.

## Portability

The payload MUST satisfy `EXT-006` and therefore use only portable JSON-compatible values.

## CONF-EXT obligations

- `CONF-EXT-001`: the payload contains only JSON-compatible values and round-trips without implementation-language-specific objects.
- `CONF-EXT-002`: a consumer that does not understand `crew-report/v1` still processes the enclosing execution observation, journal record, or adapter-owned log entry without change to canonical meaning.
- `CONF-EXT-003`: a component that advertises lossless extension round-trip preserves this payload unchanged, including unknown future fields within it, per `EXT-005`.
- `CONF-EXT-004`: nothing in this payload can override canonical execution outcome, Work identity/acceptance, candidate identity, or decision identity, per `EXT-003`.
- `CONF-EXT-005` (capability honesty): a provider that reports crew reports for an execution produces, for every reported turn, a payload with a valid `turn` and `claimed_verdict` per this schema. A provider that cannot durably persist the report history (per the "Durable ownership" section in `docs/extensions/crew-report/README.md`) does not claim durable report history for that execution.
- `CONF-EXT-006` (core ignorance): core reducer/state-machine tests prove that changing a `crew-report/v1` payload — including its `claimed_verdict` — while keeping canonical facts identical does not change generic core transitions or decisions under a policy that does not explicitly consume this extension. A `claimed_verdict` of `"done"` MUST NOT, by itself, cause any canonical state transition.

## Versioning

Adding a new required field, changing an existing field's meaning, adding ack/open-item state into this schema, or renaming `claimed_verdict` requires a new extension version (`crew-report/v2`) rather than a silent change to `v1`.
