---
id: ADAPTER-BEADS-MAPPING
type: adapter-mapping
status: draft
authority: informative
description: Draft Beads-to-WorkGraphPort mapping.
---

# Beads mapping

| Canonical | Expected provider mapping | Status |
|---|---|---|
| Work | Beads work item/bead | verify |
| `PORT-WORK-003 ready` | provider readiness frontier | verify |
| `PORT-WORK-004 claim` | provider claim/assignment | verify |
| dependency topology | provider dependencies | verify |
| completion unlock | provider dependency resolution | verify |

## Required investigation

- prove `CONF-WORK-001` through `CONF-WORK-004` where capabilities are advertised;
- record graph-patch and external-gate support as capabilities, not assumptions;
- define idempotency/error translations.
