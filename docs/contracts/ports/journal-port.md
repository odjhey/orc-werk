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
