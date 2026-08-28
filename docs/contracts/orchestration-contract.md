---
id: ORCHESTRATION-CONTRACT
type: contract
status: current
authority: normative
description: Constitutional contract for the orchestration kernel.
---

# Orchestration contract

This document defines the stable constitutional boundary of the kernel.

1. Logical work identity is independent from execution identity (`INV-001`).
2. Execution completion is independent from work acceptance (`INV-003`).
3. Assurance is candidate-bound (`INV-005` through `INV-010`).
4. Repeated work attempts preserve history (`INV-004`, `INV-018`).
5. Read/attention/acceptance are separate concepts (`INV-017`).
6. Provider capabilities are explicit and stronger semantics are never silently approximated (`INV-013`).
7. Provider-specific vocabulary does not define the core (`INV-014`).
8. Decisions are attributable and based on recorded facts (`INV-011`, `INV-012`).
9. External mutations occur through effects and ports, not from pure core code (`INV-020`).
10. The pure core MUST be testable without integration dependencies (`P-006`).
