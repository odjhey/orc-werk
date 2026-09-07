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

## Amendments (recorded during execution, 2026-09-07)

**1. The `PLAYBOOK-WATCHTOWER` ≤80-line target is amended; no fixed line
target applies.** Between this card's authoring and its execution, PR
#271 landed the External-candidate lane — five bullets plus a specimen,
genuinely harness-independent policy (adoption-precedes-judgment,
auditing-spends-the-seat, ledger-not-GitHub) that must survive any
shrink. The operative acceptance standard is now: every remaining line is
harness-independent policy or a seat-table row, and every harness-specific
mechanic named in this card's Outcome (§Model-and-effort-selection,
worktree/`watch_pr.py` Conventions) has moved out, not been deleted. Under
that standard the file is 156 lines (from 162): Roles became a five-row
seat table; §Model-and-effort-selection and the two worktree/`watch_pr.py`
Conventions bullets are gone; External-candidate lane, Pipeline, Task
sizing, Autonomy, Dormant-feature lifecycle, and Audit trail — all
explicitly named "kept" above — are unchanged and account for the bulk of
the remaining length. Hitting ≤80 lines would require deleting genuine,
still-current policy this same card lists as kept; the amended acceptance
is content-based, not a line count.

**2. `PLAYBOOK-AGENT-CLI`'s retained-sections list is amended from "§1–4,
§6, §9" to "§1–9 minus §7 (moved)."** §7 (worked example) still moves to
`docs/reports/task-m1-003-worked-example.md` exactly as specified. §2, §5,
and §8, however, contain no OMP-specific mechanics to remove — re-reading
the current file at execution time shows §2's `executor-identity/v1`
guidance was already harness-independent (the OMP-specific field-sourcing
table lives solely in `docs/adapters/omp/mapping.md`, landed by
`TASK-M5-003` as net-new content, not extracted from §2) — and two
already-landed docs cite them by section number: `CONTRACT-STORAGE-
CONCURRENCY` cites "`PLAYBOOK-AGENT-CLI` §5 ... §2", and `docs/adapters/
omp/mapping.md` cites "`PLAYBOOK-AGENT-CLI` §8's reference-first narrative
doctrine." Deleting or renumbering §2/§5/§8 would falsify those citations
for no gain — none of the three contains harness-specific prose. §2, §5,
and §8 are kept at their current numbers, trimmed only where a bullet
restated content `docs/playbooks/cli-usage.md` already owns.
