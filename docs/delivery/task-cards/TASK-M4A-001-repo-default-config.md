---
id: TASK-M4A-001
type: task-card
status: current
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
A repo sets its dispatch defaults once (a plain-JSON profile at .orc/profile.json, CLI-layer discovery only); precedence --config (deep-merged) > per-run persisted > .orc/profile.json > {}; onboard writes it idempotently. At each layer boundary, an explicitly changed adapter selector for `execution`, `candidate`, `assurance`, or `mirror` drops inherited keys exclusive to the previously selected adapter (#174), using the validator's adapter-conditional exclusivity definitions as the single source of truth; overriding-layer keys and inherited adapter-agnostic keys legal for the new adapter remain, and selecting the same adapter drops nothing. Reuses config.py _validate_* ; no core/app change. Design source: M4-COCKPIT-AND-CLARITY Phase M4a + open questions 1/2/5.
