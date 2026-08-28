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

`CAP-ASSURE-STRUCTURED-FINDINGS` means a provider can expose one or more declared structured-finding extension schemas. The provider MUST also advertise the exact extension identifiers it supports, for example `review-findings/v1`; the generic capability alone does not imply support for every finding schema.

## Extension negotiation

Extensions follow `CONTRACT-EXTENSIONS`.

A provider MAY advertise supported extension identifiers in adapter capability metadata. Policy that requires a specialized extension MUST name the exact extension/version it requires.

A provider that supports canonical assurance but not a required extension remains a valid generic assurance provider; it simply cannot satisfy that extension-specific policy requirement.

A provider MAY expose additional capabilities in adapter-specific metadata, but core policy may only rely on canonical capabilities and registered extension identifiers it understands.
