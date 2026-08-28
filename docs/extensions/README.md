---
id: EXTENSION-INDEX
type: index
status: current
authority: normative
description: Registry and rules for optional Orc Werk extensions.
---

# Extensions

Extensions carry specialized semantics that are useful to particular providers or workflows but are not required by the generic Orc Werk delivery state machine.

All extensions MUST satisfy `CONTRACT-EXTENSIONS`.

## Registered extensions

- `EXT-REVIEW-FINDINGS-V1` — structured code-review findings under `review-findings/v1`

## Rules

- Core contracts remain authoritative over extension payloads.
- Extension identifiers are stable and versioned.
- Extension payloads are portable JSON-compatible data.
- Unknown extensions do not change canonical orchestration behavior.
- Policy may explicitly require a known extension capability.
