---
id: PORT-JOURNAL
type: port
status: current
authority: normative
version: 1
description: Canonical orchestration history interface.
---

# JournalPort

## Purpose

Persist what the orchestration kernel observed, decided, and attempted independently from provider-native logs.

## Operations

### PORT-JOURNAL-001 `append_fact`
Append an immutable canonical Fact.

### PORT-JOURNAL-002 `append_decision`
Append an immutable Decision including its basis.

### PORT-JOURNAL-003 `append_effect_record`
Record requested effect identity, dispatch result, and canonical error/result.

The persisted effect record's `data` MUST include a `dispatch_result` field carrying the dispatch outcome as portable data — the canonical result on success, or the canonical error value (per `CONTRACT-ERRORS`) on failure. `dispatch_result` is a reserved key within effect-record `data`: an effect payload MUST NOT define its own `dispatch_result` field, and an attempt to do so MUST be rejected with `ERR-VALIDATION`.

### PORT-JOURNAL-004 `history`
Read ordered canonical history for one DeliveryRun.

### PORT-JOURNAL-005 `load_projection`
Load/rebuild canonical state from history or an equivalent durable projection.

Replay MUST be self-sufficient: it MUST fold history under the same retry budget (`max_attempts`) the run itself used, not an adapter's own default or the reading process's own config. A run's effective `max_attempts` is durably recorded in its `FX-CREATE-WORK` effect record's `data.max_attempts` (`CONTRACT-DURABILITY`'s "Run topology ... and effective retry budget" row, issue #52) — `load_projection` MUST read that value back and pass it to `orc_werk.core.reducer.reduce` (or an equivalent fold) instead of the reducer's own schema default. A journal written before this field existed carries no `data.max_attempts`; `load_projection` MUST fall back to the reducer's schema default (`DEFAULT_MAX_ATTEMPTS`) for such a legacy record, exactly as if the run had used that default — this is a documented read-fallback, not an error, mirroring the issue #55 layout fallback. See `CONF-JOURNAL-003`.

Issue #240 broadens this requirement beyond `load_projection`: this is not a `load_projection`-specific rule but the single authority for EVERY verb's replay of a journal that already has a `FX-CREATE-WORK` record — read-side and write-side, in any process. See `SCN-008`'s budget-authority clause for the full ruling (including match-or-refuse on an explicit `--max-attempts`/config `max_attempts` supplied for an existing run, and the divergence-is-forbidden statement `CONF-JOURNAL-003` now carries).

The JournalPort is not a general artifact store and does not duplicate provider-native transcripts.

## Canonical record envelope

### PORT-JOURNAL-ENVELOPE

Every persisted/interchanged journal record (fact, decision, or effect record) MUST use this canonical portable envelope:

```json
{
  "schema_version": 1,
  "seq": 0,
  "delivery_run_id": "string",
  "kind": "fact | decision | effect",
  "id": "<FACT-*|DEC-*|FX-*>",
  "data": {},
  "extensions": {}
}
```

- `schema_version` is an integer starting at `1` for the v0 envelope; a breaking change to the envelope shape requires a version bump.
- `seq` is a per-`delivery_run_id` monotonically increasing integer. It is the deterministic ordering key required by `CONF-JOURNAL-001` and `CONF-JOURNAL-003`. The JournalPort implementation assigns `seq` on append; append order is authoritative for ordering, and callers never supply `seq`.
- `kind` discriminates which protocol registry `id` resolves against.
- `data` carries the kind-specific required fields: per `PROTOCOL-FACTS` for facts, per `PROTOCOL-DECISIONS` (including basis, per `INV-012`) for decisions, and per `PORT-JOURNAL-003` (effect identity, idempotency key, dispatch result, canonical error/result) for effect records.
- `extensions`, when present, MUST satisfy `CONTRACT-EXTENSIONS`.
- The envelope MUST satisfy the portability constraints already specified by `ARCH-REPOSITORY-STRUCTURE` and `ADR-0003`; this document does not restate them.

### Durable-journal recovery

A durable JournalPort adapter (one backed by an on-disk or otherwise reopenable log) MUST, on reopen: tolerate a single unparseable FINAL record as a torn write — ignore it, and continue the journal from the last good record before it — while rejecting any earlier malformed record with `ERR-VALIDATION`, failing closed on real corruption rather than silently skipping it. This torn-tail tolerance applies only when at least one valid record precedes the unparseable FINAL record in the same journal (watchtower ruling on issue #18). A file containing no valid records at all is not a journal: reading it MUST reject with `ERR-VALIDATION` rather than presenting an empty history — this closes the silent-success-on-wrong-file hole (e.g. a stray or misdirected path resolving to garbage content) while keeping genuine crash recovery, where a real prefix of good records exists, intact.

### Run-id restrictions

An adapter MAY restrict the representable `delivery_run_id` character set for storage safety (for example, characters that are unsafe in a filename or path segment). An adapter that does so MUST reject an out-of-range `delivery_run_id` with `ERR-VALIDATION`.
