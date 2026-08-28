---
id: TASK-M2-003
type: task-card
status: current
authority: normative
description: Real dependent deliveries through the acp adapter, plus the journal-reconstructable dependency-tree view in orc report (issue #41).
implements:
  - PORT-WORK-GRAPH
  - PORT-EXECUTION
verifies: []
---

# TASK-M2-003 — Multi-work real DAGs

## Outcome

Drive a real, dependent multi-work plan (at minimum a diamond/fan-in shape
matching `SCN-003`/DFS-003's topology) to terminal state through the acp
`PORT-EXECUTION` adapter, with real candidates on every node. Land issue
#41 (report dependency-tree view) against this real topology, now that a
real multi-work acp-driven run makes the journal-reconstructable-topology
precondition exercisable end-to-end rather than only against a synthetic
fixture.

## In scope

- a real multi-work delivery run (this repo's own work, or a scripted
  fixture standing in if a real multi-work task is not yet available at
  dispatch time — decided at dispatch, not pre-committed here);
- `orc report`'s dependency-tree rendering, reading only journal-recorded
  `deps` and per-work history (no new canonical shape);
- a golden scenario or dogfood corpus entry (`SCN-*` vs. `DFS-*` — decided
  at dispatch) covering the real-DAG-through-real-adapter shape.

## Out of scope

Policy changes (per-work `max_attempts`, retry classification) — those are
`TASK-M2-005`, gated separately and not a precondition for this card.

## Acceptance

- a real multi-work DAG completes through the acp adapter to a terminal
  state (accepted or blocked, per plan);
- `orc report` renders the DAG's dependency edges from journal data alone,
  satisfying issue #41's journal-reconstructable-topology precondition;
- `SCN-001` through `SCN-007` remain green (regression bar).
