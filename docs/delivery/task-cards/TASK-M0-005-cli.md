---
id: TASK-M0-005
type: task-card
status: current
authority: normative
description: Deliver the first CLI over the pure orchestration kernel.
implements:
  - M-000
verifies:
  - SCN-001
  - SCN-002
  - SCN-003
  - SCN-004
  - SCN-005
  - SCN-006
---

# TASK-M0-005 — CLI and golden scenarios

## Outcome

Expose provider-free commands sufficient to dispatch an intent and inspect canonical progress/history.

Suggested minimum:

```text
orc dispatch "<intent>"
orc status [run]
orc history [run]
```

`watch` may be added if it remains a projection of canonical history rather than direct provider inspection.

## Acceptance

All six golden scenarios pass through the application/CLI surface using memory/scripted adapters.
