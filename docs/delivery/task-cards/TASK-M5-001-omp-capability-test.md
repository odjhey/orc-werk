---
id: TASK-M5-001
type: task-card
status: current
authority: normative
description: Run nother-guide's five-point harness capability test against the installed OMP version and record the results — the gate every later M5 card depends on.
implements: []
verifies: []
---

# TASK-M5-001 — OMP capability test report

Design source: `M5-OMP-FIRST-DELIVERY` Phase 0; `ADR-0007`; `nother-guide`'s
`harness-capabilities.md` (pinned reference, commit `aa1fc24`).

## The gap

`ADR-0007` proposes replacing prose-enforced seat discipline with OMP
mechanisms (schema rejection, blocking hooks, native subagent isolation).
Every one of those mechanisms is an assumption about the installed OMP
version's actual behavior until it is run and observed — an untested
capability is a gap, not a pass. Nothing today records whether OMP 18.1.11
actually denies a blocked tool call, actually rejects a malformed result,
or actually stops a task's descendants on timeout.

## Outcome

A dated report at `docs/reports/2026-09-xx-omp-capability-test.md`
recording, for each of the five capability-test points: the OMP version,
models/backends used, the exact permission/tool configuration, the exact
command run, the observed result (pass/fail, quoted output or transcript
path), and whether a fallback (per-role rules moved into agent `tools` +
system prompt instead of a hook) was required. The report also answers the
open probe: can a hook/extension learn the running agent's role (name) to
apply per-role deny rules, with the fallback stated explicitly if not.

## In scope

- Point 1: spawn verify on a non-Anthropic model family with a tool
  restriction denying `git push`; confirm denial against a disposable
  local remote.
- Point 2: a task item with no `cwd`; confirm the ship agent creates its
  own worktree and a hook fences writes outside it, with the guard
  observed firing red before being trusted (`V2`).
- Point 3: `outputSchema` + `schemaMode: strict`; confirm a result missing
  `verdict` (or any required field) is rejected.
- Point 4: `task.maxRuntimeMs` stops a task; confirm descendants stop and
  `history://` is retained afterward.
- Point 5: read a transcript from `~/.omp/agent/sessions/...jsonl` after a
  new session and after a reboot.
- The role-identity probe and its recorded fallback.

## Out of scope

Writing the agent definitions or hook themselves (`TASK-M5-004`,
`TASK-M5-005`) — this card only produces the evidence those cards build on.
Re-running the test on every future OMP upgrade (a maintenance task, not
this card).

## Acceptance

- The report exists at `docs/reports/2026-09-xx-omp-capability-test.md`
  with all five points recorded pass/fail against the real installed OMP
  version, each with the exact command and observed output or transcript
  path cited.
- Any failing point names the fallback (glue kept, or per-role rules moved
  into agent `tools`/system prompt) rather than being silently assumed
  away.
- The role-identity open probe has a recorded answer (yes with the
  mechanism, or no with the stated fallback).
- `TASK-M5-004` and `TASK-M5-005` cite this report's results for the
  capabilities their agent definitions and hook depend on.
