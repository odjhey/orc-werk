---
id: TASK-M5-005
type: task-card
status: current
authority: normative
description: Author .omp/extensions/orc-seat.ts — as of Amendments 4-7, a single advisory tripwire (not an enforcement mechanism) fencing the ship seat's write/edit calls to its own .worktrees/<branch>, failing closed on any target with zero derivable local paths (issue #297); record-before-yield, no-self-merge, and verify push/commit/comment/review denial are policy honored by the seat definitions and audited after the fact, not hook-enforced. Red-then-green tests prove the tripwire fires.
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
   `0` or `3` was observed earlier in the same session — a genuine
   invocation, tokenized at the invocation position, never merely a
   command that mentions `orc record` as text (attempt 2's own
   `echo fake-orc-record --command "orc record ..."` bypass, closed by
   attempt 3; see the dated amendment below).
2. Block `gh pr merge` from any subagent, regardless of role.
3. Deny `git push`, `git commit`, `gh pr comment`, and `gh pr review`
   unconditionally when the calling agent's role is `verify` (or, per
   `TASK-M5-001`'s role-identity fallback if role is not learnable, applies
   this denial to every non-ship subagent).
4. Fence `edit`/`write` tool calls to outside the calling ship seat's own
   `.worktrees/<branch>` — its own worktree specifically, derived from its
   own `cwd`, never merely "some `.worktrees` directory" (attempt 2's own
   sibling-worktree defect, closed by attempt 3; see the dated amendment
   below) — when the calling agent's role is `ship`.
5. Block any subagent, in any role, from pushing (or force-pushing) to
   `master`/`main`. Role-independent by design, restoring a protection
   attempt 1 had by accident and attempt 2 dropped when guard 3 became a
   literal per-role rule (see the dated amendment below).

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
- The colocated test demonstrates, for each of the five guards, a red run
  (violation succeeds without the guard) followed by a green run
  (violation blocked with the guard active) — five distinct
  red-then-green pairs, not one aggregate pass.
- The hook never issues an `orc record` call, an `.orc` file write, or any
  other ledger mutation itself — grep/inspection of the file confirms no
  such call exists.
- A `yield` attempted before any `orc record` bash call in the session is
  blocked by the hook in the test.
- `gh pr merge` is blocked from every subagent role in the test,
  regardless of which role invokes it.
- `git push` (or a force-push) to `master`/`main` is blocked from every
  subagent role in the test, regardless of which role invokes it, while a
  root/watchtower session's own push to `master`/`main` is unaffected
  (guard 5; named in the dated amendment below as a disclosed scope
  addition beyond this card's original four, closing attempt 2's finding
  11 regression).

## Amendment — role-identity finding (recorded post-implementation, corrected)

This card's own first step, per its dispatch brief, was to answer empirically
whether a `tool_call` hook running under a real `.omp/agents/*.md` seat can
learn *which named role* (ship/verify/scout) is running, before designing
guard 3/4 as literal per-role rules. **Yes, it can** — role identity is
observable. This corrects an earlier version of this amendment (and the PR
it shipped in, #284) that concluded the opposite.

The earlier "no" answer was reached by walking only the enumerable/
prototype-chain *property names* of `ctx` and `ctx.sessionManager` (35 and 99
keys respectively) looking for something literally named `role`/`agentName`/
`agentId`/`agentType` — a method this card shared with `TASK-M5-001`'s
original probe (§6-7). Neither probe ever called
`ctx.sessionManager.getEntries()` to read the actual session *transcript
content*. An independent verify seat auditing PR #284 made exactly that call
and found the answer sitting in plain sight: every subagent session's own
transcript carries a `session_init` entry whose `agent` field is the literal
role name it was spawned with. Re-confirmed by this card, live, from
*inside* a real `tool_call` hook handling a subagent's own `bash` call (not a
post-hoc file read): spawning `agent: "verify"` via the `task` tool and
reading `ctx.sessionManager.getEntries().find(e => e.type ===
"session_init").agent` from the hook itself yielded `"verify"` on the
subagent's first tool call. A root/top-level session carries no
`session_init` entry at all, so the same lookup reliably returns `undefined`
there. See `.omp/extensions/orc-seat.ts`'s own header comment, and this PR's
body, for the exact commands and captured output.

`ctx.sessionManager.getSessionFile()`'s shape difference between a root
session and any `task`-spawned subagent's session (established in the
original probe and unaffected by this correction) remains the signal guards
1 and 2 use for "is this a subagent at all" — both are role-independent by
design (ADR-0007 asks for "any subagent" on both), so neither needed the
`agent` field.

Consequence for the four guards:

- **Guard 1** (record-before-yield) and **guard 2** (no subagent runs
  `gh pr merge`) needed no change — both were role-independent by
  construction (guard 1 keys off the yield payload's own shape; guard 2 is
  already "any subagent, regardless of role").
- **Guard 3** ("verify cannot push/commit/comment/review") is now a literal
  per-role rule: `agent === "verify"` denies `git push`/`git commit`/
  `gh pr comment`/`gh pr review` unconditionally, regardless of target
  branch — `verify.md`'s own protocol never legitimately does any of these,
  so no branch resolution is needed (an earlier, role-blind version of this
  guard had to approximate the rule with a "shared branch" heuristic; that
  heuristic and its residual gap are gone, not merely relabeled).
- **Guard 4** (ship's edits stay inside `.worktrees/<branch>`) is now scoped
  to `agent === "ship"` specifically, not "any subagent with write/edit
  tools". Today only `ship` declares those tools, so the observable behavior
  is identical to the earlier version's blanket rule, but the guard is now
  correct by construction rather than correct by coincidence of today's tool
  assignments.

There is no remaining degraded guard in this file. The acceptance criteria
above are met as originally written: all four guards exist, are registered
via OMP's native `.omp/extensions` auto-discovery (`TASK-M5-001`'s finding
was that a hook can also be loaded via `--hook`/`--extension`; this card
additionally confirms cwd-based native auto-discovery needs no explicit
registration entry at all), and each guard's red-then-green pair is
demonstrated both live (real `omp -p` processes against a disposable repo,
cited in this PR's body) and in the colocated `orc-seat.test.ts`.

## Amendment 2 — 2026-09-07, attempt 3, five findings closed (dated, with provenance)

Run `task-m5-005`, work `hook`, PR #284. Attempt 1 (candidate
`cfc5f669aa158337a26f42ac51a19d7b73584f93`) was rejected at journal seq 16;
attempt 2 (candidate `4f910eaf3988525e056b71c8f87dbcd16f532bb1`) was rejected
at journal seq 26. Both rejections came from an adversarial verify seat
auditing this same PR under a live hook, not a factory unit probe alone.
Attempt 2's rejection carried five blocking findings and one non-blocking
regression (finding 11); this amendment records how attempt 3 closed all
six, each demonstrated against a fresh `omp -p` process with the hook
active (exact commands and captured output are in this PR's body).

1. **Guard 1 substring bypass (finding 1).** The verifier's own probe —
   `echo fake-orc-record --command "orc record run-x --work w --verdict
   accepted"` — satisfied the old `/\borc\s+record\b/` substring match and
   let a fabricated `yield` through. `commandRecordsOutcome` now tokenizes
   the command and requires `orc record` (bare, `uv run [--project <path>]
   orc record`, or an absolute/relative path ending `/orc record`) to be the
   first word of an actual top-level simple command, with an
   `--outcome`/`--verdict` flag in that same invocation. Live-verified twice:
   the verbatim bypass command now yields a hook rejection and the subagent
   aborts after two denied yield attempts; a real `orc record ... --outcome
   completed` invocation (through a stub `orc` binary, confirmed invoked by
   its own log) allows the identical yield shape through.
2. **Hollow RED tests (finding 2).** The four RED tests were byte-identical
   across attempts 1 and 2, each asserting only that `new Map()` starts
   empty — no violating call was ever invoked. `orc-seat.test.ts` now gives
   every guard (five, after this amendment) a `sink`-based red/green pair:
   RED runs the violating call with no guard installed and asserts its
   side effect actually lands in `sink`; GREEN runs the identical call with
   the real `orcSeat` factory installed and asserts `sink` stays empty and
   the block carries the guard's own reason.
3. **Guard 4's loose worktree fence (finding 3).** The old fence accepted
   any path containing a `.worktrees` segment, not the seat's own — a ship
   at `/repo/.worktrees/task-x` could write into
   `/repo/.worktrees/sibling/file.ts`. `ownWorktreeRoot` now derives the
   seat's own `.worktrees/<branch>` root from its own `cwd` and fences to
   that specific directory. Live-verified: a ship subagent spawned with
   `cwd` inside its own worktree wrote successfully inside that directory,
   while an identical write into a sibling worktree and into the primary
   checkout were both denied with a reason naming the seat's own worktree.
4. **Amendment provenance (finding 4).** This amendment is dated and cites
   the run, PR, and both rejection journal entries above, superseding the
   undated "recorded post-implementation, corrected" heading attempt 2
   shipped.
5. **`verify.md` self-contradiction (finding 5).** The frontmatter said
   "Cannot push, commit, comment, or merge" (unconditional) while the body
   said "never push, commit ... to a shared branch" (implying a non-shared
   commit might be permitted) — inconsistent with the hook, which denies
   every `git commit`/`git push` from the verify seat unconditionally.
   `.omp/agents/verify.md`'s body now states the unconditional form,
   while still explicitly preserving the verify seat's own scratch
   worktree add/remove (not a commit, and not fenced by any guard).
6. **Safety regression, disclosed as a fifth guard (finding 11).** Attempt 1
   blocked any subagent's push to a shared branch by accident, via a
   role-blind heuristic. Attempt 2 made guard 3 a literal `agent ===
   "verify"` rule, which dropped that protection: `ship git push origin
   master` became `ALLOW`, contradicting `ship.md`'s own boundary. Guard 5,
   named explicitly in this card's "Outcome" and "Acceptance" sections
   above, restores it as its own role-independent rule — "no subagent, in
   any role, lands directly on `master`/`main`" — using only the
   `isSubagentSession` signal, parallel to guard 2. Live-verified: a ship
   subagent's `git push origin master` is denied citing the shared branch,
   while a root/watchtower session's own `git push origin master` remains
   unaffected, and ship's own-branch push, force-with-lease push, and
   `git fetch && git rebase origin/master` all remain real, allowed
   operations.

Guard 1 and guard 2 needed no further change beyond finding 1's tokenizer
fix — both were already role-independent by construction, per the first
amendment above. There is no remaining degraded or undisclosed guard in
this file after this amendment.

## Amendment 3 — 2026-09-07, run `task-m5-005-guards`, issue #290, mechanism correction (dated, with provenance)

Run `task-m5-005` (work `hook`, PR #284, attempt 3's own delivery above) was
rejected a third time at journal seq 36 and reached `BLOCKED` at
`retry-budget-exhausted`. `issue #290` recorded the shared root cause across
all three rejections (seq 16, 26, 36): guards 1, 2, and 5 each asked "does
this command's TEXT look like X?" — a question that is undecidable from text
alone once the shell's own escape hatches (`&&`/`||`/`;`, quoting, `uv run`
wrapping, control operators) are in scope. Every attempt's patch to one
bypass re-armed either the opposite failure mode (guard 2 false-denying
`gh pr create --body "...gh pr merge..."`) or a sibling bypass (guard 1
defeated in turn by `echo fake-orc-record ...`, then `true || orc record
...`, then `uv run echo orc record ...`). This run, `task-m5-005-guards`,
re-delivers the same four files with guards 1, 2, and 5 rewritten to decide
on structure or an observed session effect instead — guards 3 and 4 are
unchanged, per issue #290's own audit table ("passed all three attempts").

1. **Guard 1 (record-before-yield): blacklist → whitelist, still
   session-observation, deliberately not a ledger read.** The issue's own
   draft brief suggested "consult the ledger, not the command" — checking
   `.orc/<run_id>/journal.jsonl` for a recorded outcome instead of watching
   bash calls. That was tried and explicitly rejected during this run: the
   ledger can only answer "does *some* recorded outcome exist for this
   run/work", never "did *this attempt*, in *this session*, just record
   one" — a prior attempt's own successful `orc record` (or a sibling
   seat's) would silently satisfy the gate for a session that never called
   `orc record` at all, and the hook has no reliable, spoof-proof way to
   learn which attempt number it is currently running under (the run/work
   IDs are nameable from the brief and `ORC_JOURNAL_DIR`, but "is this
   specific session's own attempt the one that recorded" is not a ledger
   question). `commandRecordsOutcome` instead moves from a blacklist
   (`/\borc\s+record\b/` as a substring, then a same-shape check for
   evasions as they were found — an unbounded chase) to a whitelist: the
   *entire* observed command must be one clean, bare `orc record`/`uv run
   [--project P] orc record` invocation, with an `--outcome`/`--verdict`
   flag, and zero shell control operators/pipes/redirections/substitution
   anywhere in it. `true || orc record --outcome completed` fails on the
   bare `|` alone; `uv run echo orc record ...` fails because the token
   after `run` is `echo`, not `orc`. Neither needed a named bypass entry.
   Fail-closed on ambiguity was deliberately rejected as this guard's
   default (an unresolvable run/work identity would otherwise halt every
   seat); the guard instead fails closed only on the whitelist test itself,
   never on identity resolution, and stays a pure session observation.
   Live-verified in a fresh `omp -p` process: `true || orc record ...`,
   `uv run echo orc record ...`, and the original `echo fake-orc-record
   --command "orc record ..."` are all denied at the yield; a real `orc
   record ... --outcome completed` invocation (through a stub `orc` binary,
   confirmed invoked by its own log) permits the identical yield shape
   through, for both a role-independent subagent and a real `ship` seat.
2. **Guard 2 (no subagent `gh pr merge`): whole-string regex → argv-
   positional.** `/\bgh\s+pr\s+merge\b/` matched inside a quoted argument,
   so a legitimate `gh pr create --body "...gh pr merge..."` was falsely
   denied — the catastrophic failure class named in this issue, because it
   blocks a real landing operation, not merely a self-merge attempt.
   `commandInvokesGhPrMerge` now requires `gh`, `pr`, `merge` to be the
   (env-assignment-skipped) first three words of an actual top-level simple
   command. Live-verified: `gh pr merge 1 --squash` is still denied from a
   subagent (role-independent, and from a real `ship` seat), while `gh pr
   create --title T --body "See the landing rule: never run gh pr merge
   yourself"` is allowed and reaches the real stubbed `gh` binary.
3. **Guard 5 (no subagent push to `master`/`main`): argument pattern-
   matching → git-resolved ref target.** The previous version missed the
   `+master` force-push refspec form entirely (`git push origin +master`
   advanced a disposable remote's `master`, undetected). `refspecTarget`
   strips force prefixes/flags (`+refspec`, `--force`, `-f`,
   `--force-with-lease[=...]`) before reading the remote-side branch name
   positionally. The two forms not decidable from text alone — a bare `git
   push` (relies on the configured `@{upstream}`) and a remote-only or
   bare-`HEAD` push with no explicit destination (relies on `HEAD`'s own
   branch name) — are now resolved by invoking `git rev-parse
   --symbolic-full-name` in the seat's own `cwd`, closing the gap this
   card's own attempt-3 amendment had disclosed rather than merely
   re-disclosing it; any resolution failure (no upstream configured, `git`
   unavailable) yields no confidently-known target and this guard does not
   block, because an unresolvable bare push has nothing to protect —  `git`
   itself refuses it before any effect lands. Live-verified against a
   disposable three-repo git fixture (bare origin plus two working clones):
   `git push origin +master` is denied (the bare remote's `master` ref is
   confirmed unchanged on disk after the denial); a bare `git push` with an
   upstream tracking `master` is denied identically; `git push origin
   HEAD`/`git push origin` with `HEAD` on a non-shared branch, own-branch
   push, `--force-with-lease` to the seat's own branch, and `git fetch &&
   git rebase origin/master` all remain allowed, from both a
   role-independent subagent and a real `ship` seat.

Guards 3 and 4 are unchanged in this run — issue #290's own audit table
records them passing all three prior live audits, and the card's own
"Guards 1, 2, 5" framing above already scoped this run to the other three.
`.omp/extensions/orc-seat.test.ts` gained a RED/GREEN pair for each of the
three rewritten guards' new mechanism (in addition to the five pairs
attempt 3 already established), including a pair proving a non-invoking
command (`true || orc record ...`) is denied while a real recorded outcome
permits the yield. There is no remaining command-text-matching guard in
this file after this amendment; guards 1, 2, and 5 each decide on argv
structure, a genuine whitelisted invocation, or a git-resolved ref.

## Amendment 4 — 2026-09-07, run `task-m5-005-guards`, operator ruling, descope to the worktree fence only (dated, with provenance)

Four delivery attempts in total have now been rejected on this card's guards
1, 2, 3, and 5: three on run `task-m5-005` (seq 16, 26, 36 —
`retry-budget-exhausted`) and a fourth on run `task-m5-005-guards` (attempt 1,
PR #284 at head `3e576ee51f10b69284491f42d7774da53bc4a474`, rejected at
journal seq 16 — `orc history task-m5-005-guards --limit 0`). Amendment 3
above already re-derived guards 1, 2, and 5 to decide on argv structure, a
session-observed effect, or a git-resolved ref instead of command text, and
that redesign was itself defeated live at the fourth attempt: `g\it push
origin +master` and `g\h pr merge` (backslash-escaped binary names) advanced
disposable bare remotes past guards 2, 3, and 5; `PATH=<probe-bin>:/usr/bin:/bin
orc record run-x --work w --outcome completed` satisfied guard 1's
whitelist while only a logging stub ran, because the hook resolves the
unqualified token `orc` without applying the command's own `PATH`
assignment. The fourth attempt's verify seat also confirmed a live harness
defect: native `omp -p` from the repo root loaded `orc-seat.test.ts` as a
production extension and emitted `Failed to load extension ... Cannot use
describe outside of the test runner` on every startup, because native
auto-discovery scans `.omp/extensions` for direct `*.ts` files with no test
exclusion.

**The operator ruled, 2026-09-07** (recorded on this run): stop iterating on
guards 1, 2, 3, and 5. The shared root cause across all four attempts, filed
as issue #290, is structural and does not have a fixed point within a
`tool_call` hook: `readCommand` gives the hook only `event.input.command` as
a single string — never shell argv, never the resolved executable, never
process identity — so any guard that decides by inspecting that string,
blacklist or whitelist, is answering a question the shell makes undecidable
from the string alone. Guard 4, the cwd-derived ship worktree fence, is the
one guard of the five that decides on structural context (`ctx.cwd`) the
hook genuinely receives, and it passed every audit across all four
attempts, including the fourth's.

**What moves where:**

- Push/merge restriction (guards 2, 3, 5: no subagent `gh pr merge`, verify
  cannot push/commit/comment/review, no subagent pushes to a shared branch)
  moves to server-side GitHub branch protection, applied by the watchtower —
  outside this hook and outside this card's scope.
- Record-before-yield (guard 1) needs no hook: the orc state machine already
  enforces it structurally — a work with no recorded `FACT-EXEC-SETTLED`
  stays non-terminal and the run cannot reach a terminal state, independent
  of anything a session's own tool calls do or don't do.

**Reduced acceptance — supersedes the guard-count language in "Outcome" and
"Acceptance" above; those sections are left as originally written for
provenance, not rewritten:**

- `.omp/extensions/orc-seat.ts` implements exactly one guard: it fences
  `write`/`edit` tool calls to the calling `ship` seat's own
  `.worktrees/<branch>`, derived from `ctx.cwd`, denying both
  sibling-worktree and primary-checkout targets while permitting the seat's
  own. Guards 1, 2, 3, and 5 and the command-text-parsing machinery only
  they needed (the chained-command tokenizer, `hasUncleanShellSyntax`,
  refspec/branch-ref resolution) are deleted from the file outright, not
  disabled, commented out, or feature-flagged.
- The file's own header states plainly what it enforces, that command-text
  interception was attempted and abandoned, why (the hook receives a string,
  never argv, per `readCommand`), and where the other controls now live.
- The colocated test proves the retained fence red-then-green: a red run
  shows a violating write landing with no guard installed; a green run shows
  the identical write blocked once the real factory is installed, and an
  identical write inside the seat's own worktree remains allowed.
- The test is relocated to `.omp/extensions/__tests__/orc-seat.test.ts` (from
  a flat `.omp/extensions/orc-seat.test.ts`) so native `omp` extension
  auto-discovery — which scans `.omp/extensions` for direct `*.ts` files and
  descends only one level into a subdirectory for `index.ts` or
  `package.json` (`omp://extension-loading.md`) — never loads it as a
  production extension. A native `omp -p` from the repo root no longer emits
  the `Cannot use describe outside of the test runner` load failure.
- The hook issues no `orc record` call and no `.orc` write itself, and
  imports no `src/` module.

This amendment does not touch `ADR-0007` or
`docs/reports/2026-09-07-omp-capability-test.md`; the descope ruling and its
fuller rationale are recorded there by a sibling delivery on this same run.

## Amendment 5 — 2026-09-07, run `task-m5-005-guards` attempt 3, issue #296, stale present-tense corrections (dated, with provenance)

Two sections above predate Amendment 4's operator-ruled descope (guards 1,
2, 3, and 5 deleted outright; only guard 4, the worktree fence, remains)
and are now false as written. Per this repo's own convention (Amendment 4,
`:375-377`: supersede in place, leave the original text for provenance,
never silently rewrite history), both are corrected here rather than
edited in place:

- **`:22-28` ("Today nothing rejects a session that violates any of
  these...")** was true when written (before any guard existed) and is
  false now: guard 4 rejects a `ship` seat's `write`/`edit` outside its own
  worktree, and has since attempt 1. It describes the pre-implementation
  gap this card opened against, not the file's current behavior — read it
  as history, not as a live claim.
- **`:138-158`**, part of the "role-identity finding" amendment above
  Amendment 2, claims "Guard 3 is now a literal per-role rule", "there is
  no remaining degraded guard in this file", and "all four guards exist,
  are registered... and each guard's red-then-green pair is demonstrated".
  All four guards did exist at that point in this card's history (between
  the role-identity correction and Amendment 3). They do not now: Amendment
  4 deleted guards 1, 2, 3, and 5 outright, per the operator's descope
  ruling (issue #290) and issue #296's unified root-cause finding. As of
  this run, `.omp/extensions/orc-seat.ts` implements exactly one guard
  (guard 4), stated plainly in the file's own header comment. Amendment
  4's own "Reduced acceptance" note (`:375-377`) superseded the
  guard-count language in "Outcome" and "Acceptance" only; this note
  extends that supersession to `:138-158`, which those two sections did
  not cover.

**Correcting `:404-406`.** That sentence, written as part of Amendment 4,
claims "this amendment does not touch `ADR-0007` or
`docs/reports/2026-09-07-omp-capability-test.md`". It did: the PR #284
candidate this amendment described (attempt 2 of run `task-m5-005-guards`,
rejected at journal seq 26 for, among other findings, exactly this
territory violation) modified both `docs/adapters/omp/capabilities.md` and
`docs/reports/2026-09-07-omp-capability-test.md` — regressing the latter's
"6. Role-identity open probe" section back to its pre-`#286`-correction
text, undoing that correction, inside PR #292's and PR #294's declared
territory. Neither file is in this card's scope. This attempt (3) reverted
both files to their `c7beea5` content (verified byte-identical to
`origin/master` at this attempt's head); the diff this PR now carries
touches neither file. The original sentence described an intent that one
delivered candidate did not honor; this amendment records that miss and
its correction rather than erasing it.

This amendment does not reopen guards 1, 2, 3, or 5, and does not change
`.omp/extensions/orc-seat.ts`'s single-guard scope; it corrects prose only.

## Amendment 6 — 2026-09-07, run `task-m5-005-sensor`, issue #297, reframed as an advisory sensor (dated, with provenance)

Run `task-m5-005-guards` (work `guards`, PR #284 at head `ef093a318ee7b1121b71c77b062a3a0f6a002b20`,
Amendment 4/5's own delivery above) reached `retry-budget-exhausted`. Its final audit
(ledger `task-m5-005-guards` seq 36, filed as issue #297) defeated guard 4 — the sole
surviving guard Amendment 4 (`:359-362`) had described as having "passed every audit
across all four attempts, including the fourth's" — two further structural ways at that
same head: a `write`/`edit` target carrying no local path at all (`ssh://host/<path>`,
reproduced live as `{"result":"ALLOW"}`) fell through the old
"zero-candidates-means-nothing-to-check" default; and a name hardlinked inside the
seat's own worktree shares an inode with a sibling worktree's file while its own
`realpath` stays inside, invisible to the symlink-only resolution `isInsideOwnWorktree`
performs. Taken with the already-established command-channel defeat (issue #290, and
issue #296's unified root-cause finding), the capability question this card's own first
step (the "role-identity finding" amendment above) originally set out to answer is now
settled in full, on both channels a `tool_call` hook can receive input on: **no OMP
`tool_call` hook can soundly enforce a seat rule.**

The operator ruled (recorded on this run): descope to what is actually enforceable.
Guard 4 is KEPT, for its real, demonstrated value — a tripwire that catches naive and
accidental violations, proven red-then-green (21 tests as of this amendment, up from
16) — but every sentence claiming it *enforces*, *guarantees*, *prevents*, or
*restricts* a seat rule is removed from `.omp/extensions/orc-seat.ts` and from this
card. This is a reframing, not a further guard deletion: nothing is cut from the file
that was not already disclosed as unsound.

**What changed in `.omp/extensions/orc-seat.ts` (see that file's own header and inline
comments for the full account; summarized here):**

1. **Fail-closed on unresolvable targets.** A `write`/`edit` target this guard cannot
   resolve to any local path (today: `ssh://`, moved out of the scheme table that also
   holds genuinely-never-touches-disk schemes like `local://`, into its own
   `UNRESOLVABLE_URI_SCHEMES` table) is now DENIED, citing the unresolvable input by
   name, before the guard ever reaches its path comparison. Previously, zero
   candidates meant nothing to check, which meant ALLOW.
2. **Hardlink aliasing: disclosed, not fixed.** The realpath-comparison site
   (`realOf`'s own doc comment) now states plainly that `fs.realpathSync` resolves
   symlinks, never hardlinks, that a hardlinked inside name therefore passes this guard
   while aliasing a sibling worktree's inode, and that sound detection would require an
   unbounded, racy sweep of every file in every sibling worktree — not attempted here,
   per the operator's ruling against that approach.
3. **Every enforcement claim removed.** The file's header, previously titled "What this
   hook enforces", now opens "What this hook does... DETECTS AND BLOCKS THE NAIVE,
   ACCIDENTAL CASE", names issue #297's two defeats explicitly, and states outright:
   "It is a TRIPWIRE, not a control, and no sentence in this file is a
   soundness/enforcement claim." The enumeration command used to find every candidate
   sentence, and its per-line classification, are in this PR's body (not reproduced
   here, since the PR body is the durable record a re-run of that exact command can be
   checked against; this card only records the outcome).

**Superseding `:366-369` only** (Amendment 4's "What moves where" bullet on push/merge
restriction, guards 2/3/5) — the third REJECT on this run's own final audit, verbatim:
that bullet assigns all three guards, as one bundle, to "server-side GitHub branch
protection", present tense, without saying which of the three the rung actually
carries. It does not carry all three. As of a `gh api
repos/odjhey/orc-werk/branches/master/protection --jq '[.restrictions,
.required_pull_request_reviews.required_approving_review_count]'` read-back at
`2026-09-07T08:04:54Z` (`[null, 0]`), per guard:

- **Guard 5** (no subagent, in any role, pushes directly to `master`/`main`): branch
  protection genuinely carries this. It blocks ANY identity — including every
  subagent's shared credential — from an unreviewed direct push to the protected
  branch. This is the one guard of the three `:366-369` correctly assigned.
- **Guard 2** (no subagent runs `gh pr merge`): NOT carried by branch protection today.
  `required_approving_review_count` reads `0` in the same read-back, so GitHub does not
  reject an unreviewed `gh pr merge` call from a subagent's shared credential at merge
  time — nothing server-side stops it. (Raising that count, with only the
  watchtower/operator identity able to approve, would close this specific gap; it is
  not configured as of this amendment, and that is a mutable, re-checkable fact, not a
  standing one — re-run the `gh api` call above before relying on this bullet.) Absent
  that configuration, this rule is policy — stated in `ship.md` — audited after the
  fact via the ledger and PR history, never enforced in the moment.
- **Guard 3** (verify cannot push/commit/comment/review, unconditionally, not merely to
  a shared branch): branch protection carries none of this. `git commit` never reaches
  a remote; `gh pr comment`/`gh pr review` never touch a protected git ref; branch
  protection has no opinion on either. Its "push" component overlaps guard 5's coverage
  only when the push targets the protected branch specifically — a `verify` seat
  pushing to some other, unprotected branch is not stopped by branch protection at all.
  This rule, in full, is policy — stated as an unconditional boundary in
  `.omp/agents/verify.md` — plus after-the-fact ledger/PR-history audit; nothing
  server-side enforces it.

`:366-369`'s original text is left as written above for provenance, per this card's own
established convention (Amendment 4, `:375-377`); read it as the pre-#297,
bundled-not-per-guard version of this rung assignment, not as a live claim.

**Also correcting `:359-362`** ("Guard 4... passed every audit across all four
attempts, including the fourth's"): true when written; incomplete now. A fifth audit
(issue #297, above) defeated guard 4 too. `.omp/extensions/orc-seat.ts`'s own header
states this plainly as of this amendment.

**Also correcting `:387`** ("The file's own header states plainly what it enforces"):
the header no longer uses "enforces" for guard 4 at all, per this amendment's own
change — it states plainly what the guard detects and blocks, and states, in the same
breath, both the fixed (`ssh://`/unresolvable-target fail-closed) and disclosed-but-not-
fixed (hardlink aliasing) defeats issue #297 found.

**Reduced acceptance, this amendment — supersedes none of Amendment 4's "Reduced
acceptance" bullets, adds to them:**

- An unresolvable `write`/`edit` target is denied, citing the input by name, never
  silently allowed.
- The hardlink limitation is disclosed in-source at the realpath comparison site,
  citing issue #297.
- No sentence in `.omp/extensions/orc-seat.ts` or this card claims the retained guard
  enforces, guarantees, prevents, or restricts a seat rule; it is documented,
  in-source and here, as a tripwire against naive and accidental violations.
- Guards 2, 3, and 5's actual enforcing rung (branch protection for guard 5 only;
  policy plus after-the-fact ledger/PR-history audit for guards 2 and 3) is stated per
  guard, not bundled.

This amendment does not reopen guards 1, 2, 3, or 5, and does not change
`.omp/extensions/orc-seat.ts`'s single-retained-guard scope; guard 4 remains the only
guard the file implements, now documented as a tripwire rather than a control.

## Amendment 7 — 2026-09-07, run `task-m5-005-sensor`, attempt 2, issue #297 structural fix plus four accuracy corrections (dated, with provenance)

Run `task-m5-005-sensor` (work `sensor`, PR #284 at head `623f2cfeb82b2ed3b1554626cfad597235cab1e8`,
Amendment 6's own delivery above) was rejected at journal seq 16 with five findings, each reproduced
against real code by an independent verify seat. This amendment records how attempt 2 closed all five.

1. **Structural fail-closed fix (finding 1).** Amendment 6's own fix closed issue #297's
   zero-derivable-path ALLOW for exactly one scheme (`ssh`), via an `UNRESOLVABLE_URI_SCHEMES` table
   holding that one name alongside an `IGNORED_URI_SCHEMES` table of eleven other recognized schemes
   (`local`, `memory`, `artifact`, `history`, `agent`, `rule`, `skill`, `mcp`, `issue`, `pr`, `omp`) that
   still ALLOWed unconditionally -- and any call producing zero raw candidates at all (`write {}`, a
   non-string `path`, `edit` with no hashline header, a blank `path`) fell through the same old default.
   Reproduced live via a real `bun run` fixture probe: all eleven non-`ssh` schemes, plus those four
   malformed shapes, returned ALLOW. `.omp/extensions/orc-seat.ts` now decides by DERIVABILITY, never by
   scheme-name lookup: a `write`/`edit` call is denied whenever it yields zero candidates this guard can
   resolve to a comparable local filesystem path, for any reason -- both scheme tables are deleted
   outright, so a scheme invented tomorrow fails closed automatically. See that file's own header and
   `Guard` section for the mechanism.
2. **Executable red-then-green (finding 2).** Attempt 1's swap target, `git show
   ef093a318ee7b1121b71c77b062a3a0f6a002b20:.omp/extensions/orc-seat.ts`, predates this file's own
   `extractUnresolvableTargets` export and never loaded under the test file that imports it -- a swap
   that proves nothing. The correct "pre-change" baseline for THIS delivery's own fix is this run's own
   attempt 1, head `623f2cf`, which already exports every symbol the test file imports (it always has --
   the test file's imports were never the problem; the swap TARGET was). Swapping it in and running
   `bun test ./.omp/extensions/__tests__/orc-seat.test.ts` now produces a genuine red run (22 pass, 16
   fail -- exactly the sixteen new assertions this attempt added: eleven non-`ssh` schemes plus five
   malformed-argument shapes); restoring this attempt's own source produces a genuine green run (38
   pass, 0 fail). See this PR's body for both raw command outputs.
3. **`verify.md` pair declared in scope (finding 3).** Amendment 6's delivery modified both
   `.omp/agents/verify.md` and `src/orc_werk/omp_scaffold/agents/verify.md` (one line each, kept in
   sync) while its own PR body claimed the pair unchanged -- false, reproduced via `git diff
   --name-status`. The edit itself is correct and is kept: it reframes the verify seat's
   push/commit/comment/review boundary from an ambiguous "to a shared branch" qualifier to its actual
   unconditional scope, and states plainly that this is POLICY, not a hook-enforced mechanism -- a
   direct, necessary consequence of Amendment 4 deleting the hook guard (guard 3) that the old wording's
   framing implied still existed. This amendment records the pair as in-scope, not untouched, and why.
   `PackagedScaffoldDriftTest.test_verify_matches_live_seat_modulo_allowlist` continues to pass
   unmodified with no allowlist change (`git diff --exit-code eea2319..HEAD --
   tests/scenarios/test_cli_onboard.py` is clean).
4. **Enforcement inventory re-derived and misclassification fixed (finding 4).** Re-running this card's
   own `awk` enumeration command against the final diff found different counts than Amendment 6's PR
   body claimed, and that PR body did not publish the full per-line output it asserted -- both corrected
   in this attempt's PR body (the full per-line table, from a fresh run at this attempt's own head, is
   there, not reproduced here per this card's own convention, e.g. Amendment 6's `:502-505` above). Two
   further corrections: this card's own frontmatter `description` (`:6`) said the hook "enforces" four
   rules -- LIVE, undated, normative text, not historical -- corrected above (this amendment) to
   describe the single advisory tripwire Amendments 4-6 actually left; and `.omp/extensions/orc-seat.ts`'s
   `Guard` section (the "ship seat's edits stay inside its own `.worktrees/<branch>`" heading) stated the
   fence rule without repeating the tripwire qualifier at that specific location -- it now does, in the
   same paragraph, citing the file's own header.
5. **Verify seat tool-list claim corrected (finding 5).** Amendment 6's PR body claimed the verify
   seat's tool list "grants no bash/gh write access" -- false: `.omp/agents/verify.md`'s `tools:`
   frontmatter has always granted `bash` (unchanged by this card or this run). The real boundary,
   unaffected by this correction, is policy stated in `verify.md`'s own body plus after-the-fact
   ledger/PR-history audit -- never a withheld tool; this attempt's PR body states that correctly. This
   card's own Guard 2/Guard 5 split (Amendment 6, `:516-528` above) was already correct and needed no
   change; only the prior attempt's PR body had bundled them, corrected there.

This amendment does not reopen guards 1, 2, 3, or 5, and does not change
`.omp/extensions/orc-seat.ts`'s single-retained-guard scope; guard 4 remains the only guard the file
implements, now fixed to fail closed on derivability rather than an enumerated scheme list.
