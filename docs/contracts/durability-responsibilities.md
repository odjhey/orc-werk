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
| Delegated work specification — multi-work brief | no | `BeadsMirror`'s native `bd` issue description store, when an operator configures the optional `mirror` block (`src/orc_werk/adapters/beads/mirror.py`, `TASK-M2-006`); ephemeral (dispatching-party records only) otherwise | `docs/adapters/beads/mapping.md` (`ADAPTER-BEADS-MAPPING`, adapter-local — not a `CONTRACT-EXTENSIONS` schema; the kernel still journals no brief field, per `INV-014`/rule 8) | **amended — adapter now exists, durability is conditional** (`TASK-M2-006`, landing on top of the 2026-08-28 issues #12/#47 operator ruling below): the kernel still does not journal per-work briefs and still builds no dedicated core artifact store — that disposition is unchanged. The first real WorkGraph adapter this row anticipated shipped as a **write-only mirror**, not a `PORT-WORK-GRAPH` implementation (`docs/adapters/beads/README.md`), so it durably owns briefs (`bd`'s own issue description, one `bd create --description` per Work) whenever an operator actually configures `mirror` + supplies `briefs` in the CLI dispatch config (`src/orc_werk/cli/config.py`'s "Beads mirror" docstring section) — this is genuinely durable `bd` state, independently readable after the orc-werk journal/process is gone, but it is never read back by orc-werk itself (write-only, `INV-014`-quarantined adapter vocabulary). **Absent that configuration, the original disposition is unchanged and still applies verbatim**: multi-work briefs are deliberately NOT durable — a run's journal reconstructs its topology and every verdict, but not what each work meant; per-work specifications live in the dispatching party's records (ephemeral). The single-work case remains durably owned by `FACT-INTENT-SUBMITTED` (row above) regardless of mirror configuration. Operators who need durable multi-work briefs without configuring the mirror should still carry the essentials in the run-level intent text (every Work's `bd` description falls back to that same intent text when no per-work `briefs` entry is supplied, per the mapping doc's brief-fallback note). |
| Run topology (create plan: works + dependency edges) and effective retry budget (`max_attempts` policy parameter in force for this run) | no | kernel `PORT-JOURNAL` — the `FX-CREATE-WORK` effect record's journaled `data.plan` (`PORT-WORK-001` plan shape) and `data.max_attempts` (issue #52) | none registered; already satisfied by the effect record | **resolved — normative** (operator ruling, issue #41; extended by the issue #52 ruling, 2026-08-28, citing this row as precedent rather than new design): a journal from which the run's topology cannot be reconstructed is non-conformant, and the same reasoning applies to the retry budget the run actually used — `max_attempts` is policy config, not journaled state, so without a durable record replay of a non-default-budget run can fold under the wrong budget and reject its own recorded Facts (`ERR-CONFLICT`), defeating self-sufficient replay (`PORT-JOURNAL-005`, `CONF-JOURNAL-003`, the `INV-020` durable-anchor spirit). `data.max_attempts` is therefore recorded alongside `data.plan` in the same `FX-CREATE-WORK` effect record and MUST be folded back by `load_projection`/replay (`PORT-JOURNAL-005`). A journal written before this field existed has none; readers MUST fall back to the reducer's schema default (`DEFAULT_MAX_ATTEMPTS`), mirroring the issue #55 layout read-fallback pattern. Distinct from the multi-work brief-text row above (resolved, conditionally, by `TASK-M2-006`) — topology/budget are the graph and its policy parameter, brief is the prose spec. Presentation surfaces (e.g. the report's future dependency-tree view, issue #41) MAY rely on either. |
| Execution session provenance (native session id, resume strength/ref, transcript ref, execution profile) | no | Execution adapter | `execution-session/v1`, registered by this task under `docs/extensions/execution-session/` | delegated — registered |
| Dispatcher / watchtower / preset / policy attribution | no | execution/orchestration adapter | planned future provenance extension, split out of `execution-session/v1` per the watchtower ruling on issue #12 | delegated — **planned, unregistered** |
| Structured crew reports (append-only handoff history) | no | none — see disposition | superseded: `crew-report/v1` (`docs/extensions/crew-report/`, `EXT-CREW-REPORT-V1`), registered by `TASK-M1-007`, removed per issue #100 part 2 | **superseded — no adapter-owned log** (operator ruling, issue #100 part 2, "reference-first narrative doctrine," issue #65 amended): the adapter-owned append-only crew-report log this row originally resolved to is removed, pre-v1, no backward compat. This category of information is no longer given its own durable extension at all — it folds into the reference-first disposition below (line "Disposition:" under this table): narrative content stays provider-owned, and the ledger journals a resolvable reference to it (`execution-session/v1`, `evidence_refs`), surfaced read-only via `orc refs`. `EXT-CREW-REPORT-V1`'s doc pages remain on disk, marked `status: superseded`, so a reader with a pre-removal `crew-report/v1` sidecar on disk (now inert) can still interpret its shape |
| Record observation wall-clock times (per-journal-record `observed_at`) | no | JSONL journal adapter sidecar | this row (`CONTRACT-DURABILITY`) — adapter-owned sidecar, not a `CONTRACT-EXTENSIONS` envelope `extensions`-slot extension | **resolved** (issue #39; filename layout amended by issue #55 H1) — one append-stamped `{seq, observed_at}` line (ISO-8601 UTC) per journal record, beside — never inside — the run's own journal. Every run created under issue #55's per-run directory layout gets `<run_id>/times.jsonl` beside that same directory's `<run_id>/journal.jsonl`; a run that already existed before issue #55 keeps its legacy `<run_id>+times.jsonl` flat file beside `<run_id>.jsonl` for its whole lifetime instead (read/write-fallback, never a mid-run switch — `orc_werk.adapters.jsonl.layout` resolves which applies per run id). The legacy `+` sidecar separator remains on the books for that flat layout (outside the safe run-id charset, so no legal run id can ever collide with a sidecar filename — the attempt-2 watchtower ruling on PR #46) but is moot inside a new-layout run directory, where every artifact is disambiguated by directory scope plus a fixed filename instead. Deliberately excluded from `PORT-JOURNAL-ENVELOPE` itself because the canonical envelope must stay clock-free for `SCN-007`'s idempotent, record-identical replay guarantee, so wall-clock time is owned entirely by this adapter-local sidecar that no replay/projection path ever reads. Absent sidecar (e.g. any run recorded through the in-memory journal, which never writes one) means observation times are simply unknown, never an error |
| Report open-item / acknowledgement state | no | none named — see disposition | a future companion contract, undesigned | **OPEN** — deliberately deferred; the adapter-owned `crew-report/v1` log this row's "same adapter as crew reports" owner once pointed at is removed (issue #100 part 2), so this row now names no even-hypothetical owner at all. Ack/open-item lifecycle state remains a future companion contract, reserved alongside `INV-017`, unaffected in scope by the removal (it was always explicitly out of `crew-report/v1`'s own scope, per that extension's now-superseded "Ack / open-item state" section) |
| Runtime lifecycle/background evidence (session/turn/background start-stop, derived availability) | no | runtime/execution adapter | boundary noted here only; no port defined yet | deferred — hook is `CAP-EXEC-STRUCTURED-LIFECYCLE`; a future `RuntimeEvidencePort` or provider-owned durable lifecycle store is the anticipated shape, not yet designed |
| Attention identity and handling history | not yet | future attention adapter/port | none | deferred — boundary note only; M0 excludes attention, `INV-017` is conditional on attention being enabled |

Disposition: narrative/report content is provider-owned and the ledger journals resolvable references; sidecar extensions are the fallback where no provider-native store exists, with `execution-session/v1` and `EXT-CREW-REPORT-V1` as instances.

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
| `CAP-EXEC-RESUME-EXACT` | exact native session/resume provenance MUST be durable for the session being resumed | Execution adapter | `execution-session/v1` | `CONF-EXEC-004` (unsupported resume strength fails explicitly) today; a teardown + reconstruct + exact-resume conformance test is planned alongside the first adapter that advertises this capability (first exercised by the since-superseded `TASK-M1-005`) |
| `CAP-EXEC-RESUME-BEST-EFFORT` | best-effort resume ref SHOULD be durable when advertised, but the adapter is not making an exactness promise | Execution adapter | `execution-session/v1` (`resume.strength = "best-effort"`) | `CONF-EXEC-004` |
| `CAP-EXEC-STRUCTURED-LIFECYCLE` | lifecycle evidence ordering/durability semantics MUST be declared by the adapter | runtime/execution adapter | future runtime evidence contract (unregistered) | planned — replay/ordering conformance, not yet defined |
| a future attention capability | stable attention identity + handling history MUST survive runtime teardown | future attention adapter/port | future attention contract (unregistered) | planned — teardown + reload + handling-state conformance, not yet defined |

Exact capability names for the deferred rows may change when their owning contract is designed; the requirement is the explicit mapping, not these particular identifiers.

Per the `CONTRACT-CAPABILITIES` exemption, in-memory conformance fixtures/test doubles (the scripted reference adapters) satisfy these obligations trivially — they reconstruct session identity deterministically in-process — and the mapping binds real provider adapters, first exercised by the since-superseded `TASK-M1-005`.

## Rozoro retirement ledger

This ledger audits Rozoro's durable inventory line by line, per the completeness/migration-closure rule from issue #12. Each row reaches exactly one disposition: **canonicalized**, **delegated**, **implementation-local**, or **intentionally dropped**. A "planned" or "OPEN GATE" delegated disposition is allowed — it still names an owner and, where possible, a contract — but every row must reach a disposition; none may be left unclassified.

This ledger audits the objects issue #12 itself enumerates as Rozoro's durable inventory. Completeness of that source inventory against the actual Rozoro codebase is the repository owner's to certify; this contract records the dispositions for the objects named in the proposal and its review comments, not an independent re-audit of Rozoro's source tree.

| Rozoro source object | Durable semantic / guarantee | Orc disposition | Durable owner | Contract / schema | Verification |
|---|---|---|---|---|---|
| `tasks/<id>/brief.md` | delegated work specification (single-work) | canonicalized | kernel `PORT-JOURNAL` | `FACT-INTENT-SUBMITTED` | replay reconstructs the verbatim submitted text |
| multi-work delegated brief (no single Rozoro file assumed) | delegated work specification (multi-work) | delegated — **resolved, conditional** (`TASK-M2-006`; was **OPEN**) | `BeadsMirror` (`bd` issue description), when `mirror` is configured; ephemeral (dispatching-party records) otherwise | `docs/adapters/beads/mapping.md` — adapter-local, not a registered `work-spec/v1` core extension (that proposal is superseded by the adapter-owned disposition, per the ownership-matrix row above) | teardown/reload of the `bd` database preserves every mirrored Work's description (`bd show`); no orc-werk-side conformance test reads it back (write-only, by design) — see `docs/adapters/beads/mapping.md`'s live-smoke test for the durable-write proof |
| `tasks/<id>/handoff.md` | append-only crew report history | delegated — **superseded** | none — see ownership-matrix "Structured crew reports" row above | was `crew-report/v1` (`docs/extensions/crew-report/`, `EXT-CREW-REPORT-V1`), registered under `TASK-M1-007`; removed per issue #100 part 2, superseding disposition folds this into the reference-first doctrine (`execution-session/v1`, `evidence_refs`, `orc refs`) | N/A — no adapter-owned log exists to verify; historical verification (append-only, ordered, lossless round-trip, `TASK-M1-007`'s conformance addition) applied only while the log existed |
| `.acked-blocks-v2` | unresolved/report ACK cursor | delegated — **OPEN** | none named — see ownership-matrix "Report open-item / acknowledgement state" row above | report ACK contract — a future companion contract, undecided (no longer even hypothetically owned by the crew-report adapter, which is removed) | cursor/open items survive reload — not yet defined |
| `session.json` | exact session/resume provenance | delegated | Execution adapter | `execution-session/v1` | exact-resume conformance (`CONF-EXEC-004`; teardown/reconstruct test planned with the since-superseded `TASK-M1-005`) |
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

Per issue #12: unclassified durable objects (rows with no disposition, or a delegated row with no named owner at all) block the **Rozoro-replacement milestone** — the point at which Rozoro is retired as the operational system of record. They do **not** block M1. M1a/M1a+/M1b (`M-001`) may ship with open rows outstanding, exactly as recorded above, because M1b's own acceptance bar (`docs/delivery/M1-delivery-ledger.md`) does not require closing every gate — it requires this contract to exist and the retirement ledger to have zero *unclassified* rows, which this document satisfies: every row above reaches canonicalized, delegated (registered, planned, superseded, or OPEN GATE), implementation-local, or intentionally dropped. `crew-report/v1`'s OPEN GATE closed via `TASK-M1-007`, ahead of M1b, without narrowing this rule, and its whole disposition has since been superseded by the reference-first narrative doctrine (issue #100 part 2) — a **superseded** disposition still counts as classified, not unclassified, so this remains within the rule's allowance; the multi-work brief owner closed (conditionally) via `TASK-M2-006`, in M2, the same way. The runtime evidence contract, the attention contract, and the report ack/open-item companion contract (now with no even-hypothetical owner, following the crew-report removal) remain open, and remaining open is still within this rule's allowance.

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
