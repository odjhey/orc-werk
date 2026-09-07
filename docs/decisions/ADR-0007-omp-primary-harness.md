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
- As of this amendment's own commit (`2026-09-07T10:02:48+08:00`; the
  ledger is live and settles underneath any snapshot, so a bare integer
  here would already be stale by the time a future reader checks it —
  re-derive with `orc history <run> --limit 0` or a join of
  `FACT-ASSURE-SETTLED` against `times.jsonl` for the current count),
  every verify verdict the ledger had settled between 2026-09-06 and
  2026-09-07 ran on `google-antigravity/gemini-3.8-flash`: 13 settled
  `FACT-ASSURE-SETTLED` records across 12 works — `m5-omp-harness-pilot`
  (PR #267), `fix-verify-seat-fallback` (PR #268), `adopt-270-attempt-binding`
  (PR #270), `docs-external-candidate-lane` (PR #271), `fix-262-docs-polish`
  (PR #272, rejected then accepted — the one work verified twice),
  `task-m5-003` (PR #273), `fix-254-active-filter` (PR #274), `task-m5-006`
  (PR #275), `fix-266-reobservation` (PR #276), `task-m5-001` (PR #277),
  `chore-verify-followups` (PR #278), `task-m5-002` (PR #279). **Zero of
  these ran on `openai-codex` — and whole-ledger, at any point in time,
  zero `FACT-ASSURE-SETTLED` record has ever carried `executor-identity/v1.
  model` = `openai-codex/*`.** That whole-ledger zero, not the 13, is the
  load-bearing fact; the per-window count is corroborating detail that
  will drift as more works settle. (`TASK-M5-008`'s companion run was
  still `ASSURING`, unsettled, as of the same cutoff, so it is not
  counted either way.) Ship, over the same window, ran mostly on an
  `anthropic/claude-sonnet-5` variant but twice on `xai-oauth/grok-4.6`
  (`adopt-270-attempt-binding`, `docs-external-candidate-lane`) — ship's
  own family was not fixed either, and verify differed from ship's
  *actual* family every single time, never merely from its `anthropic`
  default.
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
