---
id: TASK-M4A-002
type: task-card
status: current
authority: normative
description: project:<name> label on mirrored bd issues so the shared board slices by project.
implements: []
verifies: []
---

# TASK-M4A-002

Design source: `M4-COCKPIT-AND-CLARITY` Phase M4A. Details firm
up at dispatch (the established convention). Draft until the M4 milestone
is operator-approved.

## Outcome / scope
Optional mirror.project config key plumbed to BeadsMirror; a second --label project:<name> pair emitted at _create_work (upsert re-labels on next dispatch, no backfill); ADAPTER-BEADS-MAPPING amended; adapter stays write-only. Design source: M4-COCKPIT-AND-CLARITY Phase M4a.
