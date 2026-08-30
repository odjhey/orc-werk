---
id: EXT-ASSURANCE-CONTEXT-V1-SEMANTICS
type: contract
status: current
authority: normative
version: 1
description: Behavioral semantics for assurance-context/v1.
---

# `assurance-context/v1` semantics

## What this extension is for

`assurance-context/v1` records which resolved immutable audit base the verifier claims it used. It makes a stale-base audit distinguishable from an audit against a current base without making base freshness part of the generic delivery state machine.

It does not answer what the assurance verdict was or which candidate the verdict binds to. Those remain canonical `PORT-ASSURANCE` and `FACT-ASSURE-SETTLED` fields, untouched by this extension (`EXT-003`, `EXT-007`).

## A verifier-attested observation, never kernel truth

The payload is a provenance observation: the verifier attests that it audited against `base.identity`. Tooling may compute and echo an identity, but the recorded value remains the verifier's claim. The kernel MUST NOT inspect repository/provider state to re-derive, validate, refresh, or otherwise trust it. Replay preserves the claim and remains deterministic.

Freshness policy is outside this extension. Extension-aware application policy MAY interpret the payload, but generic projection and transitions MUST be identical whether the extension is present, absent, unknown, or changed (`EXT-002`, `EXT-005`).

## Opaque fields carry no cross-adapter meaning

All fields are opaque strings. `identity` MUST be a resolved immutable value, never a bare mutable reference; it is not necessarily a Git sha. `ref`, `relation`, `derivation_ref`, and `trial_merge` have no generic enumerated meaning. This adapter-generic posture satisfies `INV-014`.

## Missing context is valid

The extension is optional. Absence does not invalidate an assurance settlement and the kernel MUST NOT fabricate a base. Git-backed verification seats SHOULD record it under `PLAYBOOK-AGENT-CLI`; that operator practice does not turn the extension into a core requirement.

## Inherited settlements preserve the original observation

When `SCN-009` verdict inheritance applies, the later candidate re-observation cites the original `FACT-ASSURE-SETTLED`; no second assurance Fact is created. The inherited settlement therefore carries the original Fact's `assurance-context/v1` base unchanged. The kernel MUST NOT re-derive a base at inheritance time.

## Canonical assurance remains canonical

This payload cannot override the canonical verdict or candidate fingerprint (`EXT-003`). It is never the sole carrier of a canonical verdict, fingerprint, evidence binding, or other information required by `PORT-ASSURANCE` (`EXT-007`). Unknown-extension consumers may ignore it with no canonical behavior change, while lossless transports preserve it unchanged (`EXT-005`, `CONF-EXT-003`).
