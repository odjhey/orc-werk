---
id: TASK-M2-004
type: task-card
status: current
authority: normative
description: Point a second, independent repository's delivery work at an orc-werk ledger — the first true adoption test, pressure-testing PRODUCT-ADOPTION.
implements:
  - PRODUCT-ADOPTION
verifies: []
---

# TASK-M2-004 — orc as ledger for another repo

## Outcome

Run at least one real delivery for a repository other than orc-werk itself
through an orc-werk ledger, exercising `PRODUCT-ADOPTION`'s adoption
ladder from outside the project that built it — no changes to orc-werk
core semantics permitted to make the adoption work.

## In scope

- selecting a candidate second repo and a real (not synthetic) piece of
  work in it;
- running that work's delivery through `orc dispatch`/`status`/`history`
  (or a real adapter, if M2a/M1b are far enough along by dispatch time —
  decided at dispatch, not pre-committed here);
- recording any friction found as a docs gap (per `CLAUDE.md` rule 4) or a
  filed issue, per `DELIVERY-STANCE`'s dogfood-feedback-is-the-backlog
  principle — never worked around silently in code.

## Out of scope

Building bespoke tooling for the second repo beyond what any adopter would
reasonably be expected to set up per `PRODUCT-ADOPTION`'s existing ladder.
If a gap requires new tooling, that itself is the finding to report, not
something to build quietly to make the card look clean.

## Acceptance

- one real delivery in a second, independent repository reaches a
  terminal state through an orc-werk ledger;
- every friction/gap found during the attempt is recorded (docs amendment
  proposal or filed issue), not silently absorbed.
