---
id: TASK-M4C-001
type: task-card
status: draft
authority: normative
description: Role guidance — HELD. The canonical `orc guide <role>` command is DORMANT (operator ruling 2026-08-30); role clarity is covered by the installed orc-ledger skill (durable principles) + the per-project mode declaration (TASK-M4A-004) + PLAYBOOK-AGENT-CLI (full reference).
implements: []
verifies: []
---

# TASK-M4C-001 — role guidance (`orc guide` HELD dormant)

Design source: `M4-COCKPIT-AND-CLARITY` Phase M4c.

## Operator ruling (2026-08-30): HOLD `orc guide`
The proposed `orc guide watchtower|shipper|verify` command is **not built
now** — dormant, not cancelled. The two-layer analysis (adversarial ethos
review) showed the command sits in a possibly-redundant middle:
- the **durable role PRINCIPLES** (seat separation, candidate-bound
  verdicts, observations-not-decisions) are already carried by the
  installed `orc-ledger` skill — reachable in any adopting repo;
- the **per-project PROCEDURE** (scripted vs adapter-driven; how a seat is
  filled here) is generated per-project by the mode declaration
  (`TASK-M4A-004`), which onboard writes into the agents-block;
- the **full normative reference** stays `PLAYBOOK-AGENT-CLI`.
Together these three cover role clarity without a new command. "Let the
per-project decide" the procedure; orc owns the principle (via the skill).

## Pull trigger (named)
Agents in adopting repos demonstrably getting seat discipline wrong DESPITE
the installed skill + the mode declaration — i.e. a proven gap the existing
three surfaces don't close. Until then, dormant.

## If pulled (recorded shape, from the ethos review)
`orc guide <role>` — packaged in `src/orc_werk/`, surfaced like
`orc config-schema`; each guide TWO-LAYER (durable principle cited to its
invariant + phase-scoped procedure + a transfer banner: procedure applies
while a human/agent fills the seat, transfers to whoever configures the
adapter when automated, principle is what the adapter must preserve);
`orc guide` output declares `authority: informative` + the normative source
IDs (so distilled process procedure is never mistaken for product doctrine).
The verify-seat guide is the net-new, highest-value piece.

## Out of scope while dormant
Building the command; any reference to `orc guide` in adopter-facing OUTPUT
(would dangle per #127 — the mode declaration and skill are the reachable
surfaces).
