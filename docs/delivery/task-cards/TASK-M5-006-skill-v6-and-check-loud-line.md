---
id: TASK-M5-006
type: task-card
status: current
authority: normative
description: orc-ledger skill v6 references the OMP agent roles in its seat section; scripts/check.sh gains the V5 loud-skip final line. Claude Code glue (.claude/skills symlink, CLAUDE.md) is kept, not deleted.
implements:
  - ADR-0007
verifies: []
---

# TASK-M5-006 — `orc-ledger` skill v6 and the `check.sh` loud-skip line

Design source: `ADR-0007`; `M5-OMP-FIRST-DELIVERY` Phases 2/3. Depends on
`TASK-M5-002` (the rewritten playbooks the skill's seat section points
at).

## The gap

The installed `orc-ledger` skill's §3 seat-discipline section still
describes seats in purely prose terms; it does not yet name
`.omp/agents/{scout,ship,verify}.md` as the OMP-native realization of the
roles it describes, so an OMP session onboarding via the skill has no
pointer from the skill to the agent definitions actually driving it.
Separately, `scripts/check.sh` runs `docs_check.py`, `compileall`, and
`unittest` but never prints a final loud-skip line — per `nother-guide`'s
`V5` ("a skipped check is loud and counted"), any exclusion in the gate
must be the last printed line of a green run, and today the gate is
silent about what it did and did not cover.

## Outcome

The `orc-ledger` skill is bumped to v6: its §3 seat section gains a
pointer from each role (scout/ship/verify) to its `.omp/agents/*.md`
definition, alongside the unchanged recording mechanics (§1–§9 stay
otherwise as-is; this is a pointer addition, not a rewrite of recording
semantics). `scripts/check.sh` gains a final line after its existing
three steps: `check: green. NOT covered: <list|none>`, printing `none`
when every declared check ran, or the exact list of skipped/narrowed
checks otherwise. `CHANGELOG.md` alongside the skill records the v6
bump and its rationale, per `PRODUCT-ADOPTION`'s versioned-skill
discipline.

**Claude Code glue is kept, not deleted**, per `ADR-0007`'s explicit
ruling: `.claude/skills` (the symlinked skill) and the root `CLAUDE.md`
remain in place unchanged — Claude Code is still a harness in use. This
card's scope is strictly the skill's content bump and the `check.sh`
line; it does not touch `.claude/` or `CLAUDE.md` at all.

## In scope

- `.agents/skills/orc-ledger/SKILL.md` — version bump to v6, §3 seat
  section gains the `.omp/agents/*.md` pointers.
- `.agents/skills/orc-ledger/CHANGELOG.md` — v6 entry.
- `scripts/check.sh` — appended final loud-skip line.
- Any test enforcing the skill-version-bump discipline
  (`PRODUCT-ADOPTION`) updated for v6.

## Out of scope

Deleting or modifying `.claude/skills` or `CLAUDE.md` (kept, per
`ADR-0007`). Any change to the skill's recording mechanics (§1–§9's
substantive rules are unchanged; only the seat-section pointers and the
version are new).

## Acceptance

- The installed skill's frontmatter names version 6, and its §3 (or
  equivalent seat section) names `.omp/agents/scout.md`,
  `.omp/agents/ship.md`, and `.omp/agents/verify.md` by path for their
  respective roles.
- `CHANGELOG.md` has a v6 entry explaining the OMP-pointer addition.
- `bash scripts/check.sh`'s last printed line matches
  `check: green. NOT covered: <list|none>` (with the literal word `none`
  when nothing was skipped, or a comma-separated list otherwise).
- `.claude/skills` and `CLAUDE.md` are byte-identical to their state
  before this card (unchanged, confirmed by `git diff` showing no hunk
  under either path from this card's commits).
