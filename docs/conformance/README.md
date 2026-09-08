---
id: CONFORMANCE-INDEX
type: index
status: current
authority: normative
description: Provider-independent conformance requirements.
---

# Conformance

Every real adapter must pass the same conformance requirements as its in-memory counterpart for each capability it advertises.

## Initial requirements

### Work graph
- `CONF-WORK-001`: ready excludes blocked dependencies.
- `CONF-WORK-002`: completion unlocks dependents only after required completion is committed.
- `CONF-WORK-003`: duplicate completion is idempotent or deterministically conflicting.
- `CONF-WORK-004`: atomic claim is tested when `CAP-WORK-ATOMIC-CLAIM` is advertised.

### Execution
- `CONF-EXEC-001`: start returns a stable logical execution identity.
- `CONF-EXEC-002`: repeated start with the same effect/idempotency key does not create two logical executions.
- `CONF-EXEC-003`: inspect distinguishes running from terminal settlement.
- `CONF-EXEC-004`: unsupported resume strength fails explicitly.
- `CONF-EXEC-005` (**superseded**, operator ruling ADR-0005 ruling A6, issue #214): exit-status honesty for an ACP vanished worker — with no terminal result, `no-session` settles failed only when the durable session is prompted and the outstanding turn's stream has substantive agent/tool activity; an empty/no-substantive startup stream remains running. This requirement only has meaning for a pull-observing execution adapter; the `acp` adapter that exercised it was removed in 0.5.0 (last release carrying it: v0.4.1). Retained, not deleted — see `SCN-016`'s supersession note, issue #206, and the issue #157 ambiguous-evidence precedent.

### Candidate
- `CONF-CAND-001`: same exact subject yields the same fingerprint.
- `CONF-CAND-002`: changed subject yields a different fingerprint.
- `CONF-CAND-003`: current() must not silently return a known-stale candidate.
- `CONF-CAND-004`: when identification of a settled completed Execution returns no assurable subject, the null observation is non-binding; every subsequent dispatch re-attempts identification with the same attempt-scoped `FX-IDENTIFY-CANDIDATE` idempotency key until a candidate binds or the attempt is legally abandoned. See `SCN-014` and issue #191.

### Assurance
- `CONF-ASSURE-001`: settled evidence names the candidate fingerprint.
- `CONF-ASSURE-002`: rejected never normalizes to accepted.
- `CONF-ASSURE-003`: evidence from a different fingerprint is rejected by the kernel.
- `CONF-ASSURE-004`: inconclusive remains distinct from rejected/accepted.
- `CONF-ASSURE-005`: at scripted-assurance ingestion, a recorded verdict carrying `derived_identity` that fails subset-equality against the bound candidate's durable `subject_identity` MUST be rejected with `ERR-CONFLICT` before any Fact is journaled; an assurance entry without `derived_identity` binds exactly as before. See `SCN-013` and issue #180.
- `CONF-ASSURE-006`: exit-status honesty — for a command-backed assurance provider, only clean exit 0 may map to `accepted` and only clean exit 1 may map to `rejected`; every other exit code, signal termination, or timeout MUST map to `inconclusive` and MUST NOT be guessed toward acceptance or rejection. See `SCN-015` and issue #194.
- `CONF-ASSURE-007`: hostile-stdout containment — command-backed assurance stdout MUST be bounded and validated before journaling; malformed, oversized, non-portable, or non-allowlisted output MUST NOT change verdict, candidate fingerprint, or lifecycle state, and the enrichment drop MUST be recorded in evidence. See `SCN-015` and issue #194.
- `CONF-ASSURE-008`: bounded re-request — an `inconclusive` settlement with assurance budget remaining (`INV-021`) MUST re-request assurance of the identical `candidate_id`/fingerprint under a new assurance identity and MUST NOT journal an execution start or advance `attempt_number`; with the budget exhausted it MUST resolve to `BLOCKED` with reason `assurance-inconclusive`; a journal lacking a recorded assurance budget MUST fold under a budget of `1`. See `SCN-021` and `ADR-0006`.

### Extensions
See [extension conformance](extensions.md) for `CONF-EXT-001` through `CONF-EXT-007`.

### Journal
- `CONF-JOURNAL-001`: append order is deterministic.
- `CONF-JOURNAL-002`: history is immutable/append-preserving.
- `CONF-JOURNAL-003`: replay reconstructs the same canonical projection, folding under the run's own durably recorded retry budget (`FX-CREATE-WORK` effect record `data.max_attempts`, `PORT-JOURNAL-005`) and assurance budget (`data.max_assurance_attempts`, `INV-021`) rather than an adapter default — including when the run's terminal state is `BLOCKED` (retry-budget exhaustion) and when replaying a legacy journal that predates either recorded budget. The two legacy fallbacks differ and are not interchangeable: a missing `max_attempts` falls back to the reducer's schema default, while a missing `max_assurance_attempts` falls back to `1` (the pre-`ADR-0006` behavior), never to that field's schema default of `2`. See `SCN-008` and `SCN-021`.
- `CONF-JOURNAL-004`: replay of operator cancellation deterministically reconstructs a clean, confirmed terminal `CANCELLED` projection; cancellation is rejected from every terminal state and never emits a port Effect or fabricates an assurance verdict. See `SCN-011`.

### CLI
- `CONF-CLI-CENSUS-001`: whole-ledger discovery — `orc census` enumerates
  runs through the canonical new-and-legacy per-run layout discriminator
  (`layout.discover_run_ids`), never a new-layout-only glob; a run present
  under either layout is never silently omitted from the totals. See
  `SCN-022` and issue #285.
- `CONF-CLI-CENSUS-002`: only settlement events are counted — every
  `FACT-ASSURE-SETTLED` counts exactly once by verdict
  (`accepted`/`rejected`/`inconclusive`); an inherited verdict reuse
  (`STATE-DELIVERY` item 8) journals no new Fact and MUST NOT be counted
  as a fresh settlement. See `SCN-022`.
- `CONF-CLI-CENSUS-003`: dated totals are as-of a stated inclusive UTC
  cutoff and exclude every settled Fact whose times-sidecar entry does
  not parse (missing sidecar, missing entry, or non-conforming value);
  excluded Facts are disclosed through an always-present `undated` count
  — never silently dropped and never assigned a fabricated time. See
  `SCN-022` and `CONTRACT-DURABILITY`'s times-sidecar row.
- `CONF-CLI-CENSUS-004`: model grouping preserves the exact self-reported
  `executor-identity/v1` string; a settled Fact with no such extension
  and one with the extension present but no `model` field MUST be
  reported as distinguishable, never-collided groups, and neither MAY be
  assigned a fabricated placeholder model string. See `SCN-022` and
  `EXT-EXECUTOR-IDENTITY-V1-SEMANTICS`.
- `CONF-CLI-CENSUS-005`: a run whose journal cannot be replayed
  (`PORT-JOURNAL`'s durable-journal recovery clause) degrades per run —
  it is named in an `unreadable_runs` list, the remaining runs' totals
  stay complete, and the command still exits `0`. See `SCN-022`.
- `CONF-CLI-CENSUS-006`: determinism — two invocations against an
  unchanged journal directory at the same explicit `--as-of` produce
  byte-identical totals and groups; an omitted `--as-of` derives its
  default cutoff only from `observed_at` values already recorded in the
  ledger (the latest dated settlement's own timestamp), never wall-clock
  time. See `SCN-022`.

## Portable conformance kit
See [the portable conformance kit](portable-kit.md) (`CONFORMANCE-PORTABLE-KIT`)
for a versioned, language-neutral JSON fixture corpus under `conformance/`
that lets an implementation without Python check its observable results
against the reference core for a named, bounded subset of the scenarios
above -- a conformance transport, not a substitute for this document.
