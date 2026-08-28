---
id: TASK-M1-001
type: task-card
status: current
authority: normative
description: Author SCN-007 and the STATE-DELIVERY pending-mode clause before implementation.
implements:
  - STATE-DELIVERY
verifies: []
---

# TASK-M1-001 — Pending-mode contract and scenario (docs-first)

## Outcome

Author, before any code changes: a new golden scenario `docs/scenarios/SCN-007-pending-settlement.md` (pending execution / operator-recorded settlement), and a short normative clause in `STATE-DELIVERY`'s "Mechanical fact sequencing" section stating that the absence of a settlement observation is not a settlement.

SCN-007 must specify, as executable-specification prose:

- pending/incremental mode is the **default** M1a dispatch mode: a config with no recorded outcome for the next attempt is pending, not an error and not a failure;
- dispatch stops cleanly with the Work at `EXECUTING` and exits with a distinct in-progress exit code (does not collide with the existing `0`/`1`/`2` contract in `docs/playbooks/cli-usage.md`);
- recording the real outcome and re-running the same `orc dispatch` command advances the run via ordinary idempotent replay (`INV-020`);
- fully scripted attempts (every outcome supplied up front) remain valid as the opt-in simulation/testing mode and are unaffected.

## In scope

- `docs/scenarios/SCN-007-pending-settlement.md`, following `docs/templates/scenario-template.md`;
- the `STATE-DELIVERY` pending-mode clause (new clause, additive to "Mechanical fact sequencing");
- `docs/scenarios/README.md` entry for SCN-007.

## Out of scope

Implementation of pending/incremental dispatch (`TASK-M1-002`); the CLI UX batch (`TASK-M1-003`).

## Must not change

`STATE-DELIVERY`'s existing dispatch-gate-failure normalization rule (mechanical fact sequencing item 6): capability failures still journal as failed execution attempts through the ordinary retry/`DEC-BLOCK` machinery. Pending status applies only to a started-but-unobserved outcome, never to a dispatch-gate failure.

## Acceptance

- SCN-007 exists, is `status: current`, and is referenced from `docs/scenarios/README.md`;
- the `STATE-DELIVERY` clause is additive — it does not alter any existing transition-table row or renumber mechanical fact sequencing item 6;
- `python3 scripts/docs_check.py` passes;
- `TASK-M1-002` cites SCN-007 as its verification target.
