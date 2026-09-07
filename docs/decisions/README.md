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
- [ADR-0006 — Bounded assurance re-request on `inconclusive`](ADR-0006-bounded-assurance-rerequest.md)
- [ADR-0007 — OMP is the primary delivery harness](ADR-0007-omp-primary-harness.md)

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

An ADR whose ruling still stands but whose *expression* needs correction
(the decision is not reopened or reversed, so `Supersedes`/`Superseded by`
does not apply) is amended in place: append a dated `## Amendment (<date>,
<trigger>): <what changed>` section after `Related contract IDs`, state
what changed and why with evidence, and leave the original ruling above it
untouched — a historical record of what was decided and why, not rewritten
to read as though it always said the amended text. Precedent:
`docs/scenarios/SCN-008-replay-budget.md`'s `## Amendment (issue #240): ...`
section for a scenario; `ADR-0007`'s `## Amendment (2026-09-07, ...)` for
an ADR.

Do not require implementers to read ADR history to discover current behavior. Promote the lasting semantic into the appropriate product principle, invariant, domain definition, port contract, or registered extension contract.
