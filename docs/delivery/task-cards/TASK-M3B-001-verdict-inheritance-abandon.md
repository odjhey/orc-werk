---
id: TASK-M3B-001
type: task-card
status: draft
authority: normative
description: Verdict inheritance for re-observed candidates + DEC-ABANDON-ATTEMPT operator recovery record, per the approved issue #76 ruling (also resolves issue #95).
implements: []
verifies: []
---

# TASK-M3B-001 — Verdict inheritance + operator abandon record

## Outcome

The two halves of the approved issue #76 ruling (operator, 2026-08-29):

1. **Verdict inheritance.** A candidate re-observed on a new attempt is
   legal, not a conflict: the kernel resolves it by inheriting the
   existing verdict for that exact candidate identity (assurance is
   candidate-bound — `INV-007`..`INV-010`; the evidence already exists
   and already applies). A previously-rejected candidate re-observed ⇒
   an immediate rejection settlement citing the prior
   `FACT-ASSURE-SETTLED` as basis ⇒ the ordinary retry/exhaustion flow
   proceeds legibly toward `BLOCKED`. A previously-accepted candidate
   re-observed ⇒ immediate acceptance (idempotent-harmless). This
   replaces today's behavior — `ERR-CONFLICT` on
   `FACT-CANDIDATE-OBSERVED` reuse, which permanently wedges the run
   (issue #76's live specimen: `.orc/fix-69-status-resolver`).
2. **Operator abandon record.** A new operator decision record —
   working name `DEC-ABANDON-ATTEMPT` — journaled with who/why/basis,
   legal exactly when an attempt's candidate observation is in
   irrecoverable conflict OR its assurance is unsettleable by any seat
   (issue #95's gap). It consumes the blocking condition and settles the
   attempt as failed-abandoned, letting the run proceed (retry or block)
   honestly. It is an *abandon*, never a verdict: no fabricated
   assurance evidence is created (`INV-003` intact), and role separation
   remains playbook discipline.

## Docs first (hard ordering)

- `STATE-DELIVERY` (`docs/domain/state-machines/delivery.md`): the
  re-observation resolution and the abandon transition.
- `docs/protocol/` records: the new decision record's fields; the
  inherited-settlement's basis citation shape.
- A scenario per wedge shape: same-candidate-on-retry (inheritance) and
  abandoned-attempt recovery — executable-spec style, mapped to tests.
- Affordances: the states these transitions touch get `next:` updates
  derived from the state machine, per the affordance rule.

## In scope

Core reducer/policy changes implementing both halves; CLI recording path
for the operator abandon (config-entry or flag — decided at
implementation, documented); replay compatibility (legacy journals with
the old conflict must still *read*; the preserved specimen
`fix-69-status-resolver` becomes the live regression fixture — after
this card it must replay/render, and an abandon recorded against it must
settle it); conformance additions.

## Out of scope

Findings-in-retry-prompt automation (issue #75 dormant trigger);
adapter-side changes (TASK-M3B-002 owns the no-mistakes guard).

## Acceptance

- Both scenarios pass; the mutation check (revert the inheritance rule)
  turns them red.
- The live specimen `fix-69-status-resolver` replays without
  `ERR-CONFLICT` and can be settled via an abandon record, end to end,
  against the real ledger (read-only until the recorded abandon).
- Issues #76 and #95 closeable on merge.
