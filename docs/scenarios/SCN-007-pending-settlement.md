---
id: SCN-007
type: scenario
status: current
authority: normative
description: Pending execution with no recorded settlement stops cleanly; operator-recorded outcome and re-dispatch resume via idempotent replay through to acceptance.
---

# SCN-007 — Pending execution / operator-recorded settlement

## Purpose

Pending/incremental mode is the M1a **default** dispatch mode: a config with no recorded outcome for the next attempt is pending, not an error and not a failure. This scenario is the executable specification for `STATE-DELIVERY`'s no-fabricated-settlement clause and for the CLI's distinct in-progress exit code. Fully scripted attempts (every outcome supplied up front, as exercised by `SCN-001` through `SCN-006`) remain valid as the opt-in simulation/testing mode and are unaffected by this scenario.

## Given

- Work A is ready.
- `max_attempts = 3`.
- The config carries no recorded outcome for Work A's next attempt (attempt 1) — the default, incremental shape, not the fully-scripted shape.

## When

1. Operator runs `orc dispatch` (invocation 1) against the config above.
2. `FACT-EXEC-STARTED` is journaled for attempt 1. No outcome is available yet, so no settlement fact is produced.
3. Dispatch stops cleanly; the process may exit.
4. Operator separately records the real outcome for attempt 1 — execution settlement `completed` and Candidate C1, then (once known) assurance verdict `accepted` — into the provider-backing store the ExecutionPort/AssurancePort read (in M1a, the config/scripted attempt store), NOT as a journal record: the kernel emits `FACT-EXEC-SETTLED` and the subsequent facts itself, via the normal observation path, on the next dispatch — which is what makes the journal-identical assertion in step 11 hold.
5. Operator runs `orc dispatch` again (invocation 2) with the unchanged command against the same run/journal.

## Then

### Invocation 1 — pending stops cleanly, nothing is fabricated

1. Work A remains at `EXECUTING`.
2. `FACT-EXEC-STARTED` for attempt 1 is the last Fact journaled for Work A; no `FACT-EXEC-SETTLED` Fact exists for attempt 1.
3. Absence of a settlement observation is never treated as a failed attempt: no synthetic-ref `FACT-EXEC-SETTLED(failed)` is journaled for waiting, and the retry-budget attempt count is untouched by the wait (`INV-018` — cumulative attempt history is not incremented for a started-but-unobserved execution).
4. `INV-003` (execution settlement is not acceptance) and `INV-004` (retry preserves history) do not apply to this step: there is no settlement for `INV-003` to govern, and no retry has occurred for `INV-004` to protect. Neither invariant is violated by their non-applicability here.
5. Kernel-level, this is the durable resting point: the run is non-terminal (not `ACCEPTED`, not `BLOCKED`) and no fact is fabricated to force it to look otherwise.
6. CLI-level: `orc dispatch` exits with a distinct in-progress exit code — not `0` (all work `ACCEPTED`), not `1` (any work `BLOCKED`/non-accepted terminal), not `2` (usage/config error) — per `docs/playbooks/cli-usage.md`'s exit-code contract, the way `SCN-001` is exercised end-to-end through the CLI surface in its accompanying test. The exact code value is a CLI implementation detail fixed by the implementation task, not by this scenario.
7. Process exit after invocation 1 is survivable: nothing beyond the already-journaled `FACT-EXEC-STARTED` was ever asserted, so there is no in-flight state to lose.

### Invocation 2 — idempotent replay resumes exactly where it stopped

8. Re-dispatch after the operator records the real outcome advances the run from precisely where it stopped: `FACT-EXEC-SETTLED(completed)` for attempt 1, `FACT-CANDIDATE-OBSERVED` for C1, assurance settles `accepted`, `FACT-WORK-COMPLETED`.
9. No duplicate `FACT-EXEC-STARTED` is journaled for attempt 1, and `FX-START-EXECUTION` is not re-dispatched as a new effect: the idempotency key derived from `(delivery_run_id, work_id, attempt_number, effect_id)` (`INV-020`) is identical between invocations, so the already-recorded start is recognized, not repeated. No duplicated effects or facts result from the two-invocation split.
10. Work A completes (`ACCEPTED`) only after assurance acceptance, per `INV-003` — settlement of the execution alone, recorded in invocation 2, does not by itself complete the Work.
11. The full journal produced across invocations 1 and 2 — facts, decisions, effects, `seq` order, and idempotency/effect keys — is identical, record for record, to the journal a single fully-scripted invocation carrying the same eventual outcomes up front would produce. No gaps, no duplicates, no reordering: splitting one logical run across two process invocations is invisible to the journal's shape.

### Repeat through assurance to ACCEPTED

12. The same pattern applies at the next boundary: if the operator records only the execution settlement and candidate (outcome `completed`, Candidate C1) without yet knowing the assurance verdict, re-dispatch stops cleanly at `ASSURING` under the identical rules as invocation 1 above — no `FACT-ASSURE-SETTLED` is fabricated, no retry-budget attempt is consumed for the wait, and the CLI reports the same distinct in-progress exit code.
13. Recording the assurance verdict and re-dispatching again advances the run to whichever terminal `STATE-DELIVERY`'s transition table names for that verdict (`ACCEPTED` for `accepted`; `READY` for `rejected` with budget available, then onward through the same incremental pattern; `BLOCKED` for retry-budget exhaustion; for `inconclusive`, back to `ASSURING` as a re-request of the same candidate while the assurance budget permits, else `BLOCKED` — `SCN-021`, `INV-021`).
14. Every invocation boundary in this chain is independently crash-boring: the process may exit between any two invocations, in any order relative to when the operator records an outcome, without lost or duplicated facts, decisions, or effects.

## Must not be confused with SCN-006

Work A's capability is supported throughout this scenario; nothing here is a dispatch-gate failure. `STATE-DELIVERY` mechanical fact sequencing item 6 (dispatch-gate failure normalizes to a failed execution attempt) is not triggered by a missing outcome observation — only by an unsupported capability or unavailable provider at dispatch time, as in `SCN-006`. Pending applies solely to a started-but-unobserved outcome.

## Verifies

- `INV-003` — execution settlement is not acceptance; completion in this scenario follows only assurance acceptance (step 10).
- `INV-004` — retry preserves history; not applicable while a Work is pending (no retry occurs during a wait), applicable again should a rejected verdict trigger `DEC-RETRY` later in the chain (step 13).
- `INV-018` — retry budget is cumulative; waiting for an unrecorded outcome does not consume a retry-budget attempt (step 3).
- `INV-020` — effects are idempotency-addressable; replay across invocations 1 and 2 produces no duplicated effects or facts and an identical journal to a single scripted run (steps 9, 11).
