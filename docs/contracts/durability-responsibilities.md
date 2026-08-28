---
id: CONTRACT-DURABILITY
type: contract
status: current
authority: normative
version: 1
description: Durability-obligations contract and Rozoro retirement ledger for non-core durable information.
---

# Durability responsibilities

This contract records which information Orc Werk owns durably, which information it deliberately does not own, and which adapter/extension/provider is responsible for preserving what the core does not.

Non-core durable information MUST have an explicit owner. Silent loss of a durable operational record when Rozoro is retired is a defect, not an acceptable simplification.

This contract is authored per the disposition in the watchtower assessment on issue #12 (`M-001`, `TASK-M1-004`), which is binding for the dispositions recorded below.

## Purpose

`docs/contracts/orchestration-contract.md` and the core state machine (`docs/domain/state-machines/delivery.md`) define Orc Werk's canonical orchestration truth — the narrow set of Facts, Decisions, Effects, and entities (`Work`, `Execution`, `Candidate`, `Assurance`) the kernel and `PORT-JOURNAL` must preserve without exception.

Rozoro, the system Orc Werk is replacing, durably preserves additional information beyond that canonical core: delegated work briefs, structured handoff/report history, exact session/resume provenance, lifecycle evidence, attention state, and operator configuration. None of this belongs in the generic kernel (`INV-014`, `CONTRACT-EXTENSIONS`'s selection rule), but if it is dropped silently during migration, real operational and audit value disappears without anyone deciding that on purpose.

This contract is the completeness ledger: every category of non-core durable information gets an explicit disposition, and every concrete Rozoro-era durable object gets a line-item disposition in the retirement ledger below.

## Ownership matrix

| Information | Kernel canonical? | Required durable owner | Contract / extension | Disposition |
|---|---:|---|---|---|
| Canonical orchestration truth (Work/Execution/Candidate/Assurance identity, Facts, Decisions, Effects) | yes | kernel + `PORT-JOURNAL` (+ `WorkGraphPort`, `CandidatePort`, `AssurancePort` as applicable) | core | canonicalized |
| Delegated work specification — single-work run | no | kernel `PORT-JOURNAL` | `FACT-INTENT-SUBMITTED` (`intent_id`, verbatim `text`) already durably owns this case | canonicalized (already satisfied; no new extension registered) |
| Delegated work specification — multi-work brief | no | TBD | none registered yet | **OPEN** — owner TBD: a journal extension riding `FACT-WORK-CREATED`, vs. a dedicated artifact store, per watchtower open question 4 on issue #12 |
| Execution session provenance (native session id, resume strength/ref, transcript ref, execution profile) | no | Execution adapter | `execution-session/v1`, registered by this task under `docs/extensions/execution-session/` | delegated — registered |
| Dispatcher / watchtower / preset / policy attribution | no | execution/orchestration adapter | planned future provenance extension, split out of `execution-session/v1` per the watchtower ruling on issue #12 | delegated — **planned, unregistered** |
| Structured crew reports (append-only handoff history) | no | adapter-owned execution/report log (watchtower recommendation on record) | `crew-report/v1`, registered by `TASK-M1-007` under `docs/extensions/crew-report/` | **resolved** — registered; adapter-owned append-only log beside the journal (one NDJSON file per `DeliveryRun`, `execution_id` per record); reference implementation carded as `TASK-M1-007`. `PRODUCT-ADOPTION`'s Rozoro worked example (`docs/product/adoption.md` §4) was the persona-derived design input for this gate — it confirmed the adapter-owned-log disposition and that crew "steering" maps onto `CAP-EXEC-SEND` |
| Record observation wall-clock times (per-journal-record `observed_at`) | no | JSONL journal adapter sidecar | this row (`CONTRACT-DURABILITY`) — adapter-owned sidecar, not a `CONTRACT-EXTENSIONS` envelope `extensions`-slot extension | **resolved** (issue #39) — `<run_id>+times.jsonl`, one append-stamped `{seq, observed_at}` line (ISO-8601 UTC) per journal record, beside — never inside — the run's `<run_id>.jsonl` (the `+` sidecar separator is outside the safe run-id charset, so no legal run id can ever collide with a sidecar filename — the attempt-2 watchtower ruling on PR #46); deliberately excluded from `PORT-JOURNAL-ENVELOPE` itself because the canonical envelope must stay clock-free for `SCN-007`'s idempotent, record-identical replay guarantee, so wall-clock time is owned entirely by this adapter-local sidecar that no replay/projection path ever reads. Absent sidecar (e.g. any run recorded through the in-memory journal, which never writes one) means observation times are simply unknown, never an error |
| Report open-item / acknowledgement state | no | same adapter as crew reports | explicitly out of `crew-report/v1` (`EXT-CREW-REPORT-V1`'s "Ack / open-item state" section); a future companion contract | **OPEN** — deliberately deferred, not resolved by `crew-report/v1`'s registration; the report's `verdict` field is renamed to `claimed_verdict` in the registered schema per the watchtower recommendation, keeping a crew "done" report legible as a claim (`INV-003`) and not confusable with canonical assurance (`EXT-003`), but ack/open-item lifecycle state itself remains a future companion contract, reserved alongside `INV-017` |
| Runtime lifecycle/background evidence (session/turn/background start-stop, derived availability) | no | runtime/execution adapter | boundary noted here only; no port defined yet | deferred — hook is `CAP-EXEC-STRUCTURED-LIFECYCLE`; a future `RuntimeEvidencePort` or provider-owned durable lifecycle store is the anticipated shape, not yet designed |
| Attention identity and handling history | not yet | future attention adapter/port | none | deferred — boundary note only; M0 excludes attention, `INV-017` is conditional on attention being enabled |

`CONTRACT-CAPABILITIES` records the normative rule tying advertised capabilities to these durability obligations; see "Capability durability obligations" below.

## Capability durability obligations

Durability obligations are defined in terms of advertised capabilities so that preservation requirements are mechanically discoverable rather than implied by prose:

```text
capability
  -> required durable information
  -> durable owner
  -> contract/schema
  -> conformance test
```

The normative rule — an adapter MUST NOT claim a capability whose durability obligations are unmet — is landed as an explicit amendment to `CONTRACT-CAPABILITIES` (not restated here); see that document's capability-durability section. That amendment strengthens `INV-013`, `EXT-004`, and `CONF-EXT-005` from "fail rather than silently weaken/omit at the port" to "do not advertise the capability at all while the durability obligation is unmet."

The concrete mapping this contract is responsible for populating:

| Capability | Required durable information | Durable owner | Contract/schema | Conformance |
|---|---|---|---|---|
| `CAP-EXEC-RESUME-EXACT` | exact native session/resume provenance MUST be durable for the session being resumed | Execution adapter | `execution-session/v1` | `CONF-EXEC-004` (unsupported resume strength fails explicitly) today; a teardown + reconstruct + exact-resume conformance test is planned alongside the first adapter that advertises this capability (`TASK-M1-005`) |
| `CAP-EXEC-RESUME-BEST-EFFORT` | best-effort resume ref SHOULD be durable when advertised, but the adapter is not making an exactness promise | Execution adapter | `execution-session/v1` (`resume.strength = "best-effort"`) | `CONF-EXEC-004` |
| `CAP-EXEC-STRUCTURED-LIFECYCLE` | lifecycle evidence ordering/durability semantics MUST be declared by the adapter | runtime/execution adapter | future runtime evidence contract (unregistered) | planned — replay/ordering conformance, not yet defined |
| a future attention capability | stable attention identity + handling history MUST survive runtime teardown | future attention adapter/port | future attention contract (unregistered) | planned — teardown + reload + handling-state conformance, not yet defined |

Exact capability names for the deferred rows may change when their owning contract is designed; the requirement is the explicit mapping, not these particular identifiers.

Per the `CONTRACT-CAPABILITIES` exemption, in-memory conformance fixtures/test doubles (the scripted reference adapters) satisfy these obligations trivially — they reconstruct session identity deterministically in-process — and the mapping binds real provider adapters, first exercised at `TASK-M1-005`.

## Rozoro retirement ledger

This ledger audits Rozoro's durable inventory line by line, per the completeness/migration-closure rule from issue #12. Each row reaches exactly one disposition: **canonicalized**, **delegated**, **implementation-local**, or **intentionally dropped**. A "planned" or "OPEN GATE" delegated disposition is allowed — it still names an owner and, where possible, a contract — but every row must reach a disposition; none may be left unclassified.

This ledger audits the objects issue #12 itself enumerates as Rozoro's durable inventory. Completeness of that source inventory against the actual Rozoro codebase is the repository owner's to certify; this contract records the dispositions for the objects named in the proposal and its review comments, not an independent re-audit of Rozoro's source tree.

| Rozoro source object | Durable semantic / guarantee | Orc disposition | Durable owner | Contract / schema | Verification |
|---|---|---|---|---|---|
| `tasks/<id>/brief.md` | delegated work specification (single-work) | canonicalized | kernel `PORT-JOURNAL` | `FACT-INTENT-SUBMITTED` | replay reconstructs the verbatim submitted text |
| multi-work delegated brief (no single Rozoro file assumed) | delegated work specification (multi-work) | delegated — **OPEN** | TBD | TBD — `work-spec/v1` proposed, not registered | not yet defined |
| `tasks/<id>/handoff.md` | append-only crew report history | delegated — **resolved** | adapter-owned report log | `crew-report/v1`, registered under `docs/extensions/crew-report/`; reference implementation `TASK-M1-007` | teardown/reload preserves the full report history — `TASK-M1-007`'s conformance addition (append-only, ordered, lossless round-trip) |
| `.acked-blocks-v2` | unresolved/report ACK cursor | delegated — **OPEN** | same adapter as crew reports | report ACK contract — explicitly out of `crew-report/v1`; future companion contract, undecided | cursor/open items survive reload — not yet defined |
| `session.json` | exact session/resume provenance | delegated | Execution adapter | `execution-session/v1` | exact-resume conformance (`CONF-EXEC-004`; teardown/reconstruct test planned with `TASK-M1-005`) |
| `handoff-protocol.md` / `sysprompt.md` | policy/profile/version/provenance for the session, not the rendered file bytes | delegated | Execution adapter | `execution-session/v1` `profile` block | profile fields round-trip on reload |
| `monitor.db` lifecycle event records | durable lifecycle history, ordering, replay/reconstruction, conservative runtime-availability projections | delegated — deferred | runtime/execution adapter | future runtime evidence contract (unregistered); hook is `CAP-EXEC-STRUCTURED-LIFECYCLE` | planned — replay/ordering conformance, not yet defined |
| `spool/<event>.json` | pre-ACK durability: reserve -> send -> commit -> ACK -> safe removal | implementation-local | runtime/transport adapter | none — the replacement implementation documents its own equivalent guarantee, not this file shape | adapter-specific crash/retry test, not a canonical contract obligation |
| `producer-seq/*.seq` | producer ordering / replay integrity | implementation-local | runtime/transport adapter | none — equivalent guarantee documented by the replacement implementation | adapter-specific gap/replay test, not a canonical contract obligation |
| `monitor.sock` | live transport endpoint | intentionally dropped | none | n/a | rationale only: a live socket is not durable state; nothing is lost when the process is not running, so there is nothing to preserve |
| `watchtowers/attention/items/*` | stable attention identity + handling lifecycle | delegated — deferred | future attention adapter/port | future attention contract (unregistered) | planned — teardown/reload/handling-state test, not yet defined |
| watchtower registration/attribution history | dispatcher/watchtower/preset/policy provenance | delegated — planned | execution/orchestration adapter | planned future provenance extension, split out of `execution-session/v1` | planned — provenance round-trip test, not yet defined |
| watchtower presets/missions/policies | durable operator configuration | delegated | application/config provider | provider/application contract (outside Orc Werk core scope) | adapter/application-specific reload and version attribution |
| machine capability/configuration facts | capability/config provider record | delegated | capability/config provider | provider/application contract | explicitly documented by the provider, not a core obligation |
| wake generation, immutable snapshots, delivery/reconcile/ACK state | notification delivery durability | delegated | notification implementation | implementation-specific | explicitly documented by the implementation, not a core obligation |
| immutable operator artifacts | durable evidence/output references | delegated | artifact provider | artifact refs/store contract; content is ref-only and never rides `PORT-JOURNAL` or an extension payload (`PORT-JOURNAL`'s "not an artifact store" boundary) | reference remains resolvable after teardown |
| provider-native transcript/tool-level history referenced by `transcript_ref` | transcript content | delegated — ref-only | provider-specific transcript store | referenced by `execution-session/v1.transcript_ref`; content itself is out of scope for any Orc Werk contract | reference resolvability, not content preservation, is the Orc Werk-side obligation |
| execution/candidate/assurance attempt history | canonical orchestration truth | canonicalized | kernel `PORT-JOURNAL` / `CandidatePort` / `AssurancePort` | core (`ORCHESTRATION-CONTRACT`) | `CONF-JOURNAL-001` through `CONF-JOURNAL-003` |

### Migration-closure rule

Per issue #12: unclassified durable objects (rows with no disposition, or a delegated row with no named owner at all) block the **Rozoro-replacement milestone** — the point at which Rozoro is retired as the operational system of record. They do **not** block M1. M1a/M1a+/M1b (`M-001`) may ship with open rows outstanding, exactly as recorded above, because M1b's own acceptance bar (`docs/delivery/M1-delivery-ledger.md`) does not require closing every gate — it requires this contract to exist and the retirement ledger to have zero *unclassified* rows, which this document satisfies: every row above reaches canonicalized, delegated (registered, planned, or OPEN GATE), implementation-local, or intentionally dropped. `crew-report/v1`'s OPEN GATE closed via `TASK-M1-007`, ahead of M1b, without narrowing this rule: the multi-work `work-spec` owner, the runtime evidence contract, the attention contract, and `crew-report/v1`'s own ack/open-item companion contract remain open, and remaining open through M1 is still within this rule's allowance.

Closing an **OPEN** or **OPEN GATE** row later means: register the missing contract/schema, name its durable owner concretely, and land the applicable conformance test — it does not mean revisiting this contract's shape.

## Related

- `ORCHESTRATION-CONTRACT`
- `CONTRACT-EXTENSIONS`
- `CONTRACT-CAPABILITIES`
- `PORT-JOURNAL`
- `PORT-EXECUTION`
- `INV-013`
- `INV-014`
- `INV-017`
- `M-001`
- `TASK-M1-004`
- `TASK-M1-007`
- `EXT-CREW-REPORT-V1`
