---
id: ADAPTER-BEADS-CAPABILITIES
type: adapter-capabilities
status: current
authority: informative
description: Beads mirror (BeadsMirror) capability status -- write-only, no PORT-WORK-GRAPH capabilities advertised.
---

# Beads capabilities

`BeadsMirror` (`TASK-M2-006`) is a write-only observer, not a
`PORT-WORK-GRAPH` implementation. It advertises **no** `CAP-WORK-*`
capability -- it has no `capabilities()` method at all, since it
implements no `WorkGraphPort` interface for such a capability to describe.

| Capability | Advertised | Rationale |
|---|---|---|
| `CAP-WORK-ATOMIC-CLAIM` | No -- not applicable | This adapter never claims Work; it only echoes the kernel's own already-recorded claim (`claim_ref`) as metadata, write-only. |
| `CAP-WORK-GRAPH-PATCH` | No -- not applicable | This adapter never patches the run's own topology; `PORT-WORK-001`'s plan (created once per `DeliveryRun`, `INV-020`'s `FX-CREATE-WORK` reduced key form) is mirrored as-is. |
| `CAP-WORK-EXTERNAL-GATES` | No -- not applicable | Out of scope; not part of this slice (`docs/delivery/task-cards/TASK-M2-006-beads-mirror.md`'s "Out of scope" section). |

Authority graduation (`bd`-native ready/claim/dependency logic driving
real dispatch decisions, which WOULD require some of the above) is
dormant on issue #47 -- not built, not advertised, per the task card's
"Slice boundary" section. See `docs/adapters/beads/mapping.md` for the
full write-only design.
