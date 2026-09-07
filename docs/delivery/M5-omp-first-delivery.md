---
id: M5-OMP-FIRST-DELIVERY
type: milestone
status: current
authority: normative
description: M5 — Oh My Pi (OMP) becomes orc-werk's primary delivery harness for its own seats; seat discipline moves from prose playbooks into OMP agent definitions, result schemas, and hooks, per ADR-0007 and the nother-guide principles it adopts by pinned reference.
---

# M5 — OMP-first delivery

## Context

M4 closed "cockpit and clarity"; the product stayed thesis-complete and the
operator's stance was friction-driven, no new milestone, until a real gap
surfaced. It did: orc-werk's own delivery seats (watchtower, ship, verify)
were driven entirely by prose — `PLAYBOOK-WATCHTOWER`, `PLAYBOOK-AGENT-CLI`,
and the `orc-ledger` skill, re-taught to every fresh session by convention,
with no mechanism rejecting a session that ignored them. The adopted
`nother-guide` (pinned reference, commit `aa1fc24`) names exactly this
pattern and its remedy: split seat machinery into policy (survives any
harness) and glue (delete when the harness already provides it), and prefer
whatever rung enforces a rule most strongly. `ADR-0007` is the ruling this
milestone implements; read it first for the full decision record, the
isolation fork, the `V7` model-family ruling, and the deviations named with
triggers. This document tracks the delivery plan and its acceptance.

**What M5 does not touch:** the orc kernel (`src/orc_werk/*`), the `.orc/`
journal and its contracts, candidate identity (a PR head sha), the
`scripts/check.sh` gate shape, `docs_check.py`, task cards as durable
specs, or `scripts/watch_pr.py` — all per operator ruling and `ADR-0007`.

## The pilot rule

`TASK-M5-004` (this delivery's own `.omp/agents/*` + `.omp/config.yml`) is
shipped by the `.omp/agents/ship.md` seat and verified by the
`.omp/agents/verify.md` seat on a different model family, recorded in
`.orc`, and merged by the watchtower after an accepted verdict. **This
run's own ledger journal (`m5-omp-harness-pilot`) is the acceptance
evidence for the migration** — a real seat-discipline delivery through the
new harness, not a description of one. Findings from running it feed
`TASK-M5-008`'s seat-reliability log and `TASK-M5-001`'s capability report.
This is `E2` in practice: pilot one unit before fanning the remaining cards
out.

## Phase 0 — Capability test (gate)

Before any policy is encoded into an OMP agent definition or hook, the
harness's actual capabilities are probed and recorded, not assumed. Five
points, run against the installed OMP version, each with a pass/fail
recorded against the real command and its observed output — an untested
capability is a gap, not a pass, per `nother-guide`'s
`harness-capabilities.md`:

1. Spawn verify on a non-Anthropic model family with a tool restriction
   that denies `git push`; confirm the hook denies it against a disposable
   local remote.
2. Give a task item no `cwd`; confirm the ship agent creates its own
   worktree and a hook fences writes outside it — and confirm the guard is
   observed firing red before it is trusted (`V2`).
3. `outputSchema` + `schemaMode: strict`: confirm a result missing a
   required field (e.g. `verdict`) is rejected, not silently accepted.
4. `task.maxRuntimeMs` stops a task on timeout; confirm descendants stop
   and `history://` is retained afterward.
5. Read a full transcript from `~/.omp/agent/sessions/...jsonl` after a new
   session and after a reboot; confirm it survives both.

Open probe carried into the report: whether a hook or extension can learn
the running agent's role (name) to apply per-role deny rules. The report
answered **yes** (`session_init.agent`, `TASK-M5-001`'s §6 correction,
2026-09-07) — but per the 2026-09-07 operator ruling that answer did not
save the role-independent fallback guards either: block-`yield`-until-a-
record and block-`gh pr merge` both decide by matching the bash command's
own text, and `task-m5-005`'s rejected attempt 1 showed that text is
defeated by shell escaping regardless of whether role is known. Both were
dropped from the hook's scope; `AGENTS.md` records where they now live.
`TASK-M5-001` is this phase's deliverable.

## Phase 1 — Policy layer (docs first)

`ADR-0007` is authored and ratified before any `.omp/` file is written,
per `AGENTS.md` rule 4 (docs amend first). Alongside it:

- `PLAYBOOK-WATCHTOWER` shrinks to ≤80 lines: Roles collapses into a seat
  table (role, effects boundary, model family, effort, result schema,
  observed failures), keeping Pipeline, Sizing, Autonomy, Dormant
  lifecycle, and Audit trail. §Model and effort selection and the
  worktree/`watch_pr.py` Conventions lines are deleted — they move to
  agent bodies and the hook.
- `PLAYBOOK-AGENT-CLI` keeps §1–4 (observations only, no self-assurance,
  derive identity, `inconclusive` semantics), §6 (multi-work etiquette),
  and §9 (fresh-session orientation). OMP-specific mechanics move to
  `docs/adapters/omp/mapping.md`; the §7 worked example moves to
  `docs/reports/` as historical reference (`T6`: append, do not delete).
- `AGENTS.md` absorbs `nother-guide`'s ten hard rules into its existing
  twelve (deduped), and its "Delivery workflow" section is rewritten in
  OMP terms.
- `.omp/RULES.md` (sticky, ≤10 lines) carries the seat invariants that must
  survive context compaction in a long watchtower session.
- `docs/adapters/omp/{README,mapping,capabilities,conformance}.md` are
  authored per `ADAPTERS-README`: the `executor-identity/v1` field
  mapping (model/session_ref/seat_ref/role resolved from the OMP agent and
  session identity), the capability-test results link, and an OMP example
  added to `docs/extensions/executor-identity/v1/examples.md`.
- `CONTRACT-STORAGE-CONCURRENCY`'s A3 note is confirmed unchanged in
  `ADR-0007` (already done there).

`TASK-M5-002` and `TASK-M5-003` are this phase's deliverables.

## Phase 2 — Harness layer (`.omp/`)

- `.omp/agents/scout.md` — read-only recon; `tools: read, grep, glob, bash`;
  output schema `{report, unverified[], ambiguities[], stale_after}`.
- `.omp/agents/ship.md` — mid-tier model; full tools; `autoloadSkills:
  orc-ledger`; creates `.worktrees/<branch>`, runs `bash scripts/check.sh`,
  pushes, opens the PR, records the execution settlement, never merges;
  output schema `{run_id, work_id, branch, pr, head_sha, gate,
  not_covered[], ambiguities[], recorded}`.
- `.omp/agents/verify.md` — a different model family from ship; `tools:
  read, grep, glob, bash`; fetches the PR into its own worktree, derives
  the sha itself, runs the gate, defaults to `inconclusive`/`rejected` per
  the recording rules, records the verdict; output schema `{run_id,
  work_id, verdict, derived_head_sha, evidence_grade, findings[],
  ambiguities[], recorded}`.
- `.omp/extensions/orc-seat.ts` — one `tool_call` guard: fence `edit`/
  `write` outside `.worktrees/<branch>` from the ship role, the sole
  guard that decides on structure rather than command text. **Amended
  2026-09-07** (operator ruling, `task-m5-005-guards` seq 16): this
  bullet originally also planned three text-matching guards in the same
  hook — block `yield` until an `orc record` bash call with exit `0`/`3`
  was observed; block `gh pr merge` from any subagent; deny `git push`/
  `git commit`/`gh pr comment`/`gh pr review` from the verify role — all
  three defeated by shell escaping against the bare command string a
  `tool_call` hook receives, regardless of the calling role being known.
  All three moved rung instead: GitHub branch protection on `master` for
  shared-branch push, the orc ledger's own state machine for
  record-before-yield, and no enforcement rung at all for merge
  authority. Ships with a red test (`V2`): a script proving the retained
  guard fires before it is trusted.
- `.omp/config.yml` — `task.enableEffort`, `task.maxRuntimeMs`, and
  `modelRoles` for ship/verify/scout.
- `orc-ledger` skill v6 — §3's seat section references the OMP agent
  roles; recording mechanics are unchanged; the skill stays installed by
  `orc onboard` so adopters on other harnesses keep working.

`TASK-M5-004` (the pilot card — **delivered by this pilot PR itself**;
see its card body), `TASK-M5-005`, and `TASK-M5-006` are this phase's
deliverables.

## Phase 3 — Retire

- Deleted: `PLAYBOOK-WATCHTOWER`'s §Model and effort selection and its
  worktree/`watch_pr.py` Conventions lines (now enforced by agent
  definitions and the hook); the "brief lives in the card" duplication
  (task cards stay the sole tier-1 spec).
- Kept (per operator ruling): `.claude/skills` symlink and `CLAUDE.md` —
  Claude Code remains a harness in use; `scripts/watch_pr.py`;
  `scripts/check.sh`; `docs_check.py`; task cards; `.orc/`.
- `scripts/check.sh` gains the `V5` loud-skip line: `check: green. NOT
  covered: <list|none>` as its final line (a rung-0 checklist item that
  was missing).

`TASK-M5-006` is this phase's deliverable (bundled with its Phase 2 skill
work, since both land in the same check.sh/skill surface).

## Phase 4 — Product follow-through

- `orc onboard` gains an OMP scaffold step: it installs `.omp/agents/*`
  templates and `.omp/RULES.md` alongside the skill, `PRODUCT-ADOPTION`
  amended first (contract-first, per `AGENTS.md` rule 4).
- `docs/delivery/seat-reliability.md` (a rung-4 `nother-guide` artifact)
  records model hangs and rate-limits per seat, appended same-day as they
  occur, starting with this pilot's own run.
- Rung 5 (a generated retro from `.orc` + git + `gh`) stays dormant with
  its named trigger: the first week of real M5 ledger data.

`TASK-M5-007` and `TASK-M5-008` are this phase's deliverables.

## The eight cards

1. `TASK-M5-001` — OMP capability test report (Phase 0).
2. `TASK-M5-002` — `PLAYBOOK-WATCHTOWER`/`PLAYBOOK-AGENT-CLI`/`AGENTS.md`/
   `.omp/RULES.md` rewrite (Phase 1).
3. `TASK-M5-003` — `docs/adapters/omp/*` + the `executor-identity/v1`
   OMP example (Phase 1).
4. `TASK-M5-004` — `.omp/agents/*` + `.omp/config.yml`, the pilot card
   (Phase 2; **delivered by this pilot PR**).
5. `TASK-M5-005` — `.omp/extensions/orc-seat.ts` hook guards + red test
   (Phase 2).
6. `TASK-M5-006` — `orc-ledger` skill v6 + `scripts/check.sh` loud line
   (Phases 2/3).
7. `TASK-M5-007` — `orc onboard` OMP scaffold + `PRODUCT-ADOPTION`
   amendment (Phase 4).
8. `TASK-M5-008` — `docs/delivery/seat-reliability.md` + the pilot
   write-up (Phase 4).

`TASK-M5-001` gates every later card: no agent definition or hook is
trusted until the capability it depends on has a recorded pass. Beyond
that gate, `TASK-M5-002`/`TASK-M5-003` (docs) and `TASK-M5-004` (the
pilot) can proceed in parallel; `TASK-M5-005` depends on `TASK-M5-004`
existing (the hook guards the ship/verify agents it defines);
`TASK-M5-006` depends on `TASK-M5-002` (the skill's seat section
references the rewritten playbooks); `TASK-M5-007` depends on
`TASK-M5-004` (it scaffolds the same agent shapes into adopting repos);
`TASK-M5-008` is last — its write-up needs the pilot's own run and at
least one subsequent card's delivery data.

## Acceptance

- `ADR-0007` is accepted and cites the capability-test results, the
  isolation-fork rationale (option B), the `T3`/`ADR-0005` no-pull-write
  rule, the `V7` model-family ruling, and every named nother-guide
  deviation with its trigger.
- `PLAYBOOK-WATCHTOWER` is ≤80 lines and no longer contains a
  §Model-and-effort-selection section or worktree/`watch_pr.py`
  Conventions lines.
- `PLAYBOOK-AGENT-CLI`'s OMP-specific mechanics live in
  `docs/adapters/omp/mapping.md`, not in the playbook itself.
- `.omp/agents/ship.md`, `.omp/agents/verify.md`, `.omp/agents/scout.md`,
  and `.omp/config.yml` exist, and ship/verify are on different model
  families.
- **Amended 2026-09-07** (operator ruling, following `task-m5-005-guards`
  run's six reproduced-in-system REJECTs at attempt 1 —
  `.orc/task-m5-005-guards/journal.jsonl` seq 16 — which established that
  an OMP `tool_call` hook receives only the bash command as a string,
  never argv or process identity, so a guard deciding by matching that
  text is defeated by shell escaping; originally this criterion required
  `.omp/extensions/orc-seat.ts` to prove four guards fire: yield-after-
  record, no `gh pr merge`, verify push/commit denial, and the ship
  worktree fence): `.omp/extensions/orc-seat.ts` exists with a red-then-
  green test proving the one guard that is structurally decidable in a
  `tool_call` hook — the ship worktree fence on `edit`/`write` paths —
  actually fires. The other three retreat to the rung that can hold them:
  no direct push to a shared branch is GitHub branch protection on
  `master`; record-before-yield is the orc ledger's own state machine;
  merge authority has no enforcement rung and remains seat-discipline
  prose plus after-the-fact ledger detection.
- `scripts/check.sh`'s final line is `check: green. NOT covered:
  <list|none>`.
- `orc onboard` installs the `.omp/agents/*` scaffold alongside the skill,
  and `PRODUCT-ADOPTION` documents the new rung.
- `docs/delivery/seat-reliability.md` exists and records this pilot's own
  run.
- `m5-omp-harness-pilot`'s ledger journal shows a `docs` work settled by
  the ship seat and (once assurance completes) an accepted verdict from
  the verify seat on a different model family — the acceptance evidence
  for the whole milestone.
