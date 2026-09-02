---
id: ADR-INDEX
type: index
status: current
authority: informative
description: Architecture decision record convention.
---

# Architecture decisions

ADRs explain why decisions were made. Current contracts define what is authoritative now.

## Current decisions

- [ADR-0001 — Pure core](ADR-0001-pure-core.md)
- [ADR-0002 — Candidate-bound assurance](ADR-0002-candidate-bound-assurance.md)
- [ADR-0003 — Python-first reference implementation](ADR-0003-python-reference-implementation.md)
- [ADR-0004 — Versioned extensions for specialized semantics](ADR-0004-versioned-extensions.md)
- [ADR-0005 — Push recording, not pull observation](ADR-0005-push-recording-not-pull-observation.md)

## Convention

```text
ADR-XXXX — Title
Status: proposed | accepted | rejected | superseded
Context
Options
Decision
Consequences
Supersedes / Superseded by
Related contract IDs
```

Do not require implementers to read ADR history to discover current behavior. Promote the lasting semantic into the appropriate product principle, invariant, domain definition, port contract, or registered extension contract.
