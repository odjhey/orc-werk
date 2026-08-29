---
id: TASK-M4A-001
type: task-card
status: draft
authority: normative
description: Repo-default config (named profile) — set execution/candidate/assurance/mirror defaults once per repo; --config deep-merges over it.
implements: []
verifies: []
---

# TASK-M4A-001

Design source: `M4-COCKPIT-AND-CLARITY` Phase M4A. Details firm
up at dispatch (the established convention). Draft until the M4 milestone
is operator-approved.

## Outcome / scope
A repo sets its dispatch defaults once (a plain-JSON profile, CLI-layer discovery only); precedence --config > per-run persisted > repo-default profile > {}; onboard writes it idempotently. Reuses config.py _validate_* ; no core/app change. Design source: M4-COCKPIT-AND-CLARITY Phase M4a + open questions 1/2/5.
