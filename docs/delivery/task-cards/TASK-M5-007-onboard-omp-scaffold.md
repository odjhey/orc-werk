---
id: TASK-M5-007
type: task-card
status: current
authority: normative
description: orc onboard installs the .omp/agents/* + .omp/RULES.md scaffold alongside the skill in adopting repositories; PRODUCT-ADOPTION is amended first to name the new rung.
implements:
  - PRODUCT-ADOPTION
  - ADR-0007
verifies: []
---

# TASK-M5-007 — `orc onboard` OMP scaffold + `PRODUCT-ADOPTION` amendment

Design source: `ADR-0007`; `M5-OMP-FIRST-DELIVERY` Phase 4. Depends on
`TASK-M5-004` (the agent-definition shape it scaffolds) and
`TASK-M5-002` (`.omp/RULES.md`'s content).

## The gap

`orc onboard` today installs the `orc-ledger` skill and a mode-declaring
agents-block (`TASK-M4A-004`), but has no step that installs OMP agent
definitions for a repo adopting the OMP-first pattern this milestone
ratifies for orc-werk itself. An adopting repo wanting the same
scout/ship/verify seat shape must currently hand-copy the files this
pilot PR commits; `PRODUCT-ADOPTION` also does not yet document this as
an adoption rung, so the amendment must land before the scaffold code
does (contract-first, `AGENTS.md` rule 4).

## Outcome

`PRODUCT-ADOPTION` is amended first: a new row (or an amendment to the
existing "Multi-agent ledger" rung) names the OMP-native seat pattern —
`.omp/agents/{scout,ship,verify}.md`, `.omp/config.yml`, `.omp/RULES.md`
— as an available adoption shape, distinct from the harness-agnostic
`PLAYBOOK-AGENT-CLI` rung it sits above. `orc onboard` then gains a step
(behind an explicit flag, e.g. `--omp`, or triggered by an existing
`.omp/` directory, mirroring the existing never-clobber/`--force`
discipline the skill and agents-block installers already use) that writes
template copies of `.omp/agents/*.md`, `.omp/config.yml`, and
`.omp/RULES.md` into the adopting repo, sourced from this installed
package — one canonical origin, matching the skill's own
installed-from-package discipline.

## In scope

- `PRODUCT-ADOPTION` amendment naming the OMP scaffold rung.
- `orc onboard`'s new scaffold step: idempotent, never-clobber unless
  `--force`, pure scaffolding (never touches a journal).
- Tests: a fresh repo → the scaffold installs all four files; a repo with
  an operator-modified copy → preserved unless `--force`; a repo without
  the trigger (`--omp` absent, no existing `.omp/`) → scaffold not
  installed, existing behavior unchanged.

## Out of scope

Any change to `PORT-EXECUTION`/`PORT-ASSURANCE`/`PORT-WORK-GRAPH`/
`PORT-JOURNAL`/`PORT-CANDIDATE` adapters. Templating per-repo model
choices beyond the defaults `TASK-M5-004` ships (an adopting repo edits
its own copy after scaffolding, same as the skill's own
operator-modification model).

## Acceptance

- `PRODUCT-ADOPTION` names the OMP scaffold as an adoption rung, citing
  `TASK-M5-004` and `ADR-0007`, before the scaffold code exists in the
  same PR that adds it (or an earlier one).
- `orc onboard` (with its trigger satisfied) writes `.omp/agents/
  scout.md`, `.omp/agents/ship.md`, `.omp/agents/verify.md`,
  `.omp/config.yml`, and `.omp/RULES.md` into a repo that lacked them.
- Re-running `orc onboard` against an operator-modified copy of any of
  those files leaves it untouched unless `--force` is passed.
- `orc onboard` against a repo with the trigger absent installs none of
  the five files, leaving today's onboarding behavior (skill +
  agents-block only) unchanged.
