---
id: CONTRACT-CAPABILITIES
type: contract
status: current
authority: normative
description: Capability negotiation contract.
---

# Capabilities

Capabilities describe semantic guarantees, not marketing features.

## Work graph capabilities

- `CAP-WORK-ATOMIC-CLAIM`
- `CAP-WORK-GRAPH-PATCH`
- `CAP-WORK-EXTERNAL-GATES`

## Execution capabilities

- `CAP-EXEC-SEND`
- `CAP-EXEC-CANCEL`
- `CAP-EXEC-RESUME-BEST-EFFORT`
- `CAP-EXEC-RESUME-EXACT`
- `CAP-EXEC-STRUCTURED-LIFECYCLE`

## Assurance capabilities

- `CAP-ASSURE-CANDIDATE-BOUND`
- `CAP-ASSURE-STRUCTURED-VERDICT`
- `CAP-ASSURE-STRUCTURED-FINDINGS`
- `CAP-ASSURE-MAY-MUTATE-CANDIDATE`

A provider MAY expose additional capabilities in adapter-specific metadata, but core policy may only rely on canonical capabilities it understands.
