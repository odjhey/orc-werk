---
id: TASK-CARDS-INDEX
type: index
status: current
authority: informative
description: Bounded delivery task cards derived from normative contracts.
---

# Task cards

M0 cards, in dependency order:

1. `TASK-M0-001` core model and pure transition engine
2. `TASK-M0-006` port interfaces and serialization foundation (depends on `TASK-M0-001`)
3. `TASK-M0-002` memory WorkGraphPort + conformance (depends on `TASK-M0-001`, `TASK-M0-006`)
4. `TASK-M0-003` scripted Execution/Candidate/Assurance adapters (depends on `TASK-M0-001`, `TASK-M0-006`)
5. `TASK-M0-004` JournalPort + replay projection (depends on `TASK-M0-001`, `TASK-M0-006`)
6. `TASK-M0-005` CLI dispatch/status/history and golden scenarios

Card numbering reflects order of authorship, not delivery sequence; `TASK-M0-006` was split out of the original decomposition after `TASK-M0-002`/`003`/`004` were authored, so it depends on `TASK-M0-001` but is itself a dependency of `TASK-M0-002`/`003`/`004`.
