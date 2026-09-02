---
id: SCN-017
type: scenario
status: current
authority: normative
description: Blocking wait mode — dispatch --wait returns when the run's resting point moves, with nothing journaled by the waiting itself (issue #210).
---

# SCN-017 — Blocking wait for the next resting point

## Purpose

`SCN-007`'s exit-`3` poll model is sound but gives an automated caller no
wake: the only route to "the resting point moved" is re-invoking dispatch on
a timer, and a caller that forgets to poll is never told anything (issue
#210 — five finished lanes sat unnoticed in a consuming repo). This scenario
specifies a blocking wait mode that internalizes that re-dispatch loop so a
caller can be woken by process exit — `cmd &` plus the shell's
job-completion notification is the intended composition.

The wait mode adds **no kernel semantics**. No new Fact, Decision, Effect,
transition-table row, or `STATE-DELIVERY` clause exists for waiting; the
sole normative definition is CLI-level. The governing equivalence:

> A dispatch invocation carrying `--wait` is observably equivalent — journal,
> stdout/stderr content, and final exit disposition — to the operator
> re-running the identical non-`--wait` dispatch command at
> implementation-chosen intervals until the run's resting point moves, a
> deadline passes, or the run ends. Each internal pass is a full ordinary
> dispatch pass, including config re-read and idempotent journal replay
> (`INV-020`).

Because each pass re-reads the backing config, an outcome or verdict
recorded while a wait is in flight (`orc record`, or a merge-only hand edit
per `PLAYBOOK-AGENT-CLI`) is picked up on the next pass: operator recording
is a wake source, not a conflict.

**Resting point** is made precise as the run's *pending fingerprint*: the
set of `(work_id, attempt_number, awaiting)` tuples across all non-terminal
works, where `awaiting` is `execution-outcome` or `assurance-verdict` as
already surfaced by `dispatch`/`status` output. The wait returns when the
current fingerprint differs from the baseline fingerprint, or when the run
is terminal. The baseline is computed by replaying the existing journal
*before* the first pass of this invocation — so if news already arrived
(e.g. a settlement observable since before the wait began), the first pass
journals it, the fingerprint moves, and the wait returns immediately. A
caller looping on `dispatch --wait` therefore gets an at-least-once wake per
resting-point change and can never sleep through one.

The surface is a flag on `dispatch`, not a separate `wait` verb, because
observation is a write: settlement is observed only by a dispatch pass that
journals the resulting Facts (`SCN-007` step 4's observation path). A
"read-shaped" waiter that never writes would watch a journal that never
changes. Making the waiter the dispatching party keeps the existing
one-dispatching-party-per-run rule intact with no new coordination surface.

## Given

- Work A is pending exactly as at the end of `SCN-007` invocation 1: resting
  at `EXECUTING`, `FACT-EXEC-STARTED` journaled for attempt 1, no settlement
  recorded, exit `3` territory, awaiting `execution-outcome`.
- The execution provider will eventually settle observably (e.g. the `acp`
  adapter's `inspect()` path), but nothing about this scenario is
  adapter-specific — see step 12 for the operator-recorded-only case.
- `max_attempts = 3`.

## When

1. Caller runs the identical dispatch command with `--wait --timeout <T>`
   appended, with `T` generously larger than the execution's remaining
   duration.
2. The execution settles (`completed`, Candidate C1) while the wait is in
   flight.

## Then

### While nothing has settled

1. The process emits nothing on stdout/stderr and journals nothing: an
   internal pass whose observation sweep finds no settlement is
   record-for-record invisible, exactly as an ordinary re-dispatch of a
   still-pending run is today (`SCN-007` steps 1–3 applied per pass).
   Waiting fabricates no settlement and consumes no retry-budget attempt
   (`INV-018`).
2. The poll interval between passes is an implementation detail. It never
   appears in canonical data: no Fact, idempotency key, or journal field
   derives from wall-clock waiting (determinism hard bar,
   `DELIVERY-STANCE`).

### When the resting point moves

3. The pass that observes the settlement journals `FACT-EXEC-SETTLED(completed)`
   and `FACT-CANDIDATE-OBSERVED` for C1 through the normal observation path
   — the same Facts, in the same shape, that `SCN-007` invocation 2 would
   journal. Nothing about the wait is visible in the journal.
4. Work A now rests awaiting `assurance-verdict`: the pending fingerprint
   differs from the baseline, so the wait returns. It prints the ordinary
   dispatch report for the new resting state (naming the work, the new
   `awaiting`, and the `next:` block) and exits `3` — the existing pending
   exit code, because the run is still non-terminal and exit `3` already
   means "resting, safe to re-check." The caller distinguishes "woken by
   movement" (exit `3`) from "gave up" (the timeout code, step 8) without
   parsing prose.
5. The wait does **not** run through the new resting point toward terminal:
   returning at the first movement is what lets a caller interpose — e.g. a
   watchtower dispatching an independent verify seat for C1
   (`PLAYBOOK-AGENT-CLI` seat discipline). A caller that only cares about
   terminal states simply loops on `dispatch --wait`.
6. If instead the run reaches a terminal state during the wait (every work
   `ACCEPTED`, or any work `BLOCKED`/non-accepted terminal), the wait
   returns with exit `0`/`1` and output identical to a non-`--wait` dispatch
   observing the same journal.
7. A fingerprint change caused by automatic progress *through* a boundary is
   still a wake: e.g. a recorded `rejected` verdict consumed mid-wait
   triggers `DEC-RETRY`, a new `FACT-EXEC-STARTED`, and a rest at attempt 2
   awaiting `execution-outcome` — a different tuple, so the wait returns
   (exit `3`) rather than silently absorbing the retry boundary.

### Timeout, interruption, and refusal

8. If `--timeout <T>` elapses with the fingerprint unchanged, the wait stops
   cleanly with a **distinct wait-timeout exit code** — colliding with none
   of `0`/`1`/`2`/`3` — and journals nothing beyond what its ordinary passes
   journaled. Re-invoking (with or without `--wait`) is always safe; the run
   is exactly as pending as before. The exact code value is fixed by the
   implementation task and added to the exit-code tables in
   `PLAYBOOK-CLI-USAGE` and `CLI-REFERENCE`, the same division `SCN-007`
   step 6 used for exit `3`.
9. `--timeout` without `--wait` is `ERR-VALIDATION` (exit `2`). `--wait`
   without `--timeout` waits indefinitely — automated callers should pass a
   timeout; interactive operators have their shell.
10. Killing the waiting process (SIGINT or otherwise) at any point loses
    nothing: every journaled Fact was journaled by a completed ordinary
    pass, so interruption lands on an `SCN-007` step 14 invocation boundary
    by construction. No special interrupt handling is required beyond not
    corrupting the journal mid-append, which `PORT-JOURNAL`'s durability
    responsibilities already own.

### Concurrency and scope

11. The waiting process is the run's dispatching party for the entire wait.
    The existing rule that one party re-dispatches a run at a time
    (`PLAYBOOK-AGENT-CLI`) extends over the whole wait window; recording
    into the run's backing config remains legal throughout and is the
    expected wake mechanism for operator-recorded inputs.
12. The wait is adapter-agnostic by construction: against a config whose
    awaited input only an operator will ever record (scripted/incremental
    with no self-settling adapter), `--wait` is legal and simply watches for
    that recording, bounded by `--timeout`. No capability gate distinguishes
    "self-settling" from "operator-recorded" providers, because the
    equivalence in Purpose holds identically for both.
13. The full journal produced by one `--wait` invocation spanning N internal
    passes is record-for-record identical — facts, decisions, effects, `seq`
    order, idempotency/effect keys — to N manual re-dispatches, and
    therefore, by `SCN-007` step 11, to a single fully-scripted invocation
    carrying the same eventual outcomes. Waiting is invisible to the
    journal's shape.

## Must not be confused with a supervisor

Nothing here makes orc a scheduler, daemon, or notifier (issue #210's
explicit non-ask). The wait holds no state outside the process, owns no
lifecycle beyond its own, and its death is indistinguishable from an
operator who stopped re-running dispatch. `SCN-016`'s corroborated
worker-disappearance rules are unchanged: a wait pass observes
unobservability conclusions exactly as an ordinary dispatch pass would.

## Verifies

- `INV-018` — retry budget is cumulative; an arbitrary number of empty wait
  passes consumes no retry-budget attempt (step 1).
- `INV-020` — effects are idempotency-addressable; N internal passes journal
  no duplicated effects or facts and produce a journal identical to N
  manual re-dispatches (steps 3, 13).
- `SCN-007` — pending semantics are inherited per pass, not restated: steps
  1, 4, 8, and 10 are each an application of `SCN-007`'s clauses across an
  internalized invocation boundary.
