---
id: TASK-M0-006
type: task-card
status: current
authority: normative
description: Implement port interfaces and the shared canonical serialization foundation.
implements:
  - PORTS-INDEX
  - PORT-WORK-GRAPH
  - PORT-EXECUTION
  - PORT-CANDIDATE
  - PORT-ASSURANCE
  - PORT-JOURNAL
verifies: []
---

# TASK-M0-006 — Port interfaces and serialization foundation

## Outcome

Provide `orc_werk.ports` language-level interfaces mirroring the normative port documents (operation signatures, canonical observation shapes, canonical error values from `CONTRACT-ERRORS` rather than Python exception payloads), plus shared portable (de)serialization helpers for the canonical journal record envelope (`PORT-JOURNAL-ENVELOPE`) and extension passthrough (`CONTRACT-EXTENSIONS`).

## Depends on

`TASK-M0-001`.

## Must not change

Provider contracts, adapter mappings, or core domain semantics.

## Acceptance

- port interfaces are importable and depend only on `orc_werk.core` canonical types; no provider imports;
- capability-advertisement surface is present for `INV-013`/`SCN-006`;
- `ports -> adapters` remains a forbidden dependency per `ARCH-REPOSITORY-STRUCTURE`;
- shared serialization helpers round-trip the canonical envelope from `PORT-JOURNAL-ENVELOPE` losslessly.
