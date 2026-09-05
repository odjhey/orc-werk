---
id: SCN-021
type: scenario
status: current
authority: normative
description: An inconclusive assurance settlement re-requests assurance of the same candidate within a bounded assurance budget; exhaustion blocks; execution retry budget is never consumed; legacy journals replay unchanged.
---

# SCN-021 — Bounded assurance re-request on `inconclusive`

## Purpose

Executable specification for `ADR-0006`: `STATE-DELIVERY`'s two `inconclusive` rows, `INV-021`'s assurance budget, `INV-020`'s `assurance_number` key component, and the legacy read-fallback. Replaces the single-row terminal treatment `SCN-007` step 13 previously described.

## Given (re-request, then accepted)

- Work A is ready. `max_attempts = 3`, `max_assurance_attempts = 2` (the default).
- Execution 1 produces Candidate C1 (fingerprint `fp-1`).
- Assurance 1 of C1 settles `inconclusive` with `evidence_refs` naming why (e.g. a verifier log).
- Assurance 2 of C1 settles `accepted`.

## Then (re-request, then accepted)

1. Folding `FACT-ASSURE-SETTLED(inconclusive)` leaves Work A at `ASSURING`, not `BLOCKED`, with no current assurance in flight.
2. Policy emits `DEC-REQUEST-ASSURANCE` whose `basis` cites that `inconclusive` `FACT-ASSURE-SETTLED` (`INV-012`), and `FX-START-ASSURANCE` for the *same* `candidate_id`/`fp-1` (`INV-007`).
3. The new effect's idempotency key equals assurance 1's key plus an `assurance_number` component of `2` (`INV-020`); assurance 1's key is unchanged from the pre-`INV-021` form.
4. `FACT-ASSURE-STARTED` is journaled with a *new* `assurance_id`; the first assurance's record and evidence are retained, never overwritten or relabeled (`P-008`, `INV-007`).
5. `attempt_number` remains `1`: no `FACT-EXEC-STARTED` is journaled, and the execution retry budget is untouched (`INV-018`, `INV-021`).
6. Folding assurance 2's `FACT-ASSURE-SETTLED(accepted)` moves Work A to `ACCEPTED`; `DEC-ACCEPT`/`FX-COMPLETE-WORK`/`FACT-WORK-COMPLETED` follow as in `SCN-001`.
7. `orc history` shows two assurance lifecycles for one candidate within one attempt; `orc status`/`next:` while resting between them names the assurance index (e.g. "assurance 2 of 2") so a verify seat knows a re-request is in progress.

## Given (budget exhausted)

- As above, but assurance 2 of C1 also settles `inconclusive`.

## Then (budget exhausted)

8. Work A moves to `BLOCKED`; policy emits `DEC-BLOCK` with `reason: assurance-inconclusive`, its `basis` citing the *second* `inconclusive` settlement.
9. No third `FX-START-ASSURANCE` is dispatched. `FACT-WORK-BLOCKED` is the only legal continuation.
10. `attempt_number` is still `1`; `INV-018`'s cumulative execution count was never advanced by either assurance.

## Given (legacy journal)

- A journal whose `FX-CREATE-WORK` effect record carries `data.max_attempts` but no `data.max_assurance_attempts`, and which contains `FACT-ASSURE-SETTLED(inconclusive)` followed by `DEC-BLOCK`/`FACT-WORK-BLOCKED` — the pre-`ADR-0006` shape.

## Then (legacy journal)

11. `load_projection` folds that run under an assurance budget of `1` (the read-fallback `INV-021` names), so the recorded `FACT-WORK-BLOCKED` replays as a legal continuation of `BLOCKED` — not `ERR-CONFLICT` from a wrongly derived `ASSURING` (`CONF-JOURNAL-003`, `SCN-008`'s legacy-fallback shape).
12. A journal written *after* `ADR-0006` records `data.max_assurance_attempts` at creation; an explicit config/flag value on a later dispatch that disagrees with it is refused with `ERR-VALIDATION` exactly as `SCN-008`'s issue #240 R2 refuses a disagreeing `max_attempts`.

## Given (re-observed candidate with inconclusive-only history)

- Work B's lineage contains Candidate C2 whose only settled assurances are `inconclusive`, and a later Execution re-observes C2 exactly (same `candidate_id` and fingerprint). The ordinary v0 path that reaches this shape is the abandon route: assurance 1 of C2 settles `inconclusive`, the budget re-requests assurance 2, that assurance never settles, the operator records `DEC-ABANDON-ATTEMPT` (`STATE-DELIVERY` item 9 — legal at `ASSURING` with the current assurance unsettled), the Work returns to `READY`, and the next Execution re-produces C2 unchanged. The abandoned assurance is not a settlement, so C2's only settled assurance is the `inconclusive` one.

## Then (re-observed candidate with inconclusive-only history)

13. The re-observation is legal and neither inherits a verdict (`STATE-DELIVERY` item 8 inherits only `accepted`/`rejected`) nor rests as an item 9 conflict. Work B enters `ASSURING` with a fresh assurance budget for the new attempt, and `DEC-REQUEST-ASSURANCE` follows normally.

## Mutation check

Reverting the reducer to the pre-`ADR-0006` rule (`inconclusive` → `BLOCKED` unconditionally) turns items 1–7 red: Work A blocks after assurance 1 and no `DEC-REQUEST-ASSURANCE` is emitted. Dropping the `assurance_number` key component turns item 3 red: the second `FX-START-ASSURANCE` collides with the first and is skipped as already applied.

## Verifies

- `INV-007`, `INV-009`, `INV-012`, `INV-018`, `INV-019`, `INV-020`, `INV-021`
- `CONF-ASSURE-004`, `CONF-ASSURE-008`, `CONF-JOURNAL-003`
- `STATE-DELIVERY` item 11, `DEC-REQUEST-ASSURANCE`, `DEC-BLOCK`, `FX-START-ASSURANCE`
