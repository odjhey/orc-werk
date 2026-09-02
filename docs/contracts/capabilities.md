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

## Capability-durability rule

An adapter MUST NOT claim a capability whose durability obligations are unmet.

This is a durability-honesty amendment: it strengthens `INV-013`, `EXT-004`, and `CONF-EXT-005` from "fail explicitly or expose a weaker capability" at the moment of use, to "do not advertise the stronger capability at all while its required durable evidence cannot actually be produced and persisted."

Concretely: `CAP-EXEC-RESUME-EXACT` requires durable `execution-session/v1` provenance for the session it would resume. An adapter MUST NOT advertise `CAP-EXEC-RESUME-EXACT` unless it durably persists the native session/resume identity that a resume request would need to reconstruct that exact session. An adapter that can resume a session operationally but does not durably persist that provenance MUST either advertise only `CAP-EXEC-RESUME-BEST-EFFORT`, or fail explicitly per `INV-013` and `PORT-EXEC-005` rather than claim `CAP-EXEC-RESUME-EXACT` on a best-effort footing.

Exemption: in-memory conformance fixtures and test doubles (the scripted reference adapters) are not durability-bearing providers. They exercise resume-strength gating (`INV-013`, `PORT-EXEC-005`) and reconstruct session identity deterministically in-process, satisfying the durability obligation trivially — there is no provider-native session that could outlive the process they run in. This rule binds real provider adapters, first exercised by the since-superseded `TASK-M1-005`.

The full ownership matrix and the capability -> durable-information -> owner -> contract -> conformance mapping this rule generalizes to is recorded in `CONTRACT-DURABILITY`, not restated here.
