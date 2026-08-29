---
id: SCN-010
type: scenario
status: current
authority: normative
description: Operator DEC-ABANDON-ATTEMPT consumes an unresolved candidate-observation conflict or an unsettleable Assurance and lets the run proceed honestly.
---

# SCN-010 — Abandoned-attempt recovery

## Purpose

`TASK-M3B-001` (approved ruling, issue #76's PERMANENCE escalation; also
resolves issue #95's operator-override gap). `STATE-DELIVERY` mechanical
fact sequencing item 9 is the executable specification this scenario maps
to. Two independent shapes, both legal grounds for `DEC-ABANDON-ATTEMPT`:
a candidate-observation conflict `SCN-009`'s inheritance rule cannot
resolve, and an Assurance the operator knows (out-of-band) will never
settle — issue #95's adapter-owned in-flight case, where the assurance was
started by a foreign/orphaned session no seat here can observe.

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
   resolves to `BLOCKED` (`reason: attempt-abandoned`) via the same
   `INV-018`/`INV-019` arithmetic every other failed-attempt row uses. No
   `FACT-ASSURE-SETTLED` was ever fabricated for C1 (`INV-003`, `INV-009`).

## Given (unsettleable-assurance shape, #95)
- Work B is ready. `max_attempts = 3`.
- Execution 1 produces Candidate C2. `FACT-ASSURE-STARTED` is journaled
  for C2 (an assurance run began — for example, dispatched to an
  adapter-owned session outside this ledger's own seats, per issue #95).
- No `FACT-ASSURE-SETTLED` ever arrives: the session that owns this
  assurance is orphaned/foreign and no seat here can observe or poll it.
  Ordinary re-dispatch leaves Work B resting at `ASSURING`, pending
  (`STATE-DELIVERY` item 7) — indistinguishable, from journal state alone,
  from an assurance that is merely still genuinely in flight.

## Then (unsettleable-assurance shape)
4. The operator, with out-of-band knowledge that this assurance will never
   settle, records `DEC-ABANDON-ATTEMPT` for Work B (attribution: the
   operator's identity; basis: the unsettled `FACT-ASSURE-STARTED`; data:
   reason, e.g. "adapter session orphaned"). `FACT-ATTEMPT-ABANDONED` is
   journaled for Work B.
5. With attempt 1 of 3 consumed and budget remaining, Work B resolves to
   `READY` — an ordinary `DEC-RETRY` follows on the next dispatch pass,
   starting Execution 2 honestly (no fabricated candidate, no fabricated
   verdict: `INV-003` intact throughout).
6. Nothing about C2's abandoned assurance is asserted as a verdict: had the
   operator instead fabricated a `FACT-ASSURE-SETTLED` to "unstick" Work B,
   that would be a forged verdict, exactly what `DEC-ABANDON-ATTEMPT` is
   designed to avoid (`PROTOCOL-DECISIONS`).

## Mutation check
Removing `FACT-ATTEMPT-ABANDONED`'s legality as a continuation from either
resting point (reverting to: no legal Fact ever consumes an unresolved
candidate-observation conflict or an unsettleable Assurance) turns both
halves of this scenario red: Work A and Work B never leave their resting
points, and no `DEC-RETRY`/`DEC-BLOCK` ever fires for either.

Verifies: `INV-003`, `INV-006`, `INV-008`, `INV-009`, `INV-011`, `INV-012`,
`INV-018`, `INV-019`, `INV-020`.
