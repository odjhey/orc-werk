---
id: TASK-M5-002
type: task-card
status: current
authority: normative
description: Shrink PLAYBOOK-WATCHTOWER to a seat table and its harness-independent policy, move PLAYBOOK-AGENT-CLI's OMP-specific mechanics out to docs/adapters/omp/, absorb nother-guide's ten hard rules into AGENTS.md, and author the sticky .omp/RULES.md.
implements:
  - ADR-0007
verifies: []
---

# TASK-M5-002 — Playbook rewrite: `PLAYBOOK-WATCHTOWER`, `PLAYBOOK-AGENT-CLI`, `AGENTS.md`, `.omp/RULES.md`

Design source: `ADR-0007`; `M5-OMP-FIRST-DELIVERY` Phase 1.

## The gap

`PLAYBOOK-WATCHTOWER` (151 lines) and `PLAYBOOK-AGENT-CLI` (163 lines)
carry both harness-independent seat policy (roles, effect boundaries,
model families, no-self-assurance, recording mechanics) and prose that
`ADR-0007` moves to a stronger rung: model/effort selection per seat
(→ agent `model:` frontmatter), worktree/`watch_pr.py` mechanics (→ agent
bodies and the hook), and OMP-specific field mappings for
`executor-identity/v1` (→ `docs/adapters/omp/mapping.md`, provider
vocabulary that does not belong in a generic playbook). `AGENTS.md` also
does not yet reflect the ten hard rules `nother-guide`'s adoption ladder
names for rung 0, several of which orc-werk already practices without
stating them (refusal is a signal, skipped-check-is-loud, record before
destroy, proceed on the reversible, an Ambiguities section required).

## Outcome

`PLAYBOOK-WATCHTOWER` is ≤80 lines: Roles collapses into a seat table
(role · effects boundary · model family · effort · result schema ·
observed failures); Pipeline, Sizing, Autonomy, Dormant lifecycle, and
Audit trail are kept; §Model and effort selection and the
worktree/`watch_pr.py` Conventions lines are deleted (superseded by agent
frontmatter and the hook). `PLAYBOOK-AGENT-CLI` keeps §1–4 (observations
only, no self-assurance, derive identity, `inconclusive` semantics), §6
(multi-work etiquette), and §9 (fresh-session orientation); its
OMP-specific mechanics move to `docs/adapters/omp/mapping.md`
(`TASK-M5-003`); its §7 worked example moves to `docs/reports/` as
historical reference (`T6`: appended, not deleted). `AGENTS.md` merges
`nother-guide`'s ten hard rules into its existing twelve, deduplicated,
and its "Delivery workflow" section is rewritten in OMP terms. `.omp/
RULES.md` (sticky, ≤10 lines) states the seat invariants that must survive
context compaction in a long watchtower session.

## In scope

- `docs/delivery/watchtower-operations.md` (`PLAYBOOK-WATCHTOWER`):
  rewrite to ≤80 lines per the shape above.
- `docs/playbooks/agent-cli-usage.md` (`PLAYBOOK-AGENT-CLI`): trim to
  §1–4, §6, §9; move OMP mechanics out; move §7 to `docs/reports/`.
- `AGENTS.md`: merge the ten hard rules (deduped against the existing
  twelve); rewrite "Delivery workflow" in OMP terms.
- `.omp/RULES.md`: new file, ≤10 lines, the seat invariants that must
  survive compaction.

## Out of scope

Deleting `.claude/skills` or `CLAUDE.md` (kept per `ADR-0007`'s Claude
Code glue ruling). Writing `docs/adapters/omp/*` itself (`TASK-M5-003`,
parallel). Any change to `src/` or `tests/`.

## Acceptance

- `PLAYBOOK-WATCHTOWER` is ≤80 lines and contains a seat table (role,
  effects boundary, model family, effort, result schema, observed
  failures) in place of the former §Roles/§Model-and-effort-selection
  sections; the worktree/`watch_pr.py` Conventions lines are absent.
- `PLAYBOOK-AGENT-CLI` contains only §1–4, §6, and §9 content plus any
  section headers needed for navigation; no OMP-specific field-mapping
  prose remains in it.
- `docs/adapters/omp/mapping.md` (once `TASK-M5-003` lands) is the sole
  home of the OMP-specific `executor-identity/v1` field mapping formerly
  in `PLAYBOOK-AGENT-CLI`.
- `AGENTS.md` states all ten `nother-guide` hard rules (by rule content,
  deduplicated against the existing twelve) and its "Delivery workflow"
  section names the OMP agents and hook by path.
- `.omp/RULES.md` exists, is ≤10 lines, and states the seat invariants
  (no self-assurance, verify cannot push/commit/comment, record before
  yield, ship worktree-only, one dispatcher per run).
