---
id: TASK-M2-001
type: task-card
status: current
authority: normative
description: Real PORT-ASSURANCE adapter backed by no-mistakes, returning review-findings/v1, proven by CONF-ASSURE.
implements:
  - PORT-ASSURANCE
verifies: []
---

# TASK-M2-001 — no-mistakes AssurancePort

## Outcome

A real `PORT-ASSURANCE` provider backed by `no-mistakes` automates the
verdict seat: it requests/inspects assurance for a candidate and settles
`accepted`/`rejected`/`inconclusive` the way an operator does today, using
`review-findings/v1` (already-registered `EXT-REVIEW-FINDINGS-V1`) as its
structured findings channel via `CAP-ASSURE-STRUCTURED-FINDINGS`.

## In scope

- adapter implementation under `src/orc_werk/` (adapters layer only);
- mapping doc under `docs/adapters/no-mistakes/`;
- `CONF-ASSURE-001` through `CONF-ASSURE-004` re-run against the real
  adapter (stub-subprocess harness pattern, matching the acp adapter's
  precedent).

## Out of scope

`review-findings/v1` schema changes (consumed as-is); the second-agent
provider-swap proof (`TASK-M2-002`).

## Acceptance

- `CONF-ASSURE-001` through `-004` pass against the real adapter;
- a real candidate is assured end-to-end with `review-findings/v1`
  findings visible in the settled observation's `extensions`;
- no `PORT-ASSURANCE` contract change required by the implementation (if
  one is discovered to be necessary, it is proposed as a docs amendment
  first, per `CLAUDE.md` rule 4, before this card is considered complete).
