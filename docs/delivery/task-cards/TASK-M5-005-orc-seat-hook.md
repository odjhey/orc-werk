---
id: TASK-M5-005
type: task-card
status: current
authority: normative
description: Author .omp/extensions/orc-seat.ts — tool_call guards enforcing record-before-yield, no-self-merge, verify push/commit/comment denial, and the ship worktree fence — with a red-then-green test proving each guard fires.
implements:
  - ADR-0007
verifies: []
---

# TASK-M5-005 — `.omp/extensions/orc-seat.ts` hook guards

Design source: `ADR-0007`; `M5-OMP-FIRST-DELIVERY` Phase 2. Depends on
`TASK-M5-004` (the agent role names and worktree convention the hook
guards) and `TASK-M5-001` (confirms `tool_call` blocking and, if
answered, role-identity are both real OMP capabilities before any guard
is trusted).

## The gap

`ADR-0007`'s current→target mapping moves four rules from prose
enforcement to a blocking mechanism: record-before-yield, no subagent
runs `gh pr merge`, the verify role cannot push/commit/comment, and the
ship role's edits stay inside `.worktrees/<branch>`. Today nothing rejects
a session that violates any of these; an agent must simply choose to
comply. Per `V2` (a check that has never been seen red proves nothing),
none of these guards may be trusted until each is observed firing.

## Outcome

One extension file, `.omp/extensions/orc-seat.ts` (~100 lines), registers
`tool_call` hooks that:

1. Block `yield` until a bash call invoking `orc record` with exit code
   `0` or `3` was observed earlier in the same session.
2. Block `gh pr merge` from any subagent, regardless of role.
3. Deny `git push`, `git commit` to a shared branch, `gh pr comment`, and
   `gh pr review` when the calling agent's role is `verify` (or, per
   `TASK-M5-001`'s role-identity fallback if role is not learnable, applies
   this denial to every non-ship subagent).
4. Fence `edit`/`write` tool calls to paths outside `.worktrees/<branch>`
   when the calling agent's role is `ship`.

A colocated test script (`.omp/extensions/orc-seat.test.ts` or
equivalent) proves each guard: it first demonstrates the violating call
succeeding with the guard disabled/absent (red), then demonstrates the
guard firing and blocking it (green) — the `V2` anti-hollow proof, not
merely "the code exists."

## In scope

`.omp/extensions/orc-seat.ts` and its colocated test. Wiring the
extension into `.omp/config.yml` if OMP requires an explicit
registration entry (confirmed against `TASK-M5-001`'s findings).

## Out of scope

Any change to the orc kernel or `.orc/` journal (the hook never writes to
it, per `ADR-0007`'s `T3`/`ADR-0005` ruling — it only blocks `tool_call`s).
The agent definitions themselves (`TASK-M5-004`, a dependency, not
modified here except to reference the hook if its body needs to).

## Acceptance

- `.omp/extensions/orc-seat.ts` exists and is registered with OMP (per
  whatever registration `TASK-M5-001` found necessary).
- The colocated test demonstrates, for each of the four guards, a red run
  (violation succeeds without the guard) followed by a green run
  (violation blocked with the guard active) — four distinct
  red-then-green pairs, not one aggregate pass.
- The hook never issues an `orc record` call, an `.orc` file write, or any
  other ledger mutation itself — grep/inspection of the file confirms no
  such call exists.
- A `yield` attempted before any `orc record` bash call in the session is
  blocked by the hook in the test.
- `gh pr merge` is blocked from every subagent role in the test,
  regardless of which role invokes it.
