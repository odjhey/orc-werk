---
id: ADAPTER-NO-MISTAKES
type: adapter
status: draft
authority: informative
description: Planned no-mistakes adapter for AssurancePort.
---

# no-mistakes adapter

Intended role: first real candidate-assurance provider behind `PORT-ASSURANCE`.

The adapter must normalize provider pipeline status into canonical assurance state/verdict and bind evidence to the exact canonical Candidate fingerprint.

If the provider can mutate/fix the candidate, the adapter must advertise `CAP-ASSURE-MAY-MUTATE-CANDIDATE` and surface the resulting final Candidate identity.
