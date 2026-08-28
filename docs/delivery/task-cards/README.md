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

M1 cards, in dependency order:

1. `TASK-M1-001` SCN-007 and the `STATE-DELIVERY` pending-mode clause (docs-first)
2. `TASK-M1-003` CLI UX batch #16/#17/#18/#23, including the #18 `PORT-JOURNAL` docs amendment (depends on `TASK-M1-001`)
3. `TASK-M1-002` pending/incremental dispatch implementation (depends on `TASK-M1-001`)
4. `TASK-M1-006` agent CLI guidance playbook — M1a+ push mode (depends on `TASK-M1-001`, `TASK-M1-002`)
5. `TASK-M1-004` durability-responsibilities contract, `execution-session/v1` registration, `CONTRACT-CAPABILITIES` durability amendment (no dependencies within M1)
6. `TASK-M1-005` Claude Code headless ExecutionPort + real-artifact CandidatePort + conformance (depends on `TASK-M1-004` and `TASK-M1-002`)

`TASK-M1-002` and `TASK-M1-003` both depend only on `TASK-M1-001` and are independent of each other, so they may ship in parallel worktrees; `TASK-M1-004` has no M1 dependency and may start immediately alongside `TASK-M1-001`. `TASK-M1-006` is the M1a+ stage card: it is authored only after the SCN-007 command surface is fixed and implemented (guidance must not precede the commands it documents). `TASK-M1-005` is the only M1b card and gates on both the durability contract (`TASK-M1-004`) and the pending-mode implementation (`TASK-M1-002`) it dogfoods against.
