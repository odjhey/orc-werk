---
id: SCN-022
type: scenario
status: current
authority: normative
description: Whole-ledger dated tally of settled assurance verdicts across new and legacy journal layouts, grouped by raw model x verdict x UTC day; undated settlements and unreadable runs are disclosed, never fabricated or dropped.
---

# SCN-022 -- Ledger census (`orc census`, issue #285)

## Purpose

Executable specification for `TASK-FIX-285`: the whole-ledger aggregate
read issue #285 asked for, closing the defect class three hand-rolled
`jq`/Python joins each reproduced (`docs/reports/2026-09-07-m5-pilot-
retrospective.md` §4). Verifies `CONF-CLI-CENSUS-001` through `-006`.

## Given (mixed-layout, dated whole-ledger tally)

- Journal directory `D` contains:
  - `census-a` (new per-run-directory layout): Work `w` settles
    `FACT-ASSURE-SETTLED(accepted)`, times-sidecar entry `T1 =
    2026-09-01T00:00:00.000000Z`.
  - `census-b` (new layout): Work `w` settles
    `FACT-ASSURE-SETTLED(rejected)`, times-sidecar entry `T2 =
    2026-09-02T00:00:00.000000Z`.
  - `census-c` (**legacy flat layout** -- `census-c.jsonl` +
    `census-c+times.jsonl` beside `D`, no `census-c/` directory): Work `w`
    settles `FACT-ASSURE-SETTLED(inconclusive)`, times-sidecar entry `T3 =
    2026-09-01T12:00:00.000000Z` (between `T1` and `T2`).

## Then (mixed-layout, dated whole-ledger tally)

1. `orc census --as-of 2026-09-02T00:00:00Z --journal D` reports
   `totals = {accepted: 1, rejected: 1, inconclusive: 1, settled: 3}` --
   the legacy-layout run `census-c` is counted exactly like a new-layout
   run (`CONF-CLI-CENSUS-001`; this is the precise gap that undercounted
   the retrospective's own anchored figure by every legacy-layout run's
   settlements).
2. `orc census --as-of 2026-09-01T00:00:00Z --journal D` (the `T1`
   instant, inclusive) reports `totals = {accepted: 1, rejected: 0,
   inconclusive: 0, settled: 1}`: `census-b`'s later `T2` and
   `census-c`'s later-than-`T1` `T3` are both excluded, proving the
   cutoff is inclusive at `T1` and strictly excludes anything dated after
   it (`CONF-CLI-CENSUS-003`).
3. Reissuing the exact `--as-of 2026-09-02T00:00:00Z` command again
   against the unchanged directory `D` reproduces byte-identical
   `--json` output (`CONF-CLI-CENSUS-006`).

## Given (undated settlement)

- `D` additionally contains `census-d`: Work `w` settles
  `FACT-ASSURE-SETTLED(accepted)`, but its times-sidecar carries no entry
  for that Fact's `seq` (deleted/never written).

## Then (undated settlement)

4. `orc census --as-of 2026-09-02T00:00:00Z --journal D` still reports
   `totals.settled = 3` (unchanged from item 1 -- `census-d`'s settlement
   is excluded from the dated window regardless of `--as-of`) and
   `undated = 1`: the count is disclosed, never silently absent from the
   document and never assigned a fabricated `observed_at`
   (`CONF-CLI-CENSUS-003`).

## Given (unreadable run)

- `D` additionally contains `census-e`, whose journal has a malformed
  (non-final, non-JSON) line before at least one valid record.

## Then (unreadable run)

5. `orc census --journal D` still exits `0`; `census-a`/`b`/`c`/`d`'s
   totals are unaffected and complete; `unreadable_runs` names `census-e`
   with its canonical error id (`ERR-VALIDATION`,
   `PORT-JOURNAL`'s durable-journal recovery clause) -- a many-runs read
   degrades per run, never per ledger (`CONF-CLI-CENSUS-005`).

## Given (inherited verdict is not a fresh settlement)

- `D` additionally contains `census-f`: Work `w2`'s attempt 1 produces
  Candidate `C1` and settles `FACT-ASSURE-SETTLED(rejected)`; attempt 2
  re-observes `C1` unchanged (identical fingerprint), which
  `STATE-DELIVERY` item 8 resolves by mechanically inheriting the
  `rejected` verdict rather than requesting or settling a fresh
  assurance.

## Then (inherited verdict is not a fresh settlement)

6. `census-f` contributes exactly one settled Fact to the totals (the
   original attempt-1 settlement) -- inheritance journals no new
   `FACT-ASSURE-SETTLED`, so census counts settlement events, never
   attempts or projection states (`CONF-CLI-CENSUS-002`).

## Given (raw, unnormalized model grouping)

- `D` additionally contains `census-g` with three settled Facts:
  - one carrying `extensions."executor-identity/v1" = {"model":
    "claude-sonnet-5", "role": "verify"}`;
  - one carrying `extensions."executor-identity/v1" = {"role":
    "verify"}` (payload present, no `model` field);
  - one carrying no `executor-identity/v1` extension at all.

## Then (raw, unnormalized model grouping)

7. The census groups these into three distinct rows: `model =
   "claude-sonnet-5"`; `model = null, identity_extension = true` (payload
   present, no model field); and `model = null, identity_extension =
   false` (extension absent) -- never collapsed onto one another and
   never assigned a fake placeholder model string in either null case
   (`CONF-CLI-CENSUS-004`, `EXT-EXECUTOR-IDENTITY-V1-SEMANTICS`'s
   no-fabrication rule).

## Given (default `--as-of` and an empty/all-undated ledger)

## Then (default `--as-of` and an empty/all-undated ledger)

8. `orc census --journal D` (no `--as-of`) defaults the cutoff to the
   maximum dated `observed_at` among `D`'s counted settlements, echoed as
   `as_of` with `as_of_source: "latest-settlement"` -- never `now()`
   (`jsonview`'s determinism rule; `CONF-CLI-CENSUS-006`). Appending a new
   later-dated settlement to `D` and reissuing the *same explicit*
   `--as-of` from item 1 still reproduces item 1's totals unchanged; a
   bare re-run with no `--as-of` legitimately advances to the new
   high-water mark -- this is an honestly-dated current read, not a
   broken immutability promise.
9. A journal directory with zero runs, or with settled Facts but none
   dated, reports `as_of: null`, `as_of_source: "none"`,
   `totals = {accepted: 0, rejected: 0, inconclusive: 0, settled: 0}`, and
   `undated` equal to however many settled Facts exist (`0` for the
   zero-run case) -- never a fabricated cutoff.

## Mutation check

Reverting run discovery to a new-layout-only `glob(".orc/*/journal.jsonl")`
scan turns item 1 red: `census-c` silently vanishes from the totals --
issue #285's own defect, reproduced by construction. Dropping the
undated-exclusion turns item 4 red (a fabricated placement for a Fact with
no observed time). Counting inherited-verdict reuse as a fresh settlement
turns item 6 red. Normalizing/mapping bare model strings turns item 7 red.

## Verifies

- `CONF-CLI-CENSUS-001` through `CONF-CLI-CENSUS-006`
- `PORT-JOURNAL` durable-journal recovery clause
- `CONTRACT-DURABILITY`'s times-sidecar row
- `STATE-DELIVERY` item 8, `observers.py`'s inherited-verdict exclusion
- `EXT-EXECUTOR-IDENTITY-V1-SCHEMA`, `EXT-EXECUTOR-IDENTITY-V1-SEMANTICS`
