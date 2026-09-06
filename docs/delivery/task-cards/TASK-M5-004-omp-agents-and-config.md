---
id: TASK-M5-004
type: task-card
status: current
authority: normative
description: Author .omp/agents/{scout,ship,verify}.md and .omp/config.yml — the OMP-native seat definitions ADR-0007 ratifies. Delivered by this pilot PR itself.
implements:
  - ADR-0007
verifies: []
---

# TASK-M5-004 — `.omp/agents/*` + `.omp/config.yml`

Design source: `ADR-0007`; `M5-OMP-FIRST-DELIVERY` Phase 2 (the pilot
card). Depends on `TASK-M5-001`'s capability-test results for the
mechanisms it relies on (tool-restriction denial, strict output-schema
rejection).

**This card is delivered by this pilot PR itself.** The four files it
specifies — `.omp/agents/ship.md`, `.omp/agents/verify.md`,
`.omp/agents/scout.md`, and `.omp/config.yml` — are committed in this
same PR, copied unedited from the primary checkout where they were
authored ahead of this docs pass. Its status is `current` because the
deliverable already exists in this PR's tree, not merely specified.

## The gap

Before this card, no OMP agent definition exists for orc-werk's own
scout/ship/verify seats; every seat is an ad hoc session following prose.
`ADR-0007`'s current→target mapping requires these three roles to exist
as native OMP subagent definitions with frontmatter-declared model,
tools, and a strict result schema, plus one project-level `.omp/
config.yml` for shared task settings (effort, max runtime, recursion
depth).

## Outcome

- `.omp/agents/scout.md` — read-only recon; `tools: read, grep, glob,
  bash, hub, web_search`; `model: anthropic/claude-opus-5:high`; output
  schema requiring `{report, unverified, ambiguities, stale_after}`.
- `.omp/agents/ship.md` — the ship seat; `tools: read, edit, write, bash,
  grep, glob, hub`; `model: anthropic/claude-sonnet-5:medium`;
  `autoloadSkills: orc-ledger`; output schema requiring `{run_id,
  work_id, branch, pr, head_sha, gate, not_covered, ambiguities,
  recorded}`; body states the worktree-only boundary, never-merges rule,
  and the exact `orc record --outcome` invocation.
- `.omp/agents/verify.md` — the verify seat, on `openai-codex/
  gpt-5.6-sol:high` (a different model family from ship, per `ADR-0007`'s
  `V7` ruling); `tools: read, bash, grep, glob, hub`; output schema
  requiring `{run_id, work_id, verdict, derived_head_sha,
  evidence_grade, findings, ambiguities, recorded}`; body states the
  derive-your-own-sha rule, the default-to-REJECT-when-blocked rule, and
  the exact `orc record --verdict` invocation.
- `.omp/config.yml` — `task.enableEffort: true`, `task.maxRuntimeMs` set
  to a bounded wall-clock ceiling, and `task.maxRecursionDepth: 1`
  (watchtower → seat only; seats never spawn further seats).

## In scope

The four files above, at the exact paths named. Ensuring `.omp/` is not
excluded by `.gitignore` (it is not, as of this PR).

## Out of scope

`.omp/agents/dogfood.md` (an existing role not part of this migration's
seat table). `.omp/extensions/orc-seat.ts` (`TASK-M5-005`, depends on
these agent definitions existing first). The `orc onboard` scaffold step
that installs this same shape into adopting repos (`TASK-M5-007`).

## Acceptance

- `.omp/agents/scout.md`, `.omp/agents/ship.md`, `.omp/agents/verify.md`,
  and `.omp/config.yml` exist, committed to git (not merely present
  untracked in a working directory).
- `ship.md`'s `model:` and `verify.md`'s `model:` name different provider
  families (e.g. `anthropic/*` vs `openai-codex/*`), satisfying `ADR-0007`'s
  `V7` ruling.
- Each agent's `output` schema is `type: object` with a non-empty
  `required` array naming every field its body's protocol section
  promises to fill in.
- `ship.md`'s body states it never merges and never records an assurance
  verdict; `verify.md`'s body states it never pushes, commits, or
  comments.
- `git check-ignore .omp/agents/ship.md .omp/config.yml` reports neither
  path as ignored.
