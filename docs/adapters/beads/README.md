---
id: ADAPTER-BEADS
type: adapter
status: current
authority: informative
description: Write-only Beads mirror adapter -- a projection consumer, not a PORT-WORK-GRAPH implementation.
---

# Beads adapter

`BeadsMirror` (`TASK-M2-006`, `src/orc_werk/adapters/beads/mirror.py`) is a
**write-only projection** of one `DeliveryRun`'s journal-derived run/work
state and per-work briefs into a shared, label-scoped `bd` (Beads)
database. `MemoryWorkGraph` + the journal remain the sole authority for
`PORT-WORK-GRAPH` semantics (readiness, claim, dependency-unlock,
acceptance) -- nothing this adapter writes to `bd` is ever read back to
drive a dispatch decision.

This is **not** the first real `PORT-WORK-GRAPH` implementation the
earlier draft of this document anticipated. Per the ratified posture on
issue #47 (2026-08-28, recorded in full in `docs/delivery/task-cards/
TASK-M2-006-beads-mirror.md`), `bd` becoming the live authority for
`PORT-WORK-GRAPH` ("authority graduation") is a fully-designed, dormant,
unbuilt future path, pulled only if this write-only mirror view earns it.

See `mapping.md` for the full write-only design (verb mapping, id/label
discipline, status/metadata vocabulary, degraded-mirror behavior,
sandbox/testing notes, the `1.2.2` version pin, and the Dolt boundary),
`capabilities.md` for why no `CAP-WORK-*` capability is advertised, and
`conformance.md` for this slice's verified `CONF-WORK-*` analogs.
