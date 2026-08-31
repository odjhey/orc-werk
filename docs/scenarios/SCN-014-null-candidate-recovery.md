---
id: SCN-014
type: scenario
status: current
authority: normative
description: A null candidate identification is non-binding and recoverable by re-identification or legal attempt abandonment.
---

# SCN-014 — Null candidate recovery

## Purpose

Prove that PORT-CAND-001's legitimate no-subject result cannot permanently wedge a settled completed Execution at `EXECUTING`: re-dispatch heals by re-identifying the external subject, while `DEC-ABANDON-ATTEMPT` remains a legal operator escape hatch (`CONF-CAND-004`, issue #191).

## Given

- A scripted Execution settles `completed` on attempt 1.
- Candidate identity remains adapter-derived; no operator input or configuration supplies a candidate observation.
- Every identification call for attempt 1 is the same logical `FX-IDENTIFY-CANDIDATE` effect and uses the stable INV-020 key `(delivery_run_id, work_id, 1, FX-IDENTIFY-CANDIDATE)`.

## Then

### Null-then-present leg

1. On the first dispatch, identification returns no subject. No `FACT-CANDIDATE-OBSERVED` is journaled and the Work rests non-terminal at `EXECUTING`, legibly awaiting candidate identification.
2. A subsequent dispatch re-attempts identification for the same settled Execution with the same idempotency key; it neither starts another Execution nor consumes retry budget.
3. When the adapter now returns C1, `FACT-CANDIDATE-OBSERVED` binds C1 and the Work proceeds to `ASSURING` and onward exactly as for successful first-time identification.

### Null-persists leg

1. Re-dispatch may continue to observe no subject without binding a candidate or changing the attempt number.
2. `DEC-ABANDON-ATTEMPT` and `FACT-ATTEMPT-ABANDONED` are legal from this settled-execution/no-bound-candidate shape, citing `FACT-EXEC-SETTLED` as basis.
3. Folding the abandon reaches the ordinary post-abandon resting state (`READY` when budget remains, otherwise `BLOCKED`). It stops there and never auto-starts the next attempt.

### Regression leg

When first-time identification returns C1, the existing path is unchanged: exactly one candidate observation binds, assurance runs, and its verdict resolves normally.

## Replay determinism

Replaying the journal after any null observation reconstructs the same settled `EXECUTING` projection with no bound candidate. Replaying after a later binding or abandon reconstructs the same resulting `ASSURING`/terminal or post-abandon projection. Re-dispatch derives the same attempt-scoped identification idempotency key from durable state.

## Mutation check

Treating null as a binding Fact, suppressing re-identification because an earlier effect record exists, changing the key between dispatches, starting a new Execution, rejecting abandon from the null resting shape, auto-starting after abandon, or accepting a hand-authored candidate makes this scenario fail.

## Executable coverage

`tests/scenarios/test_scn_014_*.py` exercises all three legs and replay determinism with scripted/in-memory adapters.

Verifies: `CONF-CAND-004`, `STATE-DELIVERY` item 9, `PORT-CAND-001`, `INV-020`, `FX-IDENTIFY-CANDIDATE`, `FACT-CANDIDATE-OBSERVED`, `DEC-ABANDON-ATTEMPT`, `FACT-ATTEMPT-ABANDONED`.
