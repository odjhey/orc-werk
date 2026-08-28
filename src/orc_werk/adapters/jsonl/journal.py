"""`JSONLJournal`: durable, file-backed `JournalPort` (`PORT-JOURNAL`)
implementation. Stdlib only (`json`, `pathlib`, `os`).

## Layout

One JSON-Lines file per DeliveryRun, `<directory>/<delivery_run_id>.jsonl`,
under a configured directory. Each line is exactly one canonical
`PORT-JOURNAL-ENVELOPE` JSON object, appended in `seq` order (one line ==
one record; no multi-line records, no trailing commentary). Placement is
per-run rather than one shared file for the whole journal so that: (a)
`history`/`load_projection` for one DeliveryRun never has to filter a
mixed-run file, and (b) crash-recovery replay of one run's file cannot be
corrupted by a concurrent append to an unrelated run. See the PR body for
why this lives in its own `orc_werk.adapters.jsonl` package rather than
`orc_werk.adapters.memory` (that package is documented as the dependency-free
*in-memory* family; this adapter's whole reason to exist is durable
file-backed storage).

Persisted lines are strict JSON: `json.dumps(..., allow_nan=False)`, so a
record that would need Python's non-standard `NaN`/`Infinity` literals is
rejected with canonical `ERR-VALIDATION` instead of poisoning the file for
non-Python readers (defense in depth -- `orc_werk.core.portable` already
rejects non-finite floats upstream).

## Durability stance (M0 / scripted context)

Every append does `write` + `flush` on the open file handle so the record
is visible to any other reader immediately; it deliberately does **not**
call `os.fsync(fh.fileno())`. `flush()` pushes bytes out of the Python
process into the OS page cache (survives a JournalPort/process crash) but
not necessarily to physical storage (would not survive an OS-level power
loss). M0 targets a single-machine scripted orchestration context, not a
durability SLA against OS/hardware failure, so flush-without-fsync is an
explicit, accepted stance for this milestone -- not an oversight. A later
milestone that needs stronger durability guarantees should revisit this
(and should do so as a capability the adapter advertises, per
`INV-013`/`CONTRACT-CAPABILITIES`, not a silent behavior change).

## Torn-tail recovery rule (watchtower ruling on PR review)

Because appends are flush-no-fsync, a crash can leave a *torn write*: a
partial final line. On read/reopen:

- If the FINAL line of the file is unparseable, it is treated as a torn
  write and ignored -- the journal continues from the last good record
  (heal-while-use; the torn bytes are truncated away on the next append so
  the file returns to one-valid-JSON-object-per-line form).
- Any malformed NON-final line is real corruption, not a torn write (a torn
  write can only ever be the last thing written), and raises canonical
  `ERR-VALIDATION` -- fail closed rather than replaying a journal with a
  hole in the middle.

## Reopen / concurrency

Sequence numbers are derived by counting good records already on disk for a
given `delivery_run_id`, cached in memory for the lifetime of one
`JSONLJournal` instance and refreshed lazily. This is correct for the
single-writer case M0 targets (one orchestrator process per DeliveryRun,
reopening its own journal after a crash/restart) but is **not** safe for
two `JSONLJournal` instances concurrently appending to the same file --
that is out of scope for this milestone (see the PR body's "Ambiguities
encountered").
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from orc_werk.adapters.journal_support import build_effect_envelope
from orc_werk.core.decisions import Decision
from orc_werk.core.effects import Effect
from orc_werk.core.errors import validation_error
from orc_werk.core.facts import Fact
from orc_werk.core.reducer import reduce
from orc_werk.core.serialization import KIND_FACT, decision_to_envelope, fact_from_envelope, fact_to_envelope
from orc_werk.core.state import DeliveryProjection
from orc_werk.ports.journal import JournalPort

# delivery_run_id becomes a filename component -- restrict it to a safe,
# unambiguous charset (no path separators, no ".."/hidden-file tricks)
# rather than attempting to encode/escape arbitrary strings. Least-commitment
# stopgap pending a normative delivery_run_id charset (see PR body).
_SAFE_DELIVERY_RUN_ID = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?$")

# (truncate_to_byte_offset, append_needs_leading_newline) -- pending tail
# repair discovered by _scan, applied lazily by the next append.
_TailRepair = Tuple[int, bool]


class JSONLJournal(JournalPort):
    def __init__(self, directory: str | os.PathLike[str]) -> None:
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)
        self._seq_cache: Dict[str, int] = {}
        self._tail_repair: Dict[str, Optional[_TailRepair]] = {}

    def capabilities(self) -> frozenset[str]:
        return frozenset()

    # -- internal helpers --------------------------------------------------

    def _path_for(self, delivery_run_id: str) -> Path:
        if not delivery_run_id or not _SAFE_DELIVERY_RUN_ID.match(delivery_run_id):
            raise validation_error(
                "delivery_run_id is not a safe JSONL journal filename component",
                delivery_run_id=delivery_run_id,
            )
        return self._directory / f"{delivery_run_id}.jsonl"

    def _scan(self, delivery_run_id: str) -> Tuple[List[Dict[str, Any]], Optional[_TailRepair]]:
        """Read all good records for one run, applying the torn-tail rule
        (module docstring): an unparseable FINAL line is ignored as a torn
        write; an unparseable NON-final line raises canonical
        `ERR-VALIDATION`. Returns the good records plus any pending tail
        repair the next append must apply."""
        path = self._path_for(delivery_run_id)
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
                    # append truncates it away (heal-while-use).
                    break
                raise validation_error(
                    "malformed non-final JSONL journal line (corrupt journal file)",
                    delivery_run_id=delivery_run_id,
                    byte_offset=offset - len(chunk),
                )
            records.append(record)
            good_end = offset
            last_good_has_newline = chunk.endswith((b"\n", b"\r"))
        needs_newline = good_end == total and total > 0 and not last_good_has_newline
        if good_end < total or needs_newline:
            return records, (good_end, needs_newline)
        return records, None

    def _ensure_scanned(self, delivery_run_id: str) -> None:
        if delivery_run_id not in self._seq_cache:
            records, repair = self._scan(delivery_run_id)
            self._seq_cache[delivery_run_id] = len(records)
            self._tail_repair[delivery_run_id] = repair

    def _heal_tail(self, delivery_run_id: str, path: Path) -> None:
        repair = self._tail_repair.pop(delivery_run_id, None)
        if repair is None:
            return
        good_end, needs_newline = repair
        with path.open("r+b") as fh:
            fh.truncate(good_end)
            if needs_newline:
                fh.seek(good_end)
                fh.write(b"\n")

    def _append(
        self, delivery_run_id: str, build_envelope: Callable[[int], Mapping[str, Any]]
    ) -> Mapping[str, Any]:
        self._ensure_scanned(delivery_run_id)
        seq = self._seq_cache[delivery_run_id] + 1
        envelope = build_envelope(seq)
        try:
            # allow_nan=False: strict JSON only -- never Python's
            # non-standard NaN/Infinity literals (module docstring).
            line = json.dumps(envelope, sort_keys=True, allow_nan=False)
        except ValueError as exc:
            raise validation_error(
                "journal record is not strict portable JSON (non-finite float?)",
                delivery_run_id=delivery_run_id,
                record_id=str(envelope.get("id")),
            ) from exc
        path = self._path_for(delivery_run_id)
        self._heal_tail(delivery_run_id, path)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            # M0 scripted-context durability stance (module docstring):
            # flush without os.fsync(fh.fileno()) is an explicit choice, not
            # an oversight.
        # only commit the cached seq once the write above has succeeded.
        self._seq_cache[delivery_run_id] = seq
        return json.loads(line)

    # -- PORT-JOURNAL --------------------------------------------------------

    def append_fact(self, fact: Fact) -> Mapping[str, Any]:
        return self._append(fact.delivery_run_id, lambda seq: fact_to_envelope(fact, seq=seq))

    def append_decision(self, decision: Decision) -> Mapping[str, Any]:
        return self._append(
            decision.delivery_run_id, lambda seq: decision_to_envelope(decision, seq=seq)
        )

    def append_effect_record(
        self, effect: Effect, *, dispatch_result: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        return self._append(
            effect.delivery_run_id,
            lambda seq: build_effect_envelope(effect, seq=seq, dispatch_result=dispatch_result),
        )

    def history(self, *, delivery_run_id: str) -> Sequence[Mapping[str, Any]]:
        records, _repair = self._scan(delivery_run_id)
        return tuple(sorted(records, key=lambda record: record["seq"]))

    def load_projection(self, *, delivery_run_id: str) -> DeliveryProjection:
        facts = [
            fact_from_envelope(record)
            for record in self.history(delivery_run_id=delivery_run_id)
            if record["kind"] == KIND_FACT
        ]
        return reduce(facts, delivery_run_id=delivery_run_id)


__all__ = ["JSONLJournal"]
