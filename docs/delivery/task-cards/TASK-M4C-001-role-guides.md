---
id: TASK-M4C-001
type: task-card
status: current
authority: normative
description: Three crisp per-role operating guides (watchtower, shipper/work-doer, verify-seat) surfaced via `orc guide <role>`; two-layer structure — a DURABLE role principle and a PHASE-SCOPED manual procedure that transfers to adapters as seats automate.
implements: []
verifies: []
---

# TASK-M4C-001 — role guides via `orc guide <role>`

Design source: `M4-COCKPIT-AND-CLARITY` Phase M4c + Ruling 4. Details firm
up at dispatch.

## Mechanism (Ruling 4, unchanged)
Guides are PACKAGED in `src/orc_werk/` (canonical origin, like the skill)
and surfaced via a new `orc guide watchtower|shipper|verify` command (the
`orc config-schema` pattern): reachable in any repo by any agent that can
run a CLI (harness-agnostic, no dangling path — the #127 lesson). The dense
playbooks stay the full normative reference; the skill/agents-block cites
the runnable `orc guide <role>` command.

## Structural requirement (adversarial ethos review, 2026-08-30 — amended before build)
Verdict: the operator's "these are incremental-only" hypothesis is
directionally right but too blunt. Each role guide fuses two layers, and
only one is phase-scoped — so the guides MUST be authored two-layer, not as
flat how-tos (a flat how-to produces anti-automation rot, contradicting
`PRODUCT-THESIS`: "full autonomy is the top of the ladder, not the entry
fee"):

1. **Durable role PRINCIPLE** — seat separation / no self-assurance
   (`P-003`, `INV-003`, `INV-011`), candidate-bound verdicts (`P-004`,
   `INV-007`/`INV-008`), independent identity derivation → `ERR-CONFLICT`
   (`INV-006`), externally-resolvable candidates (`INV-005`). Cited to the
   normative ID. This survives automation and is the highest-value content;
   it is NOT scoped away.
2. **Phase-scoped manual PROCEDURE** — the by-hand seat operation (run
   `orc guide`, edit the config `attempts` entry, re-dispatch, exit 3,
   `PLAYBOOK-AGENT-CLI`). This applies WHILE a human/agent fills the seat by
   hand; it obsoletes as an execution/assurance adapter fills the seat.

Each guide carries a **transfer banner** (not a retire banner): "principles
are permanent; the procedure applies while a human/agent fills this seat by
hand; when an execution/assurance adapter fills it, the procedure applies to
whoever configures that adapter and the principle is what the adapter must
preserve." Calibrate per guide — the WATCHTOWER (coordinating) seat is
mostly durable (the thesis stages only exec/assurance seats as automatable);
the SHIPPER and VERIFY guides are mostly procedure over a durable spine, so
their transfer banners lead.

`orc guide` output declares its own phase-scope + `authority: informative`
+ the normative source IDs — so a product CLI command's distilled process
procedure is never mistaken for product-normative doctrine.

## Out of scope
review-findings/v1 or any contract change; automation to replace CLI
invocation (M4 hard boundary). The dense playbooks are unchanged (they stay
the normative reference).

## Acceptance
- `orc guide watchtower|shipper|verify` prints each guide, two-layer
  (durable principle cited to its invariant + phase-scoped procedure +
  transfer banner), with the informative-authority + source-ID header.
- A fresh agent in an adopting repo reaches its role's guide by the runnable
  command (no dangling path).
- The verify-seat guide (net-new — that seat is a role documented nowhere
  today) exists and leads with its durable principle.
- No flat how-to that would read as prescribing manual operation forever.
