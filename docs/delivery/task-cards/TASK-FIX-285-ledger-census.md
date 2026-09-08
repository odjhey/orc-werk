---
id: TASK-FIX-285
type: task-card
status: current
authority: normative
description: orc census -- a whole-ledger, as-of-dated tally of settled assurance verdicts, grouped by raw self-reported model x verdict x UTC day, closing issue #285's hand-rolled-join defect class.
implements: []
verifies: []
---

# TASK-FIX-285 -- `orc census`

Design source: issue #285, `docs/reports/2026-09-07-m5-pilot-retrospective.md`
§4 ("The counting lesson"). Not tied to any M-series milestone: a
standalone CLI fix card, dispatched directly by run id rather than as a
milestone-sequenced card.

## The gap

Three separate ship seats each hand-wrote a `jq`/Python join over
`.orc/*/journal.jsonl` x `times.jsonl` to answer one question -- how many
settled assurance verdicts exist, by model -- and each produced a
different wrong answer. The retrospective's own anchored "invariant"
figure (`{'accepted': 123, 'rejected': 50, 'inconclusive': 0}` as of
`2026-09-07T12:11:25Z`) reproduces the exact defect it diagnoses: its join
iterates `glob(".orc/*/journal.jsonl")`, which silently omits every
legacy flat-layout run (`layout.discover_run_ids` includes both layouts;
a bare `glob` does not). No `orc` verb performs this aggregate read today
-- `orc verdict` is a per-work latest-settlement projection that
deliberately collapses superseded assurances into prose, not a whole-run
counter.

## Outcome

`orc census [--as-of ISO8601Z] [--journal DIR] [--json]`: a read-only,
whole-ledger command that tallies every settled assurance Fact
(`FACT-ASSURE-SETTLED`; `accepted`/`rejected`/`inconclusive` -- never an
inherited verdict reuse, which journals no new Fact) across every run
under a journal directory, discovered through the canonical
new-and-legacy-layout enumeration (`layout.discover_run_ids`), dated by
the existing observed-at times sidecar, grouped by the exact self-reported
`executor-identity/v1` model string x verdict x UTC day.

**Dated, not an immutable snapshot.** `--as-of` names an inclusive UTC
cutoff; a settled Fact whose times-sidecar entry does not parse (missing
sidecar, missing entry, or a non-conforming value) is excluded from the
dated totals and disclosed through an always-present `undated` count --
never silently dropped, never assigned a fabricated time. Omitting
`--as-of` defaults to the latest recorded settlement timestamp already
present in the ledger (never wall-clock `now()`), so a default run is
still reproducible against an unchanged journal; an all-undated or empty
ledger reports `as_of: null` with the coverage disclosure, not a
fabricated cutoff. The sidecar is documented best-effort
(`CONTRACT-DURABILITY`); this command promises a reproducible *current*
dated read of what is on disk today, never a permanently frozen historical
guarantee across clock changes or a future re-stamped sidecar.

Model grouping is verbatim and unnormalized (`EXT-EXECUTOR-IDENTITY-V1-
SEMANTICS`'s no-fabrication rule): a settled Fact carrying no
`executor-identity/v1` extension at all and one carrying the extension
without a `model` field are reported as two distinct, never-collided
groups -- neither is assigned a fake model string.

A run whose journal cannot be replayed (`PORT-JOURNAL`'s durable-journal
recovery clause) degrades per run into an `unreadable_runs` list; the
remaining runs' totals stay complete and the command still exits `0`.

## In scope

- `docs/scenarios/SCN-022-ledger-census.md` (this card's executable
  specification).
- `docs/conformance/README.md`: `CONF-CLI-CENSUS-001` through `-006`
  (new `CONF-CLI-*` namespace).
- `docs/cli/README.md`: an `orc census` reference section.
- `docs/contracts/durability-responsibilities.md`: one sentence on the
  times-sidecar row noting an aggregate counting consumer now exists.
- `docs/reports/2026-09-07-m5-pilot-retrospective.md`: a dated correction
  of its anchored whole-ledger figure, preserving the original text
  (per that document's own six-vs-five correction convention) rather than
  silently rewriting it.
- `src/orc_werk/cli/census.py`: the new command's document builder.
- `src/orc_werk/cli/main.py`: `cmd_census` + `census` subparser.
- `tests/scenarios/test_cli_census.py`.

## Out of scope

- Any `executor-identity` normalization or validation rule (issue #281 --
  a separate contract decision; this card only makes the drift visible).
- A `FACT-EXEC-SETTLED`/ship-side census (assurance-only slice).
- Any `--group-by` flag, pagination, or index/caching layer (168 runs /
  3668 records / 198 settled Facts measured at 0.1s wall time -- no
  performance case exists).
- Any change to `orc verdict`'s latest-per-work projection.

## Acceptance

- `orc census` on a whole ledger containing new-layout, legacy-layout,
  undated, and corrupt runs counts every settled assurance Fact exactly
  once, excludes undated ones from the dated totals while disclosing
  their count, names unreadable runs without failing the read, and never
  counts an inherited verdict reuse as a fresh settlement.
- `orc census --json` emits one `orc-census/v1` document (schema-tagged,
  `sort_keys=True`) that is byte-identical across repeated invocations of
  an unchanged journal at the same `--as-of`.
- `SCN-022` and `CONF-CLI-CENSUS-001..006` are registered and exercised by
  `tests/scenarios/test_cli_census.py`.
- The retrospective's anchored figure carries a dated correction citing
  this command's own output against the real ledger at the same anchor.
