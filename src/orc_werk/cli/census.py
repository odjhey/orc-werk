"""`orc census` (`TASK-FIX-285`, issue #285): a read-only, whole-ledger,
as-of-dated tally of settled assurance verdicts, grouped by the exact
self-reported `executor-identity/v1` model string x verdict x UTC day.

## Why this exists

`docs/reports/2026-09-07-m5-pilot-retrospective.md` §4 ("The counting
lesson"): three separate ship seats each hand-wrote a `jq`/Python join
over `.orc/*/journal.jsonl` x `times.jsonl` to answer one question -- how
many settled assurance verdicts exist, by model -- and each produced a
different wrong answer. The retrospective's own anchored figure
reproduces the exact defect it diagnoses: its join iterates
`glob(".orc/*/journal.jsonl")`, which silently skips every legacy
flat-layout run. This module is the mechanical fix: one command that
performs the aggregate join server-side, through the same discovery and
sidecar-reading code every other whole-ledger surface already uses.

## Design -- reuses, never reimplements

- **Discovery**: `orc_werk.cli.journal_reading._available_run_ids`
  (`layout.discover_run_ids`), the same new-and-legacy-layout enumeration
  `orc`'s bare index uses -- never a new-layout-only glob. This one line
  is the exact gap that undercounted the retrospective's own figure.
- **Reading**: `JSONLJournal.history` per run -- raw envelopes, never
  `load_projection`/replay. Counting only journaled `FACT-ASSURE-SETTLED`
  records means an inherited verdict reuse (`STATE-DELIVERY` item 8,
  which journals no new Fact) is never double-counted, by construction,
  with no special case needed.
- **Dating**: `orc_werk.cli.report._load_times_sidecar` (the same
  best-effort, skip-with-note sidecar reader `orc report`/`orc show`
  already use for presentation) and `orc_werk.cli.show._parse_observed_at`
  (the same strict, never-fabricating parse). A settled Fact whose `seq`
  has no times-sidecar entry, or whose entry does not parse, is
  `undated` -- excluded from the dated totals, never silently dropped and
  never assigned a fabricated time.
- **Degradation**: a run whose `history()` raises `CoreError`
  (`PORT-JOURNAL`'s durable-journal recovery clause -- a malformed
  non-final line, or a file with zero valid records) is named in
  `unreadable_runs`; the remaining runs' totals stay complete and the
  command still exits `0`, exactly as `orc`'s bare index degrades per run
  (`orc_werk.cli.main.cmd_index`).
- **Model grouping**: verbatim, per `EXT-EXECUTOR-IDENTITY-V1-SEMANTICS`'s
  no-fabrication rule -- `claude-sonnet-5` and `anthropic/claude-sonnet-5`
  are always two distinct groups. A settled Fact carrying no
  `executor-identity/v1` extension at all (`model=None,
  identity_extension=False`) and one carrying the extension without a
  `model` field (`model=None, identity_extension=True`) are kept
  distinguishable rather than collapsed onto one fabricated placeholder
  string.
- **Byte-discipline/determinism**: `--json` reuses
  `orc_werk.cli.jsonview.dump_json` (the one `sort_keys=True` emitter
  every other `--json` surface shares). This module adds no wall-clock or
  random data of its own; the only "current time" this command ever
  reports is `--as-of`'s omitted-default, which is itself derived only
  from `observed_at` values already recorded in the ledger (the latest
  dated settlement's own timestamp), never `now()` -- so two invocations
  against an unchanged journal at the same effective `--as-of` are
  byte-identical.

## Not an immutable-snapshot promise

The times sidecar is documented best-effort
(`CONTRACT-DURABILITY`'s "record observation wall-clock times" row):
`_stamp_observed_at` swallows `OSError` and never blocks the canonical
append it follows. `orc census` promises a reproducible, honestly-dated
*current* read of what is on disk today -- an unchanged journal always
re-derives the same answer -- not a permanently frozen historical
guarantee across clock changes, filesystem races, or a future re-stamped
sidecar. `undated`/`skipped_times_lines`/`unreadable_runs` are current
observed *coverage*, not a claimed cutoff snapshot.

## Shape (`orc-census/v1`)

```json
{
  "schema": "orc-census/v1",
  "journal_dir": "/abs/path/.orc",
  "as_of": "2026-09-07T12:11:25.000000Z",
  "as_of_source": "flag",
  "totals": {"accepted": 1, "rejected": 1, "inconclusive": 1, "settled": 3},
  "undated": 0,
  "skipped_times_lines": 0,
  "unreadable_runs": [{"run_id": "census-e", "error": "ERR-VALIDATION"}],
  "groups": [
    {
      "model": "claude-sonnet-5",
      "identity_extension": true,
      "day": "2026-09-05",
      "accepted": 1,
      "rejected": 0,
      "inconclusive": 0,
      "settled": 1
    }
  ]
}
```

`as_of_source` is `"flag"` (an explicit `--as-of`), `"latest-settlement"`
(the omitted-default: the maximum dated `observed_at` among counted
settlements), or `"none"` (no dated settlement exists at all -- `as_of`
is `null`, never a fabricated cutoff). `totals`/each group row always
carries all three verdict keys plus `settled`, even at zero -- a fixed
key set, matching `orc_werk.cli.jsonview`'s "null/zero when absent, never
omitted" convention, so a consumer never has to presence-check a verdict
that simply did not occur. `groups` is sorted by `(day, model is not
None, model or "", identity_extension)` for a stable, deterministic
order; a `model: null` row always sorts before any real model string on
the same day.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Mapping, NamedTuple, Optional

from orc_werk.adapters.jsonl.journal import JSONLJournal
from orc_werk.cli.journal_reading import _available_run_ids
from orc_werk.cli.report import _load_times_sidecar
from orc_werk.cli.show import _parse_observed_at
from orc_werk.core.errors import CoreError, validation_error
from orc_werk.core.facts import ASSURANCE_VERDICTS, FACT_ASSURE_SETTLED

CENSUS_SCHEMA = "orc-census/v1"

# `_parse_observed_at`'s own `_TIMES_FORMAT` (`orc_werk.cli.show`) is the
# sidecar's write shape and always carries microseconds. `--as-of` is
# operator-typed, so fractional seconds are accepted but optional; a bare
# offset, a naive local timestamp, and a date-only value are all rejected
# (the sidecar writer's own "never a bare offset" stance, applied to the
# read side).
_AS_OF_INPUT_FORMATS = ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ")


class Settlement(NamedTuple):
    verdict: str
    observed_at: Optional[datetime.datetime]
    model: Optional[str]
    identity_extension: bool


def parse_as_of(value: str) -> datetime.datetime:
    """Parse a caller-supplied `--as-of` value into a naive UTC datetime
    comparable against `_parse_observed_at`'s own naive-UTC output.
    Raises canonical `ERR-VALIDATION` for anything else, including a bare
    offset (`+02:00`), a naive local timestamp, and a date-only value --
    never guessed toward a timezone."""
    for fmt in _AS_OF_INPUT_FORMATS:
        try:
            return datetime.datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise validation_error(
        "--as-of must be a Z-suffixed UTC ISO-8601 timestamp, optionally with fractional "
        "seconds (e.g. 2026-09-07T12:11:25Z or 2026-09-07T12:11:25.000000Z) -- a bare "
        "offset, a naive local timestamp, and a date-only value are all rejected",
        as_of=value,
        next_steps=[
            "orc census --as-of 2026-09-07T12:11:25Z",
            "orc census with no --as-of to default to the ledger's own latest recorded settlement",
        ],
    )


def _format_as_of(value: Optional[datetime.datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _model_of(record: Mapping[str, Any]) -> tuple[Optional[str], bool]:
    """`(model, identity_extension)` for one settled Fact record.
    `identity_extension` distinguishes "no `executor-identity/v1` payload
    at all" (`False`) from "payload present, no `model` field" (`True`,
    `model=None`) -- both real, distinct cases per
    `EXT-EXECUTOR-IDENTITY-V1-SCHEMA` (`model` is independently optional),
    neither collapsed onto a fabricated placeholder string."""
    extensions = record.get("extensions")
    if not isinstance(extensions, Mapping):
        return None, False
    identity = extensions.get("executor-identity/v1")
    if not isinstance(identity, Mapping):
        return None, False
    model = identity.get("model")
    return (model if isinstance(model, str) else None), True


def collect_settlements(
    directory: Path,
) -> tuple[list[Settlement], list[dict[str, str]], int]:
    """Every settled assurance verdict across the whole journal
    directory -- both new and legacy per-run layouts
    (`_available_run_ids`) -- each dated by its run's times sidecar.

    Returns `(settlements, unreadable_runs, skipped_times_lines)`.
    `unreadable_runs` names each run `history()` could not replay
    (`PORT-JOURNAL`'s durable-journal recovery clause) with its canonical
    error id, in the same degrade-per-run-not-per-ledger style `orc`'s
    bare index already uses; the remaining runs are still fully counted.
    """
    journal = JSONLJournal(directory)
    settlements: list[Settlement] = []
    unreadable_runs: list[dict[str, str]] = []
    skipped_times_lines = 0
    for run_id in _available_run_ids(directory):
        try:
            history = journal.history(delivery_run_id=run_id)
        except CoreError as exc:
            unreadable_runs.append({"run_id": run_id, "error": exc.error.get("error", "ERR-UNKNOWN")})
            continue
        times, skipped = _load_times_sidecar(directory, run_id)
        skipped_times_lines += skipped
        for record in history:
            if record.get("kind") != "fact" or record.get("id") != FACT_ASSURE_SETTLED:
                continue
            data = record.get("data")
            verdict = data.get("verdict") if isinstance(data, Mapping) else None
            if verdict not in ASSURANCE_VERDICTS:
                continue
            observed_at = _parse_observed_at(times.get(record.get("seq")))
            model, identity_extension = _model_of(record)
            settlements.append(Settlement(verdict, observed_at, model, identity_extension))
    return settlements, unreadable_runs, skipped_times_lines


def census_document(directory: Path, *, as_of: Optional[datetime.datetime] = None) -> dict[str, Any]:
    """Build the `orc-census/v1` document -- see this module's docstring
    for the full shape. `as_of=None` defaults to the maximum dated
    `observed_at` among counted settlements (`"latest-settlement"`),
    never wall-clock `now()`; `as_of=None` with no dated settlement at
    all resolves to `as_of: null`, `as_of_source: "none"`."""
    settlements, unreadable_runs, skipped_times_lines = collect_settlements(directory)
    dated = [s for s in settlements if s.observed_at is not None]
    undated = len(settlements) - len(dated)

    as_of_source: str
    effective_as_of: Optional[datetime.datetime]
    if as_of is not None:
        effective_as_of, as_of_source = as_of, "flag"
    elif dated:
        effective_as_of, as_of_source = max(s.observed_at for s in dated), "latest-settlement"
    else:
        effective_as_of, as_of_source = None, "none"

    counted = [s for s in dated if effective_as_of is not None and s.observed_at <= effective_as_of]

    totals = {"accepted": 0, "rejected": 0, "inconclusive": 0}
    groups: dict[tuple[Optional[str], bool, str], dict[str, int]] = {}
    for s in counted:
        totals[s.verdict] += 1
        day = s.observed_at.strftime("%Y-%m-%d")
        key = (s.model, s.identity_extension, day)
        group = groups.setdefault(key, {"accepted": 0, "rejected": 0, "inconclusive": 0})
        group[s.verdict] += 1

    group_rows = [
        {
            "model": model,
            "identity_extension": identity_extension,
            "day": day,
            "accepted": counts["accepted"],
            "rejected": counts["rejected"],
            "inconclusive": counts["inconclusive"],
            "settled": sum(counts.values()),
        }
        for (model, identity_extension, day), counts in sorted(
            groups.items(),
            key=lambda item: (item[0][2], item[0][0] is not None, item[0][0] or "", item[0][1]),
        )
    ]

    return {
        "schema": CENSUS_SCHEMA,
        "journal_dir": str(directory),
        "as_of": _format_as_of(effective_as_of),
        "as_of_source": as_of_source,
        "totals": {**totals, "settled": sum(totals.values())},
        "undated": undated,
        "skipped_times_lines": skipped_times_lines,
        "unreadable_runs": unreadable_runs,
        "groups": group_rows,
    }


def _model_label(group: Mapping[str, Any]) -> str:
    if not group["identity_extension"]:
        return "(no executor-identity/v1)"
    if group["model"] is None:
        return "(no model field)"
    return str(group["model"])


def render_census_text(doc: Mapping[str, Any]) -> list[str]:
    """Text rendering of `census_document`'s output -- one line of
    context, one totals line, one line per group, then the mandatory
    coverage disclosures (issue #285: "count rejections by default and
    say so")."""
    totals = doc["totals"]
    as_of = doc["as_of"]
    anchor = "as of (no dated settlements)" if as_of is None else f"at or before {as_of} (source: {doc['as_of_source']})"
    noun = "verdict" if totals["settled"] == 1 else "verdicts"
    lines = [
        f"{totals['settled']} settled assurance {noun} {anchor} in {doc['journal_dir']}",
        f"accepted={totals['accepted']} rejected={totals['rejected']} inconclusive={totals['inconclusive']}",
    ]
    for group in doc["groups"]:
        lines.append(
            f"  {_model_label(group)}  day={group['day']}  "
            f"accepted={group['accepted']} rejected={group['rejected']} inconclusive={group['inconclusive']}"
        )
    undated_noun = "verdict" if doc["undated"] == 1 else "verdicts"
    lines.append(
        f"{doc['undated']} settled {undated_noun} undated (no parseable times-sidecar entry) "
        "-- excluded from the as-of window"
    )
    if doc["skipped_times_lines"]:
        lines.append(f"{doc['skipped_times_lines']} corrupt times-sidecar line(s) skipped")
    if doc["unreadable_runs"]:
        detail = ", ".join(f"{row['run_id']} ({row['error']})" for row in doc["unreadable_runs"])
        noun_runs = "run" if len(doc["unreadable_runs"]) == 1 else "runs"
        lines.append(f"{len(doc['unreadable_runs'])} unreadable {noun_runs}: {detail}")
    return lines


__all__ = [
    "CENSUS_SCHEMA",
    "Settlement",
    "census_document",
    "collect_settlements",
    "parse_as_of",
    "render_census_text",
]
