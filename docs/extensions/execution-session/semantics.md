---
id: EXT-EXECUTION-SESSION-V1-SEMANTICS
type: contract
status: current
authority: normative
version: 1
description: Behavioral semantics for execution-session/v1.
---

# `execution-session/v1` semantics

## What this extension is for

`execution-session/v1` exists so that a provider's exact native session identity — and the reference material an operator or adapter needs to resume, inspect, or debug it — has a durable, portable home. It answers: **if the orchestrator process restarts, or the run is inspected later, what does the adapter need in order to reconnect to (or reason about) the same underlying provider session?**

It does not answer, and MUST NOT be used to answer, what the execution's outcome was — that remains `PORT-EXEC-002`'s canonical `state`/`outcome` fields, untouched by this extension (`EXT-003`).

## Relationship to `resume` capability requests

`PORT-EXEC-005` resume requests carry a `capability` field valued `CAP-EXEC-RESUME-BEST-EFFORT` or `CAP-EXEC-RESUME-EXACT` — that is the caller's requested resume *strength*. `execution-session/v1`'s `resume.strength` is the durable record of what strength the adapter can actually honor for *this specific session*, persisted at the time the session was observed.

The two are checked against each other, not merged: a resume request for `CAP-EXEC-RESUME-EXACT` against a session whose durable `execution-session/v1.resume.strength` is `"best-effort"` (or whose provenance is missing entirely) MUST fail per `INV-013` rather than silently resume at reduced strength. An adapter MUST NOT paper over that gap by upgrading a stored `"best-effort"` record to satisfy an `"exact"` request, or by fabricating provenance it did not actually durably persist.

## Opaque fields carry no cross-provider meaning

`provider`, `native_session_id`, and the fields inside `profile` are opaque per the schema's opaque-strings rule. Two payloads with the same `provider` string are only comparable because one specific adapter chose that string consistently — Orc Werk core and cross-provider policy MUST NOT infer anything about provider capability, cost, or behavior from the string value itself. Only adapter-local or explicitly provider-aware policy code may interpret it (`EXT-002`).

This is a deliberate consequence of `INV-014`: the alternative (an enumerated `provider` field) would require this contract to keep a live registry of provider names, embedding provider vocabulary into a shared contract that every adapter depends on.

## `transcript_ref` is never inlined

`transcript_ref` names a location; it does not carry the transcript. This mirrors `PORT-JOURNAL`'s explicit refusal to become a general artifact or transcript store. A component that persists `execution-session/v1` (for example, a durable `JournalPort` adapter persisting an execution observation's `extensions`) MUST persist the reference string unchanged and MUST NOT dereference, fetch, or inline the transcript content as part of that persistence. Resolving the reference into actual transcript content is entirely the concern of whatever provider-specific store the reference names, outside any Orc Werk contract.

The same rule applies to any other field this schema might add later that names, rather than carries, artifact content.

## Profile fields describe reproducibility inputs, not policy

`profile.model`, `profile.effort`, `profile.permission_mode`, and `profile.fast` record what configuration produced this session, for reproducibility and operator inspection. They are historical record of what happened, not a live policy input — Orc Werk core and cross-provider policy MUST NOT branch dispatch behavior on the contents of a *past* session's `profile`. A policy that wants to choose model/effort/permission mode for a *new* dispatch does so through adapter-specific request parameters, not by reading this extension.

## Missing provenance is not an error, but it is not exact-resume-capable

An execution observation that carries no `execution-session/v1` extension at all is a valid observation — the extension is optional per `CONTRACT-EXTENSIONS`'s selection rule. What it cannot be is the basis for a `CAP-EXEC-RESUME-EXACT` claim: per the `CONTRACT-CAPABILITIES` capability-durability amendment, an adapter that never produces durable `execution-session/v1` provenance for its sessions MUST NOT advertise `CAP-EXEC-RESUME-EXACT`, regardless of whether the underlying provider technically supports exact resume in-process.

## Dispatcher provenance is deliberately absent

Watchtower/preset/policy attribution answers a different question — *who or what dispatched this execution and under what orchestration policy* — from session provenance's *what native session is this*. Conflating the two would make `execution-session/v1` do double duty as both an Execution-adapter contract and an orchestration-adapter contract, owned by different concerns. The watchtower assessment on issue #12 is explicit that this splits into its own future extension; see `CONTRACT-DURABILITY`'s ownership matrix for its current (planned, unregistered) status.
