---
id: SCN-009
type: scenario
status: current
authority: normative
description: A candidate re-observed on a later attempt inherits its prior verdict instead of raising ERR-CONFLICT.
---

# SCN-009 — Verdict inheritance on candidate re-observation

## Purpose

`TASK-M3B-001` (approved ruling, issue #76): replaces the pre-existing
behavior where `FACT-CANDIDATE-OBSERVED` reusing a `candidate_id` already
present in a Work's lineage raised `ERR-CONFLICT` unconditionally — a
permanent wedge, since the journal is append-only and the offending Fact
was already durably recorded by the time the conflict surfaced on replay
(the live specimen: `.orc/fix-69-status-resolver`, preserved read-only).
`STATE-DELIVERY` mechanical fact sequencing item 8 is the executable
specification this scenario maps to.

## Given (rejected-then-inherited, drives toward BLOCKED)
- Work A is ready. `max_attempts = 2`.
- Execution 1 produces Candidate C1 (fingerprint `fp-1`).
- Assurance rejects C1: `FACT-ASSURE-SETTLED(rejected)` for C1.
- Retry budget is available (attempt 1 of 2), so Work A returns to `READY`
  and Execution 2 starts.
- Execution 2 re-produces the *exact same* Candidate C1 — identical
  `candidate_id` and `fingerprint` (an unchanged worktree re-executed, or a
  resumed provider session that reproduces the same content) —
  `FACT-CANDIDATE-OBSERVED` for C1 is journaled again, naming Execution 2.

## Then (rejected-then-inherited)
1. No `ERR-CONFLICT` is raised folding the second `FACT-CANDIDATE-OBSERVED`
   for C1. The reducer recognizes the exact re-observation (`INV-006`:
   fingerprint matches the fingerprint already on record for
   `candidate_id`) and inherits C1's `rejected` verdict.
2. No new `FACT-ASSURE-SETTLED` is journaled for this re-observation — no
   fresh assurance evidence is fabricated (`INV-003`). The only
   `FACT-ASSURE-SETTLED` in the full journal is the one from attempt 1.
3. Work A moves immediately toward the ordinary rejected-verdict path: with
   attempt 2 of 2 already consumed and the retry budget exhausted, Work A
   resolves to `BLOCKED` (`reason: retry-budget-exhausted`) — no attempt 3
   is dispatched, no assurance is re-requested for C1.
4. The `DEC-BLOCK` that resolves Work A cites the *attempt 1*
   `FACT-ASSURE-SETTLED(rejected)` fact as its basis (`INV-012`) — the
   inherited-settlement basis shape (`PROTOCOL-FACTS`): a basis fact from
   an earlier attempt than the Decision's current attempt is exactly how
   an inherited settlement reads in the journal.
5. Replaying the full journal from scratch (`PORT-JOURNAL-005
   load_projection`) produces this identical projection deterministically,
   every time — no crash, no `ERR-CONFLICT`, stable across repeated reads
   (`INV-020` spirit).

## Given (accepted-then-reobserved, idempotent-harmless)
- Work B is ready. `max_attempts = 3`.
- Execution 1 produces Candidate C2 (fingerprint `fp-2`).
- Assurance accepts C2: `FACT-ASSURE-SETTLED(accepted)` for C2.
- `DEC-ACCEPT`/`FX-COMPLETE-WORK`/`FACT-WORK-COMPLETED` follow normally;
  Work B reaches `ACCEPTED`.

## Then (accepted-then-reobserved)
6. Work B's lineage never legally re-executes after `ACCEPTED` under v0
   policy (there is no transition table row that retries a completed
   Work), so no second `FACT-CANDIDATE-OBSERVED` for C2 occurs in the
   ordinary run loop. The inheritance rule is nonetheless defined for this
   shape (defensive, e.g. a hand-constructed or corrective-run journal that
   re-observes C2 against Work B before any further state change): were
   `FACT-CANDIDATE-OBSERVED` for C2 folded again, it would resolve
   immediately to `ACCEPTED` citing the original `FACT-ASSURE-SETTLED(accepted)`
   as basis — idempotent-harmless, never a second, distinct acceptance
   (`INV-003` is not violated: acceptance still traces to one real
   assurance settlement, merely re-cited).

## Mutation check
Reverting the reducer's verdict-inheritance rule (folding a reused
`candidate_id` unconditionally as `ERR-CONFLICT`, the pre-`TASK-M3B-001`
behavior) turns the "rejected-then-inherited" half of this scenario red:
folding Work A's second `FACT-CANDIDATE-OBSERVED` raises `ERR-CONFLICT`
instead of resolving to `BLOCKED`.

Verifies: `INV-003`, `INV-006`, `INV-007`, `INV-008`, `INV-009`, `INV-010`,
`INV-011`, `INV-012`, `INV-018`, `INV-019`, `INV-020`.
