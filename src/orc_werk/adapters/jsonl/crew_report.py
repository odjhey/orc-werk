"""`CrewReportLog`: file-based reference implementation of the
`crew-report/v1` durable append-only log (`EXT-CREW-REPORT-V1`'s "Durable
ownership" section, `TASK-M1-007`). Stdlib only (`json`, `pathlib`, `os`),
matching `src/orc_werk/core`'s and `orc_werk.adapters.jsonl`'s
zero-integration-dependency stance (`CLAUDE.md` rule 8).

## Layout

One NDJSON file per `DeliveryRun`, `<directory>/<delivery_run_id>.reports.jsonl`,
distinct from -- and never merged into -- the `JournalPort`'s own
`<delivery_run_id>.jsonl` file (`EXT-CREW-REPORT-V1` README's "Durable
ownership" section: "a plain NDJSON file per `DeliveryRun`, distinct from
[...] the `JournalPort`'s own file"). This adapter is intentionally *not*
a `JournalPort` implementation: it does not assign `PORT-JOURNAL-ENVELOPE`
`seq` values, does not participate in `PORT-JOURNAL-005`'s canonical
projection, and core never reads it (`CONF-EXT-006`). Each line is one
record:

```json
{"schema_version": 1, "delivery_run_id": "...", "execution_id": "...", "report": {<crew-report/v1 payload>}}
```

`report` carries the `crew-report/v1` payload unchanged (`EXT-CREW-REPORT-V1-SCHEMA`),
including any unknown/non-reserved keys the producer added (`EXT-005`,
`CONF-EXT-003` lossless round-trip). Append order within one run's file is
this log's own ordering key -- distinct from, and not required to align
with, the `JournalPort` envelope's `seq` (`TASK-M1-007`'s card).

## Mechanics reused from `JSONLJournal`

This module deliberately does not reinvent the on-disk mechanics
`orc_werk.adapters.jsonl.journal.JSONLJournal` already implements for
`PORT-JOURNAL`; both adapters share the same line-scan/torn-tail/append
primitives via `orc_werk.adapters.jsonl.tailsafe` (`TASK-M1-007`'s card:
"reuse the jsonl `JournalPort` adapter's [...] mechanics rather than
reinventing them"):

- the same flush-without-`fsync` durability stance, for the same reasons
  (single-machine, single-writer-per-run context; see `JSONLJournal`'s
  module docstring for the full rationale);
- the same torn-tail recovery rule from `PORT-JOURNAL`'s durable-journal
  recovery clause, applied here "by reference" per the card: tolerate a
  single unparseable FINAL record as a torn write only when at least one
  valid record precedes it, reject any earlier malformed record with
  `ERR-VALIDATION`, and reject a file with zero valid records at all with
  `ERR-VALIDATION` rather than presenting empty history.

Unlike `JSONLJournal`, this adapter does not cache per-run record
counts/torn-tail state across calls within one process -- `append`/`list`
each rescan the file fresh. `JSONLJournal` caches because it assigns a
monotonically increasing `seq` per append and is on the orchestrator's hot
path (many facts/decisions/effects per run); this log assigns no such
counter and is written to at crew-narration frequency (per turn, not per
canonical transition), so the simplicity of "always re-derive from disk"
is preferred over caching for this reference implementation. This is a
deliberate simplicity trade-off, not a defect; a future optimization could
add the same per-instance cache `JSONLJournal` uses if append volume ever
warrants it.

## Append-only

The only operations this adapter exposes are `append` and `list_reports`;
neither mutates or removes an already-appended record (`TASK-M1-007`'s
conformance addition, "append-only"). The torn-tail heal on `append`
truncates only trailing *unparseable* bytes (a crash-torn write), never a
complete, previously valid record.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from orc_werk.adapters.jsonl import tailsafe
from orc_werk.core.errors import validation_error
from orc_werk.core.portable import is_portable, to_portable

SCHEMA_VERSION = 1

# EXT-CREW-REPORT-V1-SCHEMA: the two required fields.
_REQUIRED_FIELDS = ("turn", "claimed_verdict")

# EXT-CREW-REPORT-V1-SCHEMA "claimed_verdict" field rule: MUST be exactly
# one of these five values.
CLAIMED_VERDICT_VALUES = frozenset({"done", "waiting", "needs-action", "failed", "blocked"})

# EXT-CREW-REPORT-V1-SCHEMA: independently-optional free-text fields.
_STRING_FIELDS = ("reason", "did", "pending")

# EXT-CREW-REPORT-V1-SCHEMA "ref-only rule": independently-optional arrays
# of opaque reference strings.
_REF_ARRAY_FIELDS = ("inputs_needed", "artifact_refs")


def _validate_report_payload(report: Mapping[str, Any]) -> None:
    """`EXT-CREW-REPORT-V1-SCHEMA`'s producer-side strictness: the payload
    MUST contain `turn` and `claimed_verdict`, and every reserved field
    present MUST have the shape the schema declares. Non-reserved
    (unknown) keys are never inspected or rejected here -- they round-trip
    unchanged per `EXT-005`/`CONF-EXT-003`."""
    if not isinstance(report, Mapping):
        raise validation_error(
            "crew-report/v1 payload must be a JSON object", payload_type=type(report).__name__
        )
    if not is_portable(dict(report)):
        raise validation_error("crew-report/v1 payload must be portable JSON-compatible data")

    missing = [key for key in _REQUIRED_FIELDS if key not in report]
    if missing:
        raise validation_error(
            "crew-report/v1 payload missing required field(s)", missing_fields=missing
        )

    turn = report["turn"]
    if isinstance(turn, bool) or not isinstance(turn, int) or turn < 0:
        raise validation_error("crew-report/v1 'turn' must be a non-negative integer", turn=turn)

    claimed_verdict = report["claimed_verdict"]
    if claimed_verdict not in CLAIMED_VERDICT_VALUES:
        raise validation_error(
            "crew-report/v1 'claimed_verdict' must be one of the schema's fixed enum",
            claimed_verdict=claimed_verdict,
            allowed=sorted(CLAIMED_VERDICT_VALUES),
        )

    for key in _STRING_FIELDS:
        if key in report and not isinstance(report[key], str):
            raise validation_error(
                f"crew-report/v1 '{key}' must be a string when present", key=key
            )

    for key in _REF_ARRAY_FIELDS:
        if key in report:
            value = report[key]
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise validation_error(
                    f"crew-report/v1 '{key}' must be an array of strings when present", key=key
                )


def _validate_execution_id(execution_id: str) -> None:
    if not isinstance(execution_id, str) or not execution_id:
        raise validation_error(
            "execution_id must be a non-empty string", execution_id=execution_id
        )


class CrewReportLog:
    """Reference `crew-report/v1` durable log adapter (`TASK-M1-007`). Not
    a `JournalPort` -- there is no generic port for this extension-owned
    log; `EXT-CREW-REPORT-V1`'s "Durable ownership" section names the
    adapter-owned log itself as the contract."""

    def __init__(self, directory: str | os.PathLike[str]) -> None:
        # No filesystem side effects at construction time (the #17/#18
        # invariant PR #32 established for the CLI's main commands: a
        # read-only query, or an input rejected by validation, must never
        # leave a stray directory behind). Unlike `JSONLJournal.__init__`
        # (which predates that ruling and is guarded at the CLI layer
        # instead), this adapter defers directory creation to the first
        # actual write -- see `append`.
        self._directory = Path(directory)

    def _path_for(self, delivery_run_id: str) -> Path:
        tailsafe.ensure_safe_run_id(
            delivery_run_id,
            message="delivery_run_id is not a safe crew-report log filename component",
        )
        return self._directory / f"{delivery_run_id}.reports.jsonl"

    def append(
        self, *, delivery_run_id: str, execution_id: str, report: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        """Append one `crew-report/v1` record for `delivery_run_id`.
        Returns the persisted record (parsed back from the exact bytes
        written, mirroring `JSONLJournal.append_fact`'s return contract)."""
        _validate_execution_id(execution_id)
        _validate_report_payload(report)

        envelope = {
            "schema_version": SCHEMA_VERSION,
            "delivery_run_id": delivery_run_id,
            "execution_id": execution_id,
            "report": to_portable(dict(report)),
        }
        try:
            # allow_nan=False: strict JSON only -- never Python's
            # non-standard NaN/Infinity literals. Defense in depth:
            # `is_portable`/`to_portable` above already reject non-finite
            # floats, mirroring JSONLJournal's stance.
            line = json.dumps(envelope, sort_keys=True, allow_nan=False)
        except ValueError as exc:
            raise validation_error(
                "crew-report/v1 record is not strict portable JSON (non-finite float?)",
                delivery_run_id=delivery_run_id,
                execution_id=execution_id,
            ) from exc

        path = self._path_for(delivery_run_id)
        # Only now -- with every validation above passed and the record
        # fully serialized -- touch the filesystem at all: the deferred
        # directory creation (see `__init__`) happens here, immediately
        # before the first actual write, so a rejected append never
        # creates a stray directory as a side effect.
        self._directory.mkdir(parents=True, exist_ok=True)
        # Torn-tail rule reused by reference (module docstring): rescan for
        # a pending repair before every append rather than caching it
        # across calls (see module docstring's "Mechanics reused" section).
        _records, repair = tailsafe.scan_tolerant(path, noun="crew-report log")
        tailsafe.append_line(path, line, repair=repair)
        return json.loads(line)

    def list_reports(
        self, *, delivery_run_id: str, execution_id: Optional[str] = None
    ) -> Sequence[Mapping[str, Any]]:
        """Read reports for `delivery_run_id` back in append order
        (`TASK-M1-007`'s conformance addition, "ordered"), applying the
        torn-tail rule on reopen. When `execution_id` is given, only
        records for that execution are returned -- filtering by
        `execution_id`, per `EXT-CREW-REPORT-V1` README's "one file per
        `DeliveryRun`, `execution_id` per record" rationale, without
        needing a separate per-execution log.

        Strictly read-only: never creates the directory or the file (the
        #17/#18 no-side-effects-on-query invariant -- see `__init__`). A
        run with no report log yet returns an empty sequence, matching
        `JSONLJournal.history`'s "nonexistent path means no records yet,
        not an error" stance -- distinct from a log file that exists but
        contains no valid records, which raises `ERR-VALIDATION`."""
        path = self._path_for(delivery_run_id)
        records, _repair = tailsafe.scan_tolerant(path, noun="crew-report log")
        if execution_id is not None:
            records = [r for r in records if r.get("execution_id") == execution_id]
        return tuple(records)


__all__ = ["CLAIMED_VERDICT_VALUES", "CrewReportLog", "SCHEMA_VERSION"]
