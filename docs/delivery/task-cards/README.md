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
6. `TASK-M1-007` `crew-report/v1` registration and its file-based reference report log — sequenced at the start of stage M1a+, before phase M1b (implementable ahead of `TASK-M1-006`, most useful once it lands)
7. `TASK-M1-005` acpx (ACP) ExecutionPort driving Pi + real-artifact CandidatePort + conformance (depends on `TASK-M1-004` and `TASK-M1-002`)

`TASK-M1-002` and `TASK-M1-003` both depend only on `TASK-M1-001` and are independent of each other, so they may ship in parallel worktrees; `TASK-M1-004` has no M1 dependency and may start immediately alongside `TASK-M1-001`. `TASK-M1-006` is the M1a+ stage card: it is authored only after the SCN-007 command surface is fixed and implemented (guidance must not precede the commands it documents). `TASK-M1-007` is implementable before `TASK-M1-006` lands (it depends only on `EXT-CREW-REPORT-V1`, registered alongside it, not on the playbook's content), but is sequenced at the start of M1a+ because that is where its output first becomes useful. `TASK-M1-005` is the only M1b card and gates on both the durability contract (`TASK-M1-004`) and the pending-mode implementation (`TASK-M1-002`) it dogfoods against.

`TASK-M1-008` (human run report) is a presentation add-on with no M1-internal dependency beyond merged M1a surfaces; it runs in parallel with `TASK-M1-005` and touches only the CLI layer.

M2 cards, reshaped per operator review (2026-08-28; see `docs/delivery/M2-close-the-loop.md`'s "Deferred (M2 reshape)" section), in dependency order:

1. `TASK-M2-001` no-mistakes `PORT-ASSURANCE` adapter + `CONF-ASSURE-*` (no M2-internal dependency; depends on the merged M1b acp adapter for the delivery it assures)
2. `TASK-M2-006` Beads mirror — write-only projection of run/work state and briefs into a shared, label-scoped `bd` database, per the ratified issue #47 posture; authority graduation dormant (no M2-internal dependency; depends on the merged M1b acp adapter for the run data it mirrors)
3. `TASK-M2-003` multi-work real DAGs through the acp adapter — reframed as a practice run: exercises and populates the `TASK-M2-006` mirror and the issue #41 dependency-tree view, and harvests per-work cost/config findings (benefits from, and is intended to sequence after, `TASK-M2-006` landing first; not a hard blocker)
4. `TASK-M2-004` orc as ledger for another repo — first true adoption test, **gated**: sequenced last among the cards that remain in M2 scope, explicitly depending on `TASK-M2-001` and `TASK-M2-006` landing first (operator ruling — the demo is only compelling with the automatic verdict seat and the portfolio view already in place)

**Deferred out of M2** (recorded on the milestone's deferred list with a named pull trigger each): `TASK-M2-002` (`acpx claude` second-agent provider-swap proof) and `TASK-M2-005` (policy parameterization v1). Both card files remain in place with their design intact; neither is scheduled by this milestone.

`TASK-M2-001` and `TASK-M2-006` are independent of each other and may ship in parallel worktrees. `TASK-M2-003` shares the acp adapter surface with `TASK-M2-001`, so sequencing to avoid worktree collisions is a watchtower call at dispatch; it is also sequenced after `TASK-M2-006` for its mirror/report-harvesting purpose. `TASK-M2-004` is gate-blocked on `TASK-M2-001` + `TASK-M2-006` and is the last M2 card to start, regardless of numbering.
