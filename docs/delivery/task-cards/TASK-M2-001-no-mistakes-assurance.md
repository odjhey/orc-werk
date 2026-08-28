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

## UX sketch (operator-reviewed flow, M2 reshape)

The operator-reviewed end-to-end shape this adapter is expected to
produce, mirroring the `acp` `PORT-EXECUTION` adapter's wiring pattern
(`docs/adapters/acp/mapping.md`) on the assurance side of the loop.
Illustrative — exact config-key naming is decided at implementation time,
consistent with the M2 task-card README's "details firm up at dispatch"
note:

1. `orc dispatch` — Pi executes the Work via the acp `PORT-EXECUTION`
   adapter; the run rests at exit `3` (pending) while `EXECUTING`, exactly
   as it does today under push mode (`PLAYBOOK-AGENT-CLI`).
2. A candidate is observed (`FACT-CANDIDATE-OBSERVED`); assurance is
   auto-requested (`DEC-REQUEST-ASSURANCE`) — no operator action, this is
   the automation this card delivers relative to today's operator-recorded
   verdict.
3. The `no-mistakes` pipeline runs against the observed candidate; while it
   is in flight, re-`dispatch` again rests at exit `3` (pending,
   `assurance-verdict`) — the same poll shape execution already has, now
   on the assurance side.
4. The verdict lands: `accepted` → the run proceeds toward exit `0`
   (`DEC-ACCEPT` → `FX-COMPLETE-WORK`); `rejected` → `DEC-RETRY` (bounded
   by the Work's retry budget, unchanged cause-blind-but-bounded default
   policy, `docs/domain/state-machines/delivery.md`).
5. `evidence_refs` on the settled assurance observation is the
   `no-mistakes` run report reference (not a narrative summary — an
   externally resolvable artifact, matching `PLAYBOOK-AGENT-CLI`'s
   candidate/evidence discipline).
6. Structured findings ride `review-findings/v1` (`EXT-REVIEW-FINDINGS-V1`)
   in the settled observation's `extensions`, and `orc report` renders them
   — no new extension schema, this card is the first real producer of an
   already-registered one (per the milestone doc).

Config shape sketch (illustrative, mirroring the acp adapter's
config/session-target wiring pattern rather than the scripted-adapter
`attempts`-only schema in `docs/playbooks/cli-usage.md`):

```json
{
  "assurance": {
    "adapter": "no-mistakes",
    "...": "adapter-specific config, decided at implementation time"
  }
}
```

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
