---
id: EXT-EXECUTOR-IDENTITY-V1-SEMANTICS
type: contract
status: current
authority: normative
version: 1
description: Behavioral semantics for executor-identity/v1.
---

# `executor-identity/v1` semantics

## What this extension is for

`executor-identity/v1` records provenance about the executor occupying a ship or verify seat. It supports reconstruction of the no-self-assurance audit trail when an adapter does not already journal the seat's execution identity.

The `role` discriminator allows the same schema to describe both uses: a ship payload accompanies execution-attempt provenance, while a verify payload accompanies assurance provenance.

## Seat identity and issue #182

A `session_ref` can identify a shared orchestrating session without identifying an individual seat. As demonstrated by issue #182, ship and verify agents may be separate subagent threads within one session. Producers SHOULD therefore assign each seat a stable, distinct `seat_ref`; the two payloads are then distinguishable from journal history even when their `session_ref` values match.

`seat_ref` is optional for compatibility with payloads produced before that guidance was added. Missing or equal references do not let a consumer infer either seat separation or self-assurance.

## Observational provenance, never kernel policy

The payload is an executor's identity claim. It does not authenticate the executor and does not prove that ship and verify seats were independent. Audit or extension-aware application tooling MAY compare known payloads, but the generic kernel MUST NOT inspect or branch on any payload field (`EXT-002`).

Canonical projection and transitions MUST be identical whether the extension is present, absent, unknown, or changed (`EXT-005`). No-self-assurance remains process discipline rather than a kernel-enforced transition rule.

## Missing identity is valid

The extension is optional, and each of `model`, `session_ref`, and `seat_ref` is optional. Their absence does not invalidate an execution settlement or assurance verdict, and consumers MUST NOT fabricate missing values. When the extension is present, `role` is required so its seat use is unambiguous.

## Canonical records remain canonical

This payload cannot override a canonical execution outcome, candidate identity, assurance verdict, evidence reference, or decision identity (`EXT-003`, `EXT-007`). Unknown-extension consumers may ignore it with no canonical behavior change, while lossless transports preserve it unchanged (`EXT-005`, `CONF-EXT-003`).
