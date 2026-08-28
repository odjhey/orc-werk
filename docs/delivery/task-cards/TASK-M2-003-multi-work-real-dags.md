---
id: TASK-M2-003
type: task-card
status: current
authority: normative
description: A real multi-work DAG practice run through the acp adapter with real agents in the seats — exercises and populates the Beads mirror and the journal-reconstructable dependency-tree view, and harvests per-work cost/config findings, rather than building new capability for its own sake.
implements:
  - PORT-WORK-GRAPH
  - PORT-EXECUTION
verifies: []
---

# TASK-M2-003 — Multi-work real DAGs (practice run)

## Outcome (reframed — operator ruling, M2 reshape)

**This card is a practice run, not a build.** Its purpose is not primarily
to add new capability — `orc report`'s dependency-tree rendering (issue
#41) already reads only journal-recorded `deps` and per-work history, and
`PORT-WORK-GRAPH`/`PORT-EXECUTION` are otherwise unchanged by this card.
The point is to **drive one real multi-part deliverable as a real
dependency plan, with real agents (ship and verification seats,
`PLAYBOOK-AGENT-CLI`) in the seats**, through the acp `PORT-EXECUTION`
adapter, at minimum a diamond/fan-in shape matching `SCN-003`/DFS-003's
topology — and treat the run itself as an instrument, not just a
deliverable:

- **exercise and populate the Beads mirror** (`TASK-M2-006`) with a real
  multi-work topology, briefs, and status projection — the mirror's first
  real multi-work data, beyond whatever `TASK-M2-006` itself smoke-tests;
- **exercise `orc report`'s dependency-tree view** (issue #41) against
  real, not synthetic, journal-reconstructable topology — the precondition
  that view was originally gated on;
- **harvest findings**, not features: per-work config demand (does a real
  multi-work plan actually reveal heterogeneous risk/cost profiles between
  works — the evidence `TASK-M2-005`'s deferred gates are waiting on?) and
  real cost data (token/turn spend per Work, retry behavior under real
  agent variance) from actually running works with dependencies through a
  real adapter for the first time.

Little to build, much to learn: if the run surfaces a genuine gap (in
`PORT-WORK-GRAPH`, the report renderer, or the mirror), that gap is the
finding to record (`CLAUDE.md` rule 4/5) — not something to route around
mid-run to make the card look clean.

## In scope

- one real, dependent multi-work delivery run (this repo's own work, or a
  scripted fixture standing in if a real multi-work task is not yet
  available at dispatch time — decided at dispatch, not pre-committed
  here), driven by real ship/verification agents per
  `docs/playbooks/agent-cli-usage.md`;
- observing (not modifying) `orc report`'s existing dependency-tree
  rendering against this run's real journal data;
- observing (not modifying, beyond `TASK-M2-006`'s own scope) the Beads
  mirror populated by this run's real topology/briefs/status;
- recording harvested findings (per-work cost data, per-work config
  demand, any topology/report/mirror gaps found) as docs amendments or
  filed issues, per `DELIVERY-STANCE`'s dogfood-feedback-is-the-backlog
  principle;
- a golden scenario or dogfood corpus entry (`SCN-*` vs. `DFS-*` — decided
  at dispatch) covering the real-DAG-through-real-adapter shape.

## Out of scope

Policy changes (per-work `max_attempts`, retry classification) — those
remain `TASK-M2-005`, deferred out of M2 scope pending exactly the cost
evidence this card is positioned to harvest, not a precondition for this
card. Building new `PORT-WORK-GRAPH`/report/mirror capability beyond what
`TASK-M2-006` and issue #41 already define — a finding that argues for new
capability gets a docs amendment proposal, not an in-flight build inside
this practice run.

## Depends on

Benefits from, and is intended to sequence after, `TASK-M2-006` (Beads
mirror) landing first — there is nothing for this run to "exercise and
populate" in the mirror if the mirror does not yet exist. Not a hard
technical blocker (the DAG run and the report's dependency-tree view work
independently of the mirror), but the harvesting purpose above assumes the
mirror is live by the time this card's run happens.

## Acceptance

- a real multi-work DAG, driven by real ship/verification agents, completes
  through the acp adapter to a terminal state (accepted or blocked, per
  plan);
- `orc report` renders the DAG's dependency edges from journal data alone,
  satisfying issue #41's journal-reconstructable-topology precondition;
- the Beads mirror (`TASK-M2-006`) reflects this run's real topology and
  briefs, observed post-run;
- harvested findings (per-work cost data, per-work config demand signal for
  `TASK-M2-005`'s gates, any gaps found) are recorded as docs amendments or
  filed issues — not silently absorbed;
- `SCN-001` through `SCN-007` remain green (regression bar).
