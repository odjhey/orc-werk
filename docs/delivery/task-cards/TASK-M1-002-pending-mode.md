---
id: TASK-M1-002
type: task-card
status: current
authority: normative
description: Implement pending/incremental mode as the default M1a dispatch behavior, per SCN-007.
implements:
  - STATE-DELIVERY
verifies:
  - SCN-007
---

# TASK-M1-002 — Pending/incremental dispatch implementation

## Outcome

Implement pending/incremental dispatch semantics in the application layer and CLI so SCN-007 passes end to end. Pending mode is the **default**: a config with no recorded outcome for the next attempt leaves the Work at `EXECUTING`, dispatch exits cleanly with the distinct in-progress exit code, and no fact is fabricated for the missing settlement. Re-running `orc dispatch` after the operator appends the real outcome resumes via ordinary idempotent replay (`INV-020`) — no new "resume" command. Fully scripted attempts (M0's existing config shape) continue to work unchanged as the opt-in simulation/testing mode.

## Depends on

`TASK-M1-001`.

## Must not change

`STATE-DELIVERY`'s dispatch-gate-failure normalization rule (mechanical fact sequencing item 6): capability/provider-unavailable gate failures continue to normalize to a failed execution attempt (synthetic `FACT-EXEC-STARTED` + `FACT-EXEC-SETTLED(failed)`), never to pending.

## Acceptance

- SCN-007 passes end-to-end through the application/CLI surface;
- `SCN-001` through `SCN-006` continue to pass unmodified;
- the distinct in-progress exit code is documented in `docs/playbooks/cli-usage.md`'s exit-code contract;
- crash/restart between dispatches (process exit while a Work is pending) does not fabricate or lose a settlement on replay.
