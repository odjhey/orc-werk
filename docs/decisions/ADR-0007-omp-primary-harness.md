---
id: ADR-0007
type: decision
status: current
authority: informative
description: Oh My Pi (OMP) becomes the primary delivery harness for orc-werk's own seats; seat machinery moves from prose playbooks into OMP agent definitions, result schemas, and hooks, with principles adopted from nother-guide by pinned reference.
---

# ADR-0007 — OMP is the primary delivery harness

## Status

Accepted (operator ruling, 2026-09-06).

## Context

Since M1a+, orc-werk's own delivery seats (watchtower, ship, verify) have
been driven by prose: 151 lines of `PLAYBOOK-WATCHTOWER`, 163 lines of
`PLAYBOOK-AGENT-CLI`, and the `orc-ledger` skill, re-taught to every fresh
session by convention. Model tiers, role boundaries, result markers, worktree
discipline, and record-before-yield are all enforced by an agent reading
prose and choosing to comply — nothing rejects a non-conforming session.
orc-werk has almost no glue *code* for this (no `seat.sh`; the only script
is `scripts/watch_pr.py`); the ceremony is entirely instruction text.

The adopted `nother-guide` (pinned reference, commit `aa1fc24`,
`git@github.com:odjhey/nother-guide.git`, local path
`/Users/odz/proj/nother-guide`) already prescribes the move. Its E1
corollary reads "keep policy, delete glue when the harness provides it."
`harness-independence.md` splits its component 5 (seats and dispatch) into
**policy** (seat table, role definitions, result contract, reliability log,
verifier-derives-identity, verify-cannot-push, push-based ledger) and
**glue** (launcher argv adapters, watchdog, permission temp files,
allowlists). `harness-capabilities.md`'s five-point capability test governs
which glue a harness can replace: "if all five pass, use native role
definitions and a result contract."

Oh My Pi (18.1.11) gives orc-werk stronger rungs than prose for exactly the
policy component that split: agent frontmatter (`model`, `tools`, `output`),
`outputSchema` with `schemaMode: strict`, `tool_call` hooks that can block
(not merely advise), `task.maxRuntimeMs`, and durable `history://`
transcripts. Per `I2` (encode lessons in structure, at the strongest rung
available), a rule enforceable at "unrepresentable state" or "a
CI-failing check" is preferred over the same rule sitting only in prose.

**Retirement target: prose becomes structure.** The orc kernel
(`src/orc_werk/*`, the `.orc/` journal, its contracts) is product, not
ceremony, and this decision does not touch it beyond `orc onboard` and one
adapter-documentation addition.

## Options

1. **Keep the status quo.** Seat discipline stays entirely prose
   (`PLAYBOOK-WATCHTOWER`, `PLAYBOOK-AGENT-CLI`, the skill), re-taught to
   every session. Cheapest to leave alone; leaves every rule in this ADR's
   Context at the weakest rung (I2), unenforced by anything but a session's
   willingness to read and comply.
2. **Adopt OMP as the primary harness for orc-werk's own delivery seats,
   encoding the policy/glue split `harness-independence.md` already
   prescribes: policy → OMP agent definitions, result schemas, and hooks;
   glue → deleted where OMP already provides it.** The orc ledger, PR head
   sha as candidate identity, `scripts/check.sh`, `docs_check.py`, task
   cards, and `scripts/watch_pr.py` are unchanged; only the seat-discipline
   layer moves from prose to structure. (Chosen.)
3. **Replace the orc kernel and ledger itself with OMP-native mechanisms**
   (e.g. treat OMP task state as the durable record). Rejected outright:
   this violates `T3`/`ADR-0005` (canonical state is pushed, never pulled;
   no extension or hook writes `.orc`) and collapses the very distinction
   `nother-guide` draws between contract (the ledger) and adapter/glue (the
   harness driving it). Not seriously considered.

## Decision

Option 2.

### Current → target mapping

| Need | Today (orc-werk) | Target (OMP native) |
|---|---|---|
| Role definitions (scout/ship/verify) | prose §Roles in `PLAYBOOK-WATCHTOWER` | `.omp/agents/{scout,ship,verify}.md` frontmatter + body |
| Model/effort per seat | prose §Model and effort selection | agent `model:` field, `thinking-level`, per-item `effort` |
| Result contract (`VERDICT:`, Ambiguities) | prose in `PLAYBOOK-AGENT-CLI` | agent `output:` JSON schema with `schemaMode: strict`; a missing required field is a failure, not a question |
| Verify seat cannot push/commit/comment | prose §2/§4 | agent `tools` restriction + a `tool_call` hook blocking `git push`/`git commit`/`gh pr comment`/`gh pr review`/`gh pr merge` |
| Ship works in its own worktree; never merges | prose Conventions + `AGENTS.md` | ship agent creates `.worktrees/<branch>`; a hook fences `edit`/`write` to that path; the PR stays the externally resolvable candidate |
| Dispatch brief | task card + `orc dispatch` intent | unchanged: task card is the tier-1 durable spec; the batch/task brief is the tier-2 brief, no new file |
| Record before yield | prose | a `tool_call` hook on `yield` blocked until a successful `orc record` was observed in the session |
| Executor identity (`executor-identity/v1`) | hand-typed `--model`/`--session-ref`/`--seat-ref` | model resolved from the agent's own `model:`; `session_ref`/`seat_ref` derived from the OMP session/agent identity; documented in `docs/adapters/omp/` |
| Evidence / transcript | PR body, `.orc` evidence refs | + `history://<id>`, referenced from the ledger as supplementary, machine-local evidence |
| Fresh-session orientation | skill §9 prose | unchanged: bare `orc` first; `.omp/RULES.md` carries the sticky seat invariants |
| Harness glue | `.claude/skills` symlink, `CLAUDE.md` | **kept** — see "Claude Code glue" ruling below |

What is **NOT** replaced by OMP: the orc kernel and ledger (`orc`, `.orc/`),
candidate identity (a PR head sha, never an OMP session or task id),
`scripts/check.sh`, `docs_check.py`, task cards as durable specs, and
`scripts/watch_pr.py` (kept — an `E4` lever, not ceremony this ADR touches).

### Isolation ruling: ship seats use a git worktree + PR, not OMP `isolated`

This is the one real mechanical fork the migration forces, and it is a
`T4` (execution is not acceptance) question in disguise. OMP's `task`
`isolated: true` mode merges on completion: patch mode applies the root
patch to the parent tree, and branch mode commits to `omp/task/<id>` and
cherry-picks into the parent HEAD **immediately** on task completion
(`omp://tools/task.md`, flow steps 11 and 15). That lands work before
independent verification — a direct violation of `T4` and of the standing
rule that the watchtower merges only after a verdict. It also leaves no
externally resolvable candidate identity for a patch (`T3`'s "measuring a
durable artifact is not observing a process" requires a resolvable
identity such as a commit sha; an unmerged, uncommitted patch has none).

Three options were on the table (the migration plan's "Isolation
decision"):

- **B (chosen).** The ship agent is a **non-isolated** OMP subagent that
  creates `.worktrees/<branch>` itself with plain `git`, commits, pushes,
  and opens the PR — exactly as today's ship seat does, just running as an
  OMP agent instead of an ad hoc session. Candidate identity stays a PR
  head sha. The verify agent fetches the PR into its own worktree, derives
  the sha itself, and records the verdict. The watchtower merges only
  after `accepted`. This is a zero-change to every ledger contract:
  `orc record`'s `--outcome`/`--verdict` shapes, candidate identity, and
  the push-only rule are all untouched.
- **A (rejected).** OMP `isolated` (patch or branch mode). Mechanically
  cheapest, but it lands work before verification unless the watchtower
  session itself lived on a long-running per-run integration branch, and
  concurrent ships would then interleave commits on it — a candidate
  identity contamination hazard with no clean resolution.
- **C (compatible with B, not adopted in this decision).** `isolated` is
  reserved for read-only or throwaway probes (`A3` empirical-fork spikes)
  that produce no candidate at all. This is compatible with option B and
  may be adopted alongside it later; it is not itself in scope for this
  ADR or M5.

### `T3`/`ADR-0005` ruling: no OMP hook or extension writes `.orc`

`ADR-0005` already establishes that orc-werk's canonical state is pushed,
never pull-observed, and that "an OMP subagent is yet another external
executor pushing observations in" is exactly the seam that ADR defines.
This ADR restates it explicitly for the OMP migration so it is not
mistakenly read as reopened: **no `.omp/extensions/*` hook or OMP task
mechanism writes to `.orc` directly, ever.** Hooks (`.omp/extensions/
orc-seat.ts`, `TASK-M5-005`) are sensors only — they may **block** a
`tool_call` (deny `git push` from the verify role, deny `yield` until a
successful `orc record` was observed in the session, deny `gh pr merge`
from any subagent) but they never call `orc record` or edit a journal
file themselves. Every ledger write remains a seat pushing its own
observation via `orc record` or a merge-only config edit, exactly as
`PLAYBOOK-AGENT-CLI` already requires of every executor regardless of
harness.

### `V7` ruling: verify runs on a different model family than ship

`nother-guide`'s `V7` ("model diversity is a risk control": verification
uses a different model family from authorship; same-family use is a
named, time-boxed deviation with an end trigger) was a live, undocumented
violation before this decision — the previous informal practice paired a
Sonnet ship seat with an Opus verify seat, both Anthropic. Operator
ruling: **verify runs on the `openai-codex` family (`gpt-5.6-sol`); ship
runs on `anthropic` (`claude-sonnet-5`); scout runs on `anthropic`
(`claude-opus-5`)**, encoded directly in `.omp/agents/verify.md`'s and
`.omp/agents/ship.md`'s `model:` fields — a `contract`-layer requirement
(`boundaries.md` §5, §6) enforced by the agent definition itself rather
than a recorded deviation, because the two families genuinely differ.
Scout shares ship's family; this is acceptable because scout is read-only
reconnaissance, never a verdict-bearing seat, so `V7`'s risk-control
purpose (an independent verdict) does not apply to it.

### nother-guide adopted by pinned reference

`nother-guide` is adopted as a pinned external reference, not vendored or
copied into this repository: `git@github.com:odjhey/nother-guide.git`
commit `aa1fc24`, checked out locally at `/Users/odz/proj/nother-guide`
for citation. orc-werk's own docs remain the canonical, checked contract
(`docs_check.py` validates only `docs/`); `nother-guide`'s portable docs
(`principles.md`, `boundaries.md`, `harness-independence.md`,
`harness-capabilities.md`, `adoption-ladder.md`, `verification.md`) are
cited by section/principle id (e.g. `T3`, `V7`, `E1`, `I2`) the same way
this ADR cites them above, never paraphrased into a competing orc-werk
contract. Deviations from a cited principle are named with an explicit
trigger, per `nother-guide`'s own `I3` ("every deferral, relaxation, and
risk names its trigger"):

- **Scout shares ship's model family (deviation from strict `V7`
  scope).** Trigger: scout begins rendering a verdict-bearing judgment
  (rather than read-only recon) — if that ever happens, scout moves to a
  third family or drops out of the seat table entirely.
- **`.omp/agent/sessions/*` transcript paths are machine-local, not a
  portable ledger evidence ref.** Trigger: named already in the migration
  plan's risk register — verdict/findings ride the PR and the ledger's
  `extensions` as the durable evidence; the transcript path is
  supplementary only, never load-bearing for a verdict.
- **`task.agentIdleTtlMs` parks idle agents at 7 minutes.** Trigger: a
  seat parked mid-task loses no state (`hub` `send` revives it) unless a
  seat is observed losing work to this timeout, in which case the value is
  revisited as a recorded policy change.

### Claude Code glue is kept

Per operator ruling, `.claude/skills` (the symlinked `orc-ledger` skill)
and the root `CLAUDE.md` are **kept** — Claude Code remains a harness in
use alongside OMP, so this glue is not yet dead per
`harness-independence.md`'s own rule ("delete glue when the harness
provides it" applies only once no harness needs it). `TASK-M5-006` is
scoped down accordingly: it delivers the `orc-ledger` skill v6 and the
`scripts/check.sh` loud-skip line, and does **not** delete
`.claude/skills` or `CLAUDE.md`.

### `orc onboard` OMP scaffold is in M5

Per operator ruling, `orc onboard` gains an OMP-agent scaffold step in M5
(`TASK-M5-007`), not deferred to a later milestone — adopting repos should
be able to install the same `.omp/agents/*` + `.omp/config.yml` pattern
this ADR ratifies for orc-werk's own use, contract-first (`PRODUCT-ADOPTION`
amended before the scaffold step is implemented).

**Landed:** `TASK-M5-007` is implemented, not merely planned. It merged to
`master` at commit `e102e1e` ("TASK-M5-007: orc onboard --omp scaffolds the
.omp/ seat pattern", PR #291) — a fifth idempotent `orc onboard` step,
`src/orc_werk/omp_scaffold/`, installs `.omp/agents/{scout,ship,verify}.md`,
`.omp/config.yml`, and `.omp/RULES.md` from the canonical package origin
under the same never-clobber/`--force` discipline as the existing steps,
with `docs/product/adoption.md` amended for the new rung. This is grounded
in the merged commit, a durable fact that needs no as-of instant.

### `scripts/watch_pr.py` is kept

Per operator ruling, `scripts/watch_pr.py` is kept unchanged: it encodes
policy (blocker order, verdict staleness) as a lever, per `E4` ("build the
lever, not the artifact"), not as ceremony this migration retires.

### `CONTRACT-STORAGE-CONCURRENCY` A3 note

The one-dispatcher-per-run convention (`PLAYBOOK-AGENT-CLI`) remains
**seat semantics** under this migration, unchanged from
`CONTRACT-STORAGE-CONCURRENCY`'s existing framing: it is process
discipline agents follow, not a correctness precondition the storage
layer depends on. Moving the rule's enforcement surface from prose to an
OMP hook (`TASK-M5-005`) does not change this — the hook enforces the same
seat-semantics rule at a stronger rung; the storage layer's own safety
under concurrent dispatch is unaffected either way.

## Consequences

Positive:

- Seat discipline that was previously enforced only by an agent reading
  and complying with prose is now enforced, where OMP's capability test
  (`TASK-M5-001`) confirms it, at a stronger rung: a schema rejection, a
  blocking hook, or an unrepresentable state, per `I2`.
- `PLAYBOOK-WATCHTOWER` and `PLAYBOOK-AGENT-CLI` shrink to the parts that
  remain genuinely harness-independent policy (roles, invariants,
  recording mechanics), with OMP-specific mechanics moved to
  `docs/adapters/omp/` where provider vocabulary belongs
  (`ADAPTERS-README`).
- The ledger, candidate identity, and every recording contract are
  unchanged — this decision is fully additive to `ADR-0005` and
  `ADR-0006`, not a reopening of either.
- This run (`m5-omp-harness-pilot`) is itself the first delivery shipped
  by `.omp/agents/ship.md` and verified by `.omp/agents/verify.md` on a
  different model family, so its own journal is the acceptance evidence
  for the migration (per `E2`, one unit before fan-out).

Costs:

- A second harness-specific directory (`.omp/`) alongside the kept
  `.claude/` glue, until a future decision retires the latter.
- `.omp/agent/sessions/*` transcript evidence is machine-local; the ledger
  and PR remain the durable, portable evidence, per the named deviation
  above.
- The hook-enforced rules (`TASK-M5-005`) are only as strong as OMP's own
  `tool_call` guard mechanism; `TASK-M5-001`'s capability test is the
  gate that must pass, with a red-then-green proof (`V2`), before any rule
  is trusted to fire.

Not decided here: whether `.claude/` glue is ever retired (a future
decision, gated on Claude Code no longer being a harness in use); OMP
`isolated` for throwaway probes (option C, compatible but not adopted);
whether a future non-Anthropic, non-openai-codex third family is added
for scout once/if it becomes verdict-bearing.

## Supersedes

None. This ADR is additive to `ADR-0005` (push recording, not pull
observation) and `ADR-0006` (bounded assurance re-request); it does not
change either.

## Related contract IDs

- `ADR-0005`, `ADR-0006`
- `CONTRACT-STORAGE-CONCURRENCY`
- `EXT-EXECUTOR-IDENTITY-V1`
- `M5-OMP-FIRST-DELIVERY`
- `TASK-M5-001`, `TASK-M5-002`, `TASK-M5-003`, `TASK-M5-004`, `TASK-M5-005`, `TASK-M5-006`, `TASK-M5-007`, `TASK-M5-008`
- `ADAPTERS-README`
- `PRODUCT-ADOPTION`
- `SEAT-RELIABILITY` (`docs/delivery/seat-reliability.md`, cited by the `V7` amendment below)

## Amendment (2026-09-07, `TASK-M5-008` pilot write-up, PR #280): `V7` states the invariant; the model assignment is deployment preference

The `V7` ruling above named `openai-codex` (`gpt-5.6-sol`) as the verify
family and `anthropic` (`claude-sonnet-5`) as the ship family, calling that
specific pairing a `contract`-layer requirement "because the two families
genuinely differ." Two calendar days of post-ratification delivery
(2026-09-06/07) — the ledger's own record, not this write-up's prose — show
the pairing itself did not hold, while the invariant it was meant to
encode did:

- Two `openai-codex` verify spawns (`VerifyM5Pilot`, `VerifyM5PilotB`,
  both against `m5-omp-harness-pilot`'s `docs` work) died within seconds
  of `usage_limit_reached` on 2026-09-06 and recorded nothing to the
  ledger — no `FACT-ASSURE-SETTLED`, so no assurance budget was spent
  (`docs/delivery/seat-reliability.md`'s 2026-09-06 entries 1–2).
- As of `2026-09-07T02:18:46Z` — a recount performed for this attempt,
  independent of attempt 1's cutoff and its miscount — join every
  `.orc/<run>/journal.jsonl` record with `id == "FACT-ASSURE-SETTLED"` to
  its own `seq` in the sibling `.orc/<run>/times.jsonl` for `observed_at`;
  keep every pair (regardless of `verdict` — **a `rejected` settlement is
  still a settled verify verdict and counts**, the omission that got
  attempt 1 rejected) whose `observed_at` falls on 2026-09-06 or
  2026-09-07 UTC; group by `work_id`. That join currently returns **15**
  settled verify verdicts across 14 unique works (`fix-262-docs-polish`
  verified twice: rejected, then accepted) — `m5-omp-harness-pilot` (PR
  #267), `fix-verify-seat-fallback` (PR #268), `adopt-270-attempt-binding`
  (PR #270), `docs-external-candidate-lane` (PR #271), `fix-262-docs-polish`
  (PR #272, both verdicts), `task-m5-003` (PR #273), `fix-254-active-filter`
  (PR #274), `task-m5-006` (PR #275), `fix-266-reobservation` (PR #276),
  `task-m5-001` (PR #277), `chore-verify-followups` (PR #278), `task-m5-002`
  (PR #279), `task-m5-008` (PR #280, **rejected** at `02:01:57Z` — settled,
  not "still ASSURING" as attempt 1 claimed; the work reopened as attempt 2
  per `ADR-0006`'s bounded re-request), and this amendment's own attempt 1
  (PR #283, **rejected** at `02:14:58Z`, the rejection this attempt 2
  answers). **All 15 ran on `google-antigravity/gemini-3.8-flash`; zero ran
  on `openai-codex`.** This count is monotonically increasing and this text
  does not depend on it staying 15: every attempt so far has recounted
  higher than the one before (9 → 10 → 13 → 15) purely because sibling
  seats keep settling verdicts while this run is in flight, and a future
  reader re-running the join above and getting a number larger than 15 is
  the expected outcome, not a contradiction of this text. Whole-ledger, at
  any point in time — 141 `FACT-ASSURE-SETTLED` records as of the same
  instant, going back to 2026-08-28 — **zero has ever carried
  `executor-identity/v1.model` = `openai-codex/*`.** That whole-ledger
  zero, never falsified by a larger window count, is the load-bearing fact
  this amendment rests on; the per-window number above is corroborating
  detail only, expected to keep growing. Ship, over the same window,
  settled 15 `FACT-EXEC-SETTLED` records (14 unique works,
  `fix-262-docs-polish` shipped twice): 13 on an `anthropic/claude-sonnet-5`
  variant, 2 on `xai-oauth/grok-4.6` (`adopt-270-attempt-binding`,
  `docs-external-candidate-lane`) — 13 + 2 = 15, matching the verify count
  above and including both `task-m5-008` and this amendment's own attempt
  1. Ship's own family was not fixed either, and verify differed from
  ship's *actual* family every single time, never merely from its
  `anthropic` default.
- `docs/delivery/seat-reliability.md`'s 2026-09-06 entry recorded this at
  the time as "a recorded deviation, not an amendment," naming an
  explicit trigger: revisit once Codex quota is restored, or once a
  `retry.fallbackChains` key exists so a usage-limit death falls through
  automatically. Neither trigger fired by 2026-09-07; the deviation is
  now the entirety of observed practice, which is exactly the standing-
  deviation-without-an-amendment condition `AGENTS.md` rule 4 forbids
  keeping quiet.

**Amended ruling.** `V7`'s load-bearing requirement is the invariant this
ADR's own heading already states — **verify runs on a model family
different from the ship seat that actually produced the candidate** — not
the specific `openai-codex` assignment, which was an implementation
preference that did not survive contact with quota reality. This ADR no
longer names a specific verify family or model. The prioritized, ordered
model list a verify spawn resolves against is a deployment-preference
decision that belongs in `.omp/agents/verify.md`'s `model:` field alone
(already reordered this way by PR #268, `google-antigravity/gemini-3.8-flash`
first, `openai-codex/gpt-5.6-sol` second, ahead of this amendment landing)
and MUST continue to satisfy the invariant above — every entry non-Anthropic,
for as long as ship runs `anthropic/*` — without this ADR re-litigating or
re-pinning the list itself. Scout's shared-family deviation (see the
`nother-guide adopted by pinned reference` section above) is unaffected:
scout remains read-only and never verdict-bearing, so `V7`'s risk-control
purpose does not reach it.

The original operator ruling above is left as written: a historical
record of what was decided on 2026-09-06 and why, not rewritten to read
as though it always said this.

## Amendment (2026-09-07, run `docs-hook-capability-limit`): the hook's command-blindness bounds enforcement to four rungs, one of them open

`TASK-M5-005`'s hook-based guards (Decision's mapping row "Verify seat cannot
push/commit/comment... a `tool_call` hook blocking `git push`/`git
commit`/`gh pr comment`/`gh pr review`/`gh pr merge`", above) were
re-delivered as run `task-m5-005-guards` after issue #290's three-attempt
rejection of the original `task-m5-005`. Attempt 1 of the re-delivery was
itself rejected with six reproduced-in-system REJECTs (`orc history
task-m5-005-guards --limit 0`, seq 16, `FACT-ASSURE-SETTLED`, work
`guards`) against guards 1, 2, 3, and 5, plus a native-extension-load
failure — every rejected guard decided by matching the text of
`event.input.command`, and every one was defeated by a new shell
construct: guard 2 by an escaped `g\h pr merge …`, guard 3 by an escaped
`g\it push …` from a live session whose `session_init.agent` was
`verify`, guard 5 twice (an escaped `g\it push origin +master`, and a
command-local `PATH` assignment the hook's own resolution never applied).
Issue #290 states the bound this establishes: the hook's `tool_call`
event hands a guard `event.input.command` as one string — "never shell
argv, never the resolved executable, never process identity" (this run's
own `FACT-INTENT-SUBMITTED`, `docs-hook-capability-limit`) — and "the
shell has `||`, `&&`, `;`, command substitution, aliases, wrappers (`uv
run`), `eval`, and quoting," so "deciding 'does this command string
invoke X' is not decidable from the string" (issue #290 body). Issue
#290's same-day correction narrows the remedy further: even "whitelist
the exact shape of a clean invocation" is a text-shape decision,
legitimate only because it inverts which residual error it accepts
(false-negative-on-gate-satisfaction, not false-negative-on-denial); it
does not change the underlying bound.

Operator ruling, 2026-09-07 (amended in-flight after an initial
overstatement of what branch protection can do — see rung 2): this bound
splits the M5 enforcement design ("Decision" above, and its
`TASK-M5-005` row) into four rungs, only three of which are enforceable,
stated here rather than left uncovered by omission.

**1. Structural/context rules → the OMP hook.** The one guard in
`task-m5-005-guards` seq 16 that was *not* rejected is guard 4, the
cwd-derived worktree fence — it decides on structural context (`ctx`'s
own cwd) the hook is actually handed, not on command prose, and
`docs/reports/2026-09-07-omp-capability-test.md` §2 independently proves
the mechanism red-then-green. This is the one rung `TASK-M5-005`'s hook
may still enforce.

**2. No direct write to a shared branch → server-side GitHub branch
protection.** Read back from `gh api
repos/odjhey/orc-werk/branches/master/protection`, reconfirmed unchanged
at `2026-09-07T06:44:29Z` (an as-of-instant reading, not a standing fact
— re-run the same call to confirm it still holds):

```
required_status_checks         {'strict': True, 'contexts': ['ci-required'], 'checks': [{'context': 'ci-required', 'app_id': 15368}]}
enforce_admins                 {'enabled': True}
required_pull_request_reviews  {'required_approving_review_count': 0, 'dismiss_stale_reviews': False, 'require_code_owner_reviews': False, 'require_last_push_approval': False}
allow_force_pushes             {'enabled': False}
allow_deletions                {'enabled': False}
restrictions                   None
required_linear_history        {'enabled': False}
```

`enforce_admins` and `required_pull_request_reviews` (0 required
approvals, deliberately — it blocks direct pushes without inventing a
review step no one is staffed to perform) were added on 2026-09-07; the
rest predates this amendment. Net effect: no identity, including the
repo admin, can write directly to `master` — a change can only arrive via
a PR whose `ci-required` check passes and whose branch is up to date.
The evidence grade is a configuration read-back, not an observed
rejection: no destructive live probe (an actual direct push) was
attempted, because with force-push and deletion disabled a junk commit
that unexpectedly landed could not be cleanly removed.

**3. Record-before-yield → enforced structurally for the paths that
reach `ACCEPTED`/`BLOCKED` through bound assurance; the cancellation
path is a disclosed, unenforced escape from that rung (issue #293).**
Verified against `src/orc_werk/core/reducer.py` at this amendment's own
head: the only path to `STATE_ACCEPTED` folds `FACT_CANDIDATE_OBSERVED`
(`reducer.py:448-467`, which requires the *current* Execution's
`outcome == "completed"` — INV-005) into `STATE_ASSURING`
(`reducer.py:510-513`, `546-549` — the only two rows that set it), then
`FACT_ASSURE_SETTLED` with `verdict == "accepted"` (`reducer.py:594-595`,
`620-622`) into `STATE_ACCEPTED`; `FACT_CANDIDATE_OBSERVED` itself
requires `STATE_EXECUTING` (`reducer.py:449`), which is entered only by
`FACT_EXEC_STARTED` (`reducer.py:368-369`, requires prior `STATE_READY`)
and left only by `FACT_EXEC_SETTLED` (`reducer.py:406-407`). No fold
reaches `ACCEPTED` — or, by the identical arithmetic, the seat-triggered
path to `BLOCKED` via a rejected/inconclusive verdict or an abandoned
attempt (`reducer.py:623-627`, `641-649`, `680-715`) — without a prior
`FACT-EXEC-SETTLED`. **That is the full and correct scope of the claim:
on the paths gated by bound assurance, no hook rung is needed because
the state machine already carries it.**

The claim does not extend past that gate, and an independent verify
seat proved the gap in system code against this run's own head, filed
as issue #293: `FACT_WORK_CANCELLED` is legal "from any non-terminal
state" (`reducer.py:717-729`), including `STATE_READY` immediately
after `FACT-WORK-READY`, before any Execution ever starts, and the `orc
cancel` CLI verb that fires it (`src/orc_werk/cli/main.py:1157-1196`)
derives its actor from `$USER`/`whoami` with **no caller-role
authorization** — nothing in the verb distinguishes an operator's shell
from a ship or verify seat's own. A targeted real-code probe (`uv run
python -m unittest
tests.core.test_scenarios.Scn001HappyPathTest.test_terminal_accepted
tests.core.test_reducer_transitions.ReservedUnreachableTest.test_fact_work_cancelled_is_reachable
tests.scenarios.test_cli_cancel.CancelledReportingTest.test_cancelled_is_settled_and_excluded_from_active_index`)
ran 3 tests OK, including terminal cancellation reaching a settled
state with no execution outcome recorded at all.
`Orchestrator.cancel_work` is documented as "Operator-only terminal
closure" (`src/orc_werk/app/orchestrator.py:857-858`), and a seat's own
recording protocol calls only `orc record`, never `orc cancel`
(`docs/cli/README.md` "`orc cancel`", "Operator-only terminal
closure") — but that is protocol prose describing intended use, not a
kernel-enforced distinction between an operator and a seat holding the
same OS identity. Issue #293 leaves open whether cancel-from-any-state
is intended, whether the record-before-yield rung needs to say
explicitly that it covers only the assurance-bearing paths, and whether
caller-role authorization is even meaningful given every seat
authenticates identically (rung 4 below); none of those questions is
resolved by this amendment, and no code fix is proposed here.

**4. Merge authority ("only the watchtower may merge") → open residue,
no enforcement rung, prose plus after-the-fact detection only.**
`restrictions` above is the one field that binds a push/merge
restriction to a specific actor, and it is `None`; even populated, it
keys on GitHub user/team/app identity, not on seat role, and every seat
in this repository is currently provisioned with one shared GitHub
credential rather than a distinct one per seat (`gh api user` →
`login: odjhey`, reconfirmed at `2026-09-07T06:44:29Z`) — there is no
seat-scoped identity for a restriction to bind to. This is not covered
by rung 1, for a different reason than an earlier draft of this
amendment gave: the hook *can* see which role is running its own
session — `session_init.agent` is a structural field the session's own
entries carry, not a text match against prose
(`docs/reports/2026-09-07-omp-capability-test.md` §6 Correction) — but
deciding *whether a given command is a merge* is not something the hook
receives at all. The hook is handed `event.input.command` as one string
(`readCommand`), never shell argv, the resolved executable, or process
identity, and the shell defeats any text match against that string:
`task-m5-005-guards` seq 16 guard 2 landed a live `g\h pr merge 999
--squash` — the shell strips the backslash before exec — past a hook
matching the literal token `gh`
(`docs/reports/2026-09-07-omp-capability-test.md` §6b). **Role is
visible; the action is not decidable.** A rung-1 hook could deny every
`bash` call from a given role, but it cannot single out *merge*
commands from that role without falling back to the same defeated
command-text matching. Nor is this covered by rung 2 (branch protection
restricts *who may write to the ref*, not *which agent-role of the one
authenticated identity did it*). It remains exactly what it was before
this amendment: `PLAYBOOK-WATCHTOWER`/`PLAYBOOK-AGENT-CLI` prose plus
after-the-fact ledger/PR-history detection — named here as an
unenforced residue rather than left uncovered by omission.

The `TASK-M5-005` re-delivery (`task-m5-005-guards`) implementing rung 1
above was still in-flight, not landed, as of `2026-09-07T06:44:29Z`
(`gh pr view 284 --json state,mergedAt,headRefOid`: `state: OPEN`,
`mergedAt: null`, head `c11601cb`). This amendment does not
describe that PR's contents or claim its guards are fixed — only that
guard 4's mechanism is proven and the other three guards' *design
target* moves to rungs 2–4 above, per the operator ruling that produced
this amendment.

The original operator ruling and M5 mapping above are left as written: a
historical record of what was decided and designed before this bound was
established, not rewritten to read as though it always said this.
