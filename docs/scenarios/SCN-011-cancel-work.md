---
id: SCN-011
type: scenario
status: current
authority: normative
description: Operator DEC-CANCEL closes non-terminal Work as terminal CANCELLED without fabricating a verdict.
---

# SCN-011 — Operator cancellation

## Purpose

`STATE-DELIVERY` mechanical fact sequencing item 10 is the executable
specification this scenario maps to. Cancellation lets an operator
truthfully close Work without acceptance when it would otherwise remain
non-terminal. It is a journal-only terminal transition, not a verdict.

## Given
- Work A is in `READY`.
- Work B is in `EXECUTING`, with an Execution currently in flight.
- Work C is in `ASSURING`, with an Assurance currently in flight.
- The operator supplies an identity and a free-form reason for each close.

## Then
1. For Work A, the operator records `DEC-CANCEL` (operator attribution;
   basis: an appropriate current-state Fact; data: reason), followed by
   `FACT-WORK-CANCELLED`. Work A transitions directly from `READY` to
   terminal `CANCELLED` and is confirmed in that same Fact.
2. The same pair transitions Work B from `EXECUTING` to terminal
   `CANCELLED`; replay leaves no current execution, assurance, or
   candidate-conflict marker.
3. The same pair transitions Work C from `ASSURING` to terminal
   `CANCELLED`; replay leaves no assurance-in-flight marker.
4. No port Effect is emitted for any cancellation, and no
   `FACT-ASSURE-SETTLED` is fabricated (`INV-003`, `INV-009`).
5. Attempting cancellation from terminal `ACCEPTED` or `BLOCKED` is
   rejected with `ERR-CONFLICT`. Cancellation from already-`CANCELLED` is
   likewise rejected.
6. A second `FACT-WORK-CANCELLED` for the same Work is rejected with
   `ERR-CONFLICT`.
7. Replaying each valid journal deterministically reconstructs the same
   clean, confirmed terminal `CANCELLED` projection. Such a run is settled,
   not active.

## Mutation check
Removing `FACT-WORK-CANCELLED`'s transition branch, omitting `CANCELLED`
from terminal/reachable states, or treating `CANCELLED` as active turns
this scenario red: cancellation is rejected or replay/reporting leaves the
operator-closed Work perpetually in flight.

Verifies: `INV-003`, `INV-009`, `INV-011`, `INV-012`, `INV-020`,
`CONF-JOURNAL-004`.
