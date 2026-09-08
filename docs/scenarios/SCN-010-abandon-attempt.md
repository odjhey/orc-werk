---
id: SCN-010
type: scenario
status: current
authority: normative
description: Operator DEC-ABANDON-ATTEMPT consumes an unresolved candidate-observation conflict, or an Assurance the operator elects not to await settlement for (adapter-orphaned per #95, or externally invalidated per #289), and lets the run proceed honestly.
---

# SCN-010 — Abandoned-attempt recovery

## Purpose

`TASK-M3B-001` (approved ruling, issue #76's PERMANENCE escalation; also
resolves issue #95's operator-override gap and issue #289's
external-invalidation gap). `STATE-DELIVERY` mechanical fact sequencing
item 9 is the executable specification this scenario maps to. Two
independent shapes, both legal grounds for `DEC-ABANDON-ATTEMPT`: a
candidate-observation conflict `SCN-009`'s inheritance rule cannot
resolve, and an Assurance the operator has out-of-band reason not to
await -- issue #95's adapter-owned in-flight case (the assurance was
started by a foreign/orphaned session no seat here can observe), or
issue #289's externally-invalidated-candidate case (the assurance
session is perfectly capable of settling on its own terms, but the
operator already knows -- from something outside this ledger, e.g. a
later commit on the same branch, or a sibling run's own settlement --
that the frozen Candidate it would be judging no longer reflects
reality). Both bases produce the identical mechanical shape below: only
the operator-supplied `reason` differs, never the Fact/Decision
sequence, the attempt cost, or the frozen candidate identity
(`INV-007`/`INV-008`) issue #289 leaves fully intact. No supersede/rebind
verb and no budget waiver exist for either basis -- the sanctioned
recovery is this same abandon, then an ordinary retry (or, once the
budget is exhausted, a new run) that re-observes honestly.

## Given (candidate-observation conflict shape)
- Work A is ready. `max_attempts = 2`.
- Execution 1 produces Candidate C1 (fingerprint `fp-1`); Assurance never
  settles for C1 (no `FACT-ASSURE-SETTLED` — only `FACT-ASSURE-STARTED`
  exists in C1's lineage: an abandoned or crashed first assurance attempt,
  nothing to inherit from per `SCN-009`'s item-8 rule).
- The operator separately abandons that unsettled assurance (the
  ASSURING-unsettleable shape below) so Work A returns to `READY` with
  attempt 1 of 2 already consumed, and no verdict ever recorded for C1.
- Execution 2 re-produces the exact same Candidate C1 (`candidate_id`
  matches, `fingerprint` matches `fp-1`). `FACT-CANDIDATE-OBSERVED` for C1
  is journaled again, naming Execution 2.

## Then (candidate-observation conflict shape)
1. Folding the second `FACT-CANDIDATE-OBSERVED` for C1 does not raise
   `ERR-CONFLICT` and does not crash replay: `SCN-009`'s inheritance rule
   does not apply (no prior `FACT-ASSURE-SETTLED` exists for C1 to
   inherit), so the Work rests at `EXECUTING` marked with an unresolved
   candidate-observation conflict — a normal, non-erroneous resting point
   (item 9), not a hard failure. `orc status`/`orc history` continue to
   render this run without error.
2. The operator records `DEC-ABANDON-ATTEMPT` (attribution: the operator's
   identity; basis: the conflicting `FACT-CANDIDATE-OBSERVED`; data:
   reason) via the CLI operator surface. `FACT-ATTEMPT-ABANDONED` is
   journaled for Work A.
3. With attempt 2 of 2 now consumed and the retry budget exhausted, Work A
   resolves to `BLOCKED` via the same `INV-018`/`INV-019` arithmetic every
   other failed-attempt row uses. No `FACT-ASSURE-SETTLED` was ever
   fabricated for C1 (`INV-003`, `INV-009`). `blocked_reason` is derived
   *eagerly*, the instant `FACT-ATTEMPT-ABANDONED` folds, to the literal
   `attempt-abandoned` (`policy._block_reason`'s reason vocabulary) --
   the same eager-derivation convention every other row in this state
   machine already uses; `blocked_confirmed` stays `False` and no port
   Effect is dispatched by this `--abandon-work` invocation (the
   confirming `DEC-BLOCK`/`FX-BLOCK-WORK`/`FACT-WORK-BLOCKED` is left to a
   later dispatch under the run's real adapters, exactly like the READY
   branch's next attempt, issue #165). Because `blocked_reason` is
   already set, `orc`'s text and JSON projections carry
   `blocked_reason=attempt-abandoned` immediately -- never a transient
   `None`/`null` awaiting a follow-up dispatch (issue #288). The
   operator's full free-form abandon reason is never discarded either: it
   stays durable on `FACT-ATTEMPT-ABANDONED` in history, and the `next:`
   guidance for this Work names the same `attempt-abandoned` reason
   rather than deferring to `orc history`.

## Given (unsettleable-or-invalidated-assurance shape, #95/#289)
- Work B is ready. `max_attempts = 3`.
- Execution 1 produces Candidate C2. `FACT-ASSURE-STARTED` is journaled
  for C2 (an assurance run began — for example, dispatched to an
  adapter-owned session outside this ledger's own seats, per issue #95).
- No `FACT-ASSURE-SETTLED` ever arrives: the session that owns this
  assurance is orphaned/foreign and no seat here can observe or poll it.
  Ordinary re-dispatch leaves Work B resting at `ASSURING`, pending
  (`STATE-DELIVERY` item 7) — indistinguishable, from journal state alone,
  from an assurance that is merely still genuinely in flight.
- Issue #289's variant reaches the identical resting point (Work B at
  `ASSURING`, `FACT-ASSURE-STARTED` journaled for C2, no
  `FACT-ASSURE-SETTLED` yet) without any orphaned session: the assurance
  is live and could still settle on its own terms, but the operator
  already knows -- from something outside this ledger, e.g. `git log` on
  the same branch showing HEAD moved past what C2 froze, or a sibling
  run's own settlement -- that C2 no longer reflects what it should be
  judged against.

## Then (unsettleable-or-invalidated-assurance shape)
4. The operator, with out-of-band knowledge that this assurance is not
   worth letting settle -- whether it never will (issue #95: an
   orphaned/foreign session) or because the Candidate it would judge has
   already been overtaken by something outside the ledger (issue #289: a
   later commit, a sibling run's settlement), records
   `DEC-ABANDON-ATTEMPT` for Work B (attribution: the operator's
   identity; basis: the unsettled `FACT-ASSURE-STARTED`; data: reason,
   e.g. "adapter session orphaned" or "sibling run superseded this
   candidate"). `FACT-ATTEMPT-ABANDONED` is journaled for Work B -- this
   settles the *attempt* as abandoned; it never fabricates a verdict for
   C2 and never rebinds or supersedes C2's own frozen identity
   (`INV-007`/`INV-008`).
5. With attempt 1 of 3 consumed and budget remaining, Work B resolves to
   `READY` — an ordinary `DEC-RETRY` follows on the next dispatch pass,
   starting Execution 2 honestly (no fabricated candidate, no fabricated
   verdict: `INV-003` intact throughout). Because this branch leaves the
   next attempt's `FX-START-EXECUTION` to a later dispatch under the run's
   real adapters (issue #165), there is no `blocked_reason` to confirm
   here — Work B is not `BLOCKED`.
6. Nothing about C2's abandoned assurance is asserted as a verdict: had the
   operator instead fabricated a `FACT-ASSURE-SETTLED` to "unstick" Work B,
   that would be a forged verdict, exactly what `DEC-ABANDON-ATTEMPT` is
   designed to avoid (`PROTOCOL-DECISIONS`).

## Additional note

Like `orc cancel` (`SCN-011` item 8), `--abandon-work` requires only the
run's own journal to determine legality and act: an unloadable or
schema-invalid persisted config — for example one still naming an adapter
removed by a later release (`ADR-0005`) — never blocks it (issue #236). An
ordinary `orc dispatch` of that same config is refused unchanged; only this
journal-only escape hatch opens.

## Mutation check
Removing `FACT-ATTEMPT-ABANDONED`'s legality as a continuation from either
resting point (reverting to: no legal Fact ever consumes an unresolved
candidate-observation conflict or an unsettleable Assurance) turns both
halves of this scenario red: Work A and Work B never leave their resting
points, and no `DEC-RETRY`/`DEC-BLOCK` ever fires for either. Separately,
reverting the eager `blocked_reason` derivation in the
`FACT-ATTEMPT-ABANDONED` reducer branch back to leaving `blocked_reason`
unset until the later `FACT-WORK-BLOCKED` confirmation (issue #288's
prior shape) turns step 3 red: `orc status` right after the abandon
would again show `blocked_reason=None` for a terminal Work.

Verifies: `INV-003`, `INV-006`, `INV-007`, `INV-008`, `INV-009`, `INV-011`,
`INV-012`, `INV-018`, `INV-019`, `INV-020`.
