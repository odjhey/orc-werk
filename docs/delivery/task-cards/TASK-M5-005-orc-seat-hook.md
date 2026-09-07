---
id: TASK-M5-005
type: task-card
status: current
authority: normative
description: Capability finding — can an OMP `tool_call` hook enforce a seat rule (record-before-yield, no-self-merge, verify push/commit/comment denial, the ship worktree fence)? Tested to exhaustion across three attempt cycles; answered no, 2026-09-07. The hook is abandoned, not descoped further; seat discipline rests on tool restriction, GitHub branch protection, and after-the-fact ledger audit instead.
implements:
  - ADR-0007
verifies: []
---

# TASK-M5-005 — `.omp/extensions/orc-seat.ts` hook guards (closed 2026-09-07, negative result)

Design source: `ADR-0007`; `M5-OMP-FIRST-DELIVERY` Phase 2. Depended on
`TASK-M5-004` (the agent role names and worktree convention the attempted
hook would have guarded) and `TASK-M5-001` (confirmed `tool_call`
blocking and, if answered, role-identity were both real OMP capabilities
that would have been needed before any guard could be trusted).

> **Closed 2026-09-07 (operator ruling) — negative result.** The design
> below (`## The gap` through `## Acceptance`) is the card's *original*
> scope, kept verbatim as the record of what was asked. It was not
> delivered because it cannot be: a `tool_call` hook receives the
> harness's unresolved arguments, never its post-resolution path, so
> every guard re-implements that resolution and every divergence is a
> fresh escape. Full account, evidence, and the rung reassignment: see
> `## Closure — 2026-09-07 (negative result)` at the end of this card.

## The gap (original design — superseded, see Closure)

`ADR-0007`'s current→target mapping moves four rules from prose
enforcement to a blocking mechanism: record-before-yield, no subagent
runs `gh pr merge`, the verify role cannot push/commit/comment, and the
ship role's edits stay inside `.worktrees/<branch>`. Today nothing rejects
a session that violates any of these; an agent must simply choose to
comply. Per `V2` (a check that has never been seen red proves nothing),
none of these guards may be trusted until each is observed firing.

## Outcome (original design — superseded, see Closure)

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

## In scope (original design — superseded, see Closure)

`.omp/extensions/orc-seat.ts` and its colocated test. Wiring the
extension into `.omp/config.yml` if OMP requires an explicit
registration entry (confirmed against `TASK-M5-001`'s findings).

## Out of scope (original design — superseded, see Closure)

Any change to the orc kernel or `.orc/` journal (the hook never writes to
it, per `ADR-0007`'s `T3`/`ADR-0005` ruling — it only blocks `tool_call`s).
The agent definitions themselves (`TASK-M5-004`, a dependency, not
modified here except to reference the hook if its body needs to).

## Acceptance (original design — superseded, see Closure)

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

## Closure — 2026-09-07 (negative result)

**Outcome: abandoned, not descoped further.** The capability question
this card asked — can an OMP `tool_call` hook enforce a seat rule? — is
answered **no**, by exhaustion, and that negative result is this card's
deliverable, not a failure to hide or a card to quietly drop.

`.omp/extensions/orc-seat.ts` never existed on `master`. It lived only on
branch `task-m5-005-orc-seat-hook`; PR #284 (`fix(m5): descope orc-seat
hook to the worktree fence only`) was **closed unmerged** at head
`69e482988736bb48ed9fb3e3301a8ab694a4cdfd` (branch ref preserved, not
deleted).

**The canonical reason.** A `tool_call` hook receives *unresolved*
arguments — `event.input.command` is a raw shell string,
`event.input.path` an unresolved target — while a sound guard needs the
harness's own *post-resolution* path, which the hook never receives.
Every attempt to close that gap made the hook re-implement the harness's
own resolution semantics, and every divergence became a fresh escape.

**Three escape classes, each found by a different verify seat:**

1. **Command text** (issue #290) — the shell is Turing-complete; no text
   predicate establishes program, argv, or effect. Four of the five
   originally-scoped guards were descoped 2026-09-07 on this finding
   (`M5-OMP-FIRST-DELIVERY`'s Acceptance section carries the dated
   four-guards → one-guard chain).
2. **Path canonicalization** (issues #296, #297) — symlinks,
   colon-splitting, `scheme://` traversal, case-insensitive filesystems,
   `ssh://` with no local path, hardlink inode aliasing invisible to
   `realpath`.
3. **Scheme adjudication** (issue #298), introduced *by the fix for class
   2* — a case-insensitive `local://` match the harness treats
   case-sensitively, and an unscoped `conflict://<id>` allowed without
   inspecting the registered marker's `absolutePath`. Both wrote outside
   the seat worktree under a real `WriteTool.execute`.

**Evidence.** Three independent attempt cycles, one run each:
`.orc/task-m5-005/journal.jsonl`, `.orc/task-m5-005-guards/journal.jsonl`,
and `.orc/task-m5-005-sensor/journal.jsonl` — each ran 3 attempts against
PR #284 and recorded one `FACT-ASSURE-SETTLED` fact with
`verdict: rejected` per attempt (9 rejected verdicts total across the
three journals, cutoff 2026-09-07T10:22:15Z — the last of the three
journals' final rejection). Narrative detail:
`docs/reports/2026-09-07-omp-capability-test.md` and
`docs/decisions/ADR-0007-omp-primary-harness.md`. Issue trail: #290
(command text), #293 (record-before-yield/merge-authority rung gap,
unrelated to the hook itself but adjacent), #296 and #297 (path
canonicalization), #298 (scheme adjudication).

**Where seat discipline rests instead — the three rungs that hold:**

- **Tool restriction** — the `tools:` list in an agent definition;
  `.omp/agents/verify.md:8` grants `read, bash, grep, glob, hub` and no
  `write`/`edit`.
- **GitHub branch protection** on `master` — `enforce_admins=true`,
  required status check `ci-required`.
- **After-the-fact ledger audit** — the orc journal, which is where
  every one of the escapes above was actually caught.

This closure supersedes the frontmatter `description` above and every
acceptance criterion in the (retained, unmodified) `## Acceptance`
section: none of them will be met, and none needs to be — the capability
finding above is the deliverable this card closes with.
