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

### PORT-JOURNAL-004 `history`
Read ordered canonical history for one DeliveryRun.

### PORT-JOURNAL-005 `load_projection`
Load/rebuild canonical state from history or an equivalent durable projection.

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
