"""Shared torn-tail-tolerant JSONL scan/append primitives.

`JSONLJournal` (`orc_werk.adapters.jsonl.journal`, `PORT-JOURNAL`'s
durable-journal-recovery clause) and the crew-report log adapter
(`orc_werk.adapters.jsonl.crew_report`, `TASK-M1-007`) both need the exact
same on-disk shape and recovery rule: one JSON envelope per line, flush
(never `fsync`) on append, and on reopen -- tolerate a single unparseable
FINAL line as a torn write only when at least one valid record precedes it,
reject any earlier malformed line with `ERR-VALIDATION`, and reject a file
with zero valid records at all with `ERR-VALIDATION` rather than presenting
empty history (`docs/contracts/ports/journal-port.md`'s "Durable-journal
recovery" clause; `TASK-M1-007`'s card applies this "by reference" to the
crew-report log). This module implements that rule exactly once so both
adapters share it instead of each reimplementing (and risking drifting)
it -- `TASK-M1-007`'s "reuse the jsonl JournalPort adapter's mechanics
rather than reinventing them."

Stdlib only (`json`, `pathlib`, `re`), matching `CLAUDE.md` rule 8's
zero-integration-dependency stance for adapters this reference
implementation ships alongside `src/orc_werk/core`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from orc_werk.core.errors import validation_error

# A run id becomes a filename component for every JSONL adapter in this
# package -- restrict it to a safe, unambiguous charset (no path
# separators, no ".."/hidden-file tricks) rather than attempting to
# encode/escape arbitrary strings. Least-commitment stopgap pending a
# normative delivery_run_id charset (see JSONLJournal's original PR body).
SAFE_DELIVERY_RUN_ID = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?$")

# (truncate_to_byte_offset, append_needs_leading_newline) -- pending tail
# repair discovered by `scan_tolerant`, applied lazily by the next append
# via `append_line`.
TailRepair = Tuple[int, bool]


def ensure_safe_run_id(delivery_run_id: str, *, message: str) -> None:
    """Raise canonical `ERR-VALIDATION` unless `delivery_run_id` is safe to
    use as a filename component. `message` is caller-supplied so each
    adapter's error names itself (a journal vs. a crew-report log) rather
    than this shared helper guessing which noun applies."""
    if not delivery_run_id or not SAFE_DELIVERY_RUN_ID.match(delivery_run_id):
        raise validation_error(message, delivery_run_id=delivery_run_id)


def scan_tolerant(path: Path, *, noun: str) -> Tuple[List[Dict[str, Any]], Optional[TailRepair]]:
    """Read all good JSON-envelope records from `path`, applying the
    torn-tail rule (module docstring): an unparseable FINAL line is
    ignored as a torn write only when at least one valid record precedes
    it; an unparseable NON-final line raises canonical `ERR-VALIDATION`;
    and a file with zero valid records at all raises canonical
    `ERR-VALIDATION` rather than presenting an empty history. A
    nonexistent path is not "a file with no valid records" -- it means no
    records have been appended yet, and returns `([], None)`.

    `noun` names the kind of file in error messages (e.g. `"journal"` or
    `"crew-report log"`) without this shared helper hardcoding either."""
    if not path.exists():
        return [], None
    raw = path.read_bytes()
    total = len(raw)
    records: List[Dict[str, Any]] = []
    good_end = 0
    offset = 0
    last_good_has_newline = True
    for chunk in raw.splitlines(keepends=True):
        offset += len(chunk)
        stripped = chunk.strip()
        if not stripped:
            good_end = offset
            continue
        try:
            record = json.loads(stripped.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            if offset >= total:
                # Torn write: partial final line -- ignore it; the next
                # append truncates it away (heal-while-use). This
                # tolerance is only meaningful when `records` already has
                # a good prefix -- when it does not, the zero-valid-
                # records check below (after the loop) fails this closed
                # instead, since a torn-looking final line with nothing
                # preceding it is indistinguishable from a plain garbage
                # file.
                break
            raise validation_error(
                f"malformed non-final JSONL {noun} line (corrupt {noun} file)",
                byte_offset=offset - len(chunk),
            )
        records.append(record)
        good_end = offset
        last_good_has_newline = chunk.endswith((b"\n", b"\r"))
    if not records:
        raise validation_error(
            f"{noun} file contains no valid records (not a {noun})",
            path=str(path),
        )
    needs_newline = good_end == total and total > 0 and not last_good_has_newline
    if good_end < total or needs_newline:
        return records, (good_end, needs_newline)
    return records, None


def append_line(path: Path, line: str, *, repair: Optional[TailRepair]) -> None:
    """Apply a pending torn-tail repair (if any) and append `line` (a
    single already-serialized JSON envelope, no trailing newline) to
    `path`, flushing without `fsync` -- the shared M0 durability stance
    (single-machine, single-writer-per-run context; see `JSONLJournal`'s
    module docstring for the full rationale, unchanged by this
    extraction)."""
    if repair is not None:
        good_end, needs_newline = repair
        with path.open("r+b") as fh:
            fh.truncate(good_end)
            if needs_newline:
                fh.seek(good_end)
                fh.write(b"\n")
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()


__all__ = ["SAFE_DELIVERY_RUN_ID", "TailRepair", "append_line", "ensure_safe_run_id", "scan_tolerant"]
