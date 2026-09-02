---
id: EXT-EXECUTION-SESSION-V1
type: extension
status: current
authority: normative
version: 1
description: Durable provider session/resume provenance extension for execution observations and journal records.
---

# `execution-session/v1`

`execution-session/v1` is an optional extension carrying durable provider session and resume provenance for an `Execution`. It is registered per `TASK-M1-004`, ahead of the first real `PORT-EXECUTION` adapter (`TASK-M1-005`), per the watchtower assessment on issue #12: `CAP-EXEC-RESUME-EXACT` without durable session provenance is exactly the capability-without-durability dishonesty `CONTRACT-DURABILITY` and the `CONTRACT-CAPABILITIES` durability-honesty amendment target.

It is intentionally not part of generic `Execution` semantics. `PORT-EXECUTION`'s explicit non-semantics (model identity, subagent visibility, transcript access, provider tool-call events, terminal/pane identity) are unchanged by this extension; it only gives those provider-native facts, when a provider chooses to carry them, a durable and portable place to live.

## Purpose

Preserve what a provider needs to resume the exact same native session, and what a provider needs to identify the session for inspection, debugging, and operator continuity — without making any of it part of generic `Execution` semantics or branching core behavior on provider identity (`INV-014`).

## Scope rules

- **Opaque strings.** `provider`, `native_session_id`, and every field inside `profile` (`model`, `effort`, `permission_mode`) are opaque, provider-defined free-form strings. This schema MUST NOT enumerate provider or model values — doing so would put provider vocabulary into a normative core-adjacent contract, which `INV-014` forbids. Consumers MUST treat these fields as uninterpreted identifiers for storage, display, and equality comparison only.
- **Ref-only content.** `transcript_ref` (and any other artifact-provenance field this extension carries) is a reference, never a content payload. The referenced content never rides this extension, the journal envelope, or any other Orc Werk canonical structure, per `PORT-JOURNAL`'s "not an artifact store" boundary. See [Semantics](semantics.md).
- **Dispatcher provenance is a separate extension.** Watchtower/preset/policy attribution (what dispatched this execution and under what policy) is explicitly split out of `execution-session/v1` per the watchtower assessment on issue #12. It is recorded as a planned, unregistered future extension in `CONTRACT-DURABILITY`'s ownership matrix, not a field here.
- **No canonical override.** Per `EXT-003`, this extension never redefines execution outcome, work identity, candidate identity, or decision identity; it is additive provenance only.

## Durability obligation

Per the `CONTRACT-CAPABILITIES` capability-durability amendment: an adapter MUST NOT advertise `CAP-EXEC-RESUME-EXACT` unless it durably persists the `execution-session/v1` provenance required to reconstruct the exact session. See `CONTRACT-DURABILITY` for the full capability -> durable-information -> owner -> contract -> conformance mapping.

## Historical passthrough

Issue #223's short-lived ship-seat `orc record --outcome` implementation routed `--evidence-ref` values through an `{"evidence_refs": [...]}` payload under this extension's key, ahead of that extension's registered schema (which declares `provider`/`native_session_id` required and carries no `evidence_refs` field) -- a schema-nonconforming emission (issue #224). Issue #224 repoints that verb to canonical `artifact_refs` on `FACT-EXEC-SETTLED` (`PROTOCOL-FACTS`) and removes the `execution-session/v1` emission entirely. Journals written during that short window still carry the old payload; per `CONF-EXT` unknown/nonconforming-field tolerance, it is preserved as opaque historical passthrough with no migration, never validated against this schema retroactively.

## Files

- [Schema](schema.md)
- [Semantics](semantics.md)
- [Examples](examples.md)

## Related

- `CONTRACT-EXTENSIONS`
- `CONTRACT-DURABILITY`
- `PORT-EXECUTION`
- `PORT-JOURNAL`
- `CAP-EXEC-RESUME-EXACT`
- `CAP-EXEC-RESUME-BEST-EFFORT`
- `INV-013`
- `INV-014`
