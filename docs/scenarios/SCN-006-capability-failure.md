---
id: SCN-006
type: scenario
status: current
authority: normative
description: Required stronger capability fails explicitly when provider only offers weaker semantics.
---

# SCN-006 — Unsupported capability

## Given
- Policy requires exact resume.
- The selected Execution adapter advertises only best-effort resume.

## Then
- The kernel does not silently start a fresh conversation.
- The operation fails with `ERR-UNSUPPORTED-CAPABILITY` or policy selects another provider.
- The Decision and failure are journaled.

Verifies: `INV-013`.
