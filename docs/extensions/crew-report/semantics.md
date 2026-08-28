---
id: EXT-CREW-REPORT-V1-SEMANTICS
type: contract
status: current
authority: normative
version: 1
description: Behavioral semantics for crew-report/v1.
---

# `crew-report/v1` semantics

## What this extension is for

`crew-report/v1` exists so that a provider's own turn-by-turn narration of its progress — what Rozoro called the handoff/report history — has a durable, portable home, without that narration ever being confused for canonical orchestration truth. It answers: **what does this execution's producer currently believe about its own progress, on this turn?** It does not answer, and MUST NOT be used to answer, what the execution's canonical outcome was (`PORT-EXEC-002`'s `state`/`outcome`) or whether the Work is accepted (`INV-003`).

## `claimed_verdict` is a claim, never a fact

A `claimed_verdict` of any value — including `"done"` — is exactly that: a claim by the report's producer. `INV-003` ("done is a claim, not a fact") governs it directly. Core orchestration logic MUST NOT branch on `claimed_verdict`; `CONF-EXT-006` requires that core reducer/state-machine tests prove changing a `crew-report/v1` payload while holding canonical facts constant produces no change in canonical transitions or decisions.

This is a stronger and more literal instance of the general extension rule (`EXT-002`, `EXT-003`) than most extensions need to satisfy, precisely because `claimed_verdict`'s vocabulary (`done`, `failed`, `blocked`, ...) is suggestively close to canonical execution/assurance vocabulary. The field name (`claimed_verdict`, not `verdict`) and this semantics rule are two independent layers of the same immunization — see `schema.md`'s "`claimed_verdict`, not `verdict`" section for the naming rationale.

## Relationship to canonical settlement and assurance

A crew report and a canonical execution settlement (`FACT-EXEC-SETTLED`) answer different questions asked at different times by different parties:

- a crew report is the producer's own self-assessment, available as soon as the producer chooses to emit one, mid-attempt or at any turn;
- canonical settlement is the orchestrator's recorded observation of an execution's outcome, and canonical assurance (`PORT-ASSURANCE`) is an independent verdict on the resulting candidate.

A `claimed_verdict = "done"` report MAY precede, coincide with, or (if the producer is wrong, lying, or simply premature) never be followed by an actual `FACT-EXEC-SETTLED(completed)` and an accepting assurance verdict. Nothing in this extension requires or implies any ordering or consistency relationship between the two — a consumer that wants to correlate a crew's claim with the eventual canonical outcome does so as application-level policy, never as a core semantics guarantee.

## Ref-only fields are never inlined

`inputs_needed` and `artifact_refs` name things; they do not carry them. This mirrors `execution-session/v1`'s `transcript_ref` rule and `PORT-JOURNAL`'s explicit refusal to become a general artifact store. A component that persists `crew-report/v1` (the adapter-owned log, or a `JournalPort`/execution-observation snapshot) MUST persist each reference string unchanged and MUST NOT dereference, fetch, or inline the referenced content as part of that persistence. Resolving a reference into actual content is entirely the concern of whatever store the reference names, outside any Orc Werk contract.

## Durable ownership: the log is authoritative, journal snapshots are incidental

The adapter-owned append-only log (`docs/extensions/crew-report/README.md`'s "Durable ownership" section) is the durable owner of the full crew-report history for a `DeliveryRun`. An individual report MAY additionally ride an execution observation's or journal record's `extensions` slot as a point-in-time snapshot — for example, when a report happens to accompany a canonical fact that is being journaled anyway — but that snapshot is incidental, not authoritative: a consumer reconstructing "what did the crew report over the life of this run" reads the log, not a scan of journal `extensions` payloads, because most reports are produced between canonical transitions and have no journal write to ride at the moment they are produced.

## Ack / open-item state is deliberately absent

Whether a report has been acknowledged, and whether an open item it raises (an `inputs_needed` entry, a `"needs-action"` claim) has been handled, are questions this extension deliberately does not answer. `INV-017` keeps observed, handled, and accepted distinct wherever persistent attention is enabled, and issue #12 requires that report acknowledgement remain distinct from Work acceptance and from attention handling. `crew-report/v1` satisfies the append-only history requirement issue #12 raises without building ack/open-item machinery; a future companion contract, recorded in `CONTRACT-DURABILITY`'s ownership matrix, owns that state when it is designed.

## Relationship to steering (`CAP-EXEC-SEND`)

A crew report is a passive narration the producer emits; steering — sending a follow-up instruction mid-task — is a distinct, active operation already covered by `CAP-EXEC-SEND` (`PORT-EXECUTION`). `crew-report/v1` does not define or extend the send operation; a `"needs-action"` or `"waiting"` `claimed_verdict` may be the human/operator signal that prompts a `CAP-EXEC-SEND` call, but that correlation is operator/application judgment, not a mechanism this extension defines.
