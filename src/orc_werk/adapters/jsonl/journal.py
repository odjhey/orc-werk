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

## Torn-tail recovery rule (watchtower ruling on PR review; refined for
## issue #18, `docs/contracts/ports/journal-port.md`'s amended
## durable-journal-recovery clause)

Because appends are flush-no-fsync, a crash can leave a *torn write*: a
partial final line. On read/reopen:

- If the FINAL line of the file is unparseable AND at least one valid
  record precedes it in the same file, it is treated as a torn write and
  ignored -- the journal continues from the last good record
  (heal-while-use; the torn bytes are truncated away on the next append so
  the file returns to one-valid-JSON-object-per-line form).
- Any malformed NON-final line is real corruption, not a torn write (a torn
  write can only ever be the last thing written), and raises canonical
  `ERR-VALIDATION` -- fail closed rather than replaying a journal with a
  hole in the middle.
- A file that exists but contains **zero valid records at all** (a
  one-line garbage file whose single line is indistinguishable from a
  "torn" final line with no preceding good records, or any other content
  that never parses as a single valid envelope) is not a journal: reading
  it raises canonical `ERR-VALIDATION` rather than presenting an empty
  history. This closes the silent-success-on-wrong-file hole (issue #18) --
  a stray or misdirected path resolving to garbage content used to be
  indistinguishable from a legitimate torn write with an empty prefix. A
  *nonexistent* path is unaffected: it is not "a file with no valid
  records", it is no file at all, and continues to mean "no journal yet"
  (a fresh run's first dispatch).

The line-scan/torn-tail-recovery/append mechanics below are implemented
once, shared with the crew-report log adapter (`TASK-M1-007`,
`orc_werk.adapters.jsonl.crew_report`), in
`orc_werk.adapters.jsonl.tailsafe`; this module keeps only what is
journal-specific (`seq` assignment/caching, fact/decision/effect envelope
construction).

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
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from orc_werk.adapters.journal_support import build_effect_envelope
from orc_werk.adapters.jsonl import tailsafe
from orc_werk.core.decisions import Decision
from orc_werk.core.effects import Effect
from orc_werk.core.errors import validation_error
from orc_werk.core.facts import Fact
from orc_werk.core.reducer import reduce
from orc_werk.core.serialization import KIND_FACT, decision_to_envelope, fact_from_envelope, fact_to_envelope
from orc_werk.core.state import DeliveryProjection
from orc_werk.ports.journal import JournalPort

# (truncate_to_byte_offset, append_needs_leading_newline) -- pending tail
# repair discovered by _scan, applied lazily by the next append. Re-exported
# alias of the shared primitive (module docstring's "Torn-tail recovery
# rule" section, `orc_werk.adapters.jsonl.tailsafe`).
_TailRepair = tailsafe.TailRepair


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
        tailsafe.ensure_safe_run_id(
            delivery_run_id,
            message="delivery_run_id is not a safe JSONL journal filename component",
        )
        return self._directory / f"{delivery_run_id}.jsonl"

    def _scan(self, delivery_run_id: str) -> Tuple[List[Dict[str, Any]], Optional[_TailRepair]]:
        """Read all good records for one run via the shared torn-tail
        primitive (`orc_werk.adapters.jsonl.tailsafe.scan_tolerant`,
        `PORT-JOURNAL`'s durable-journal recovery clause, issue #18).
        Returns the good records plus any pending tail repair the next
        append must apply."""
        path = self._path_for(delivery_run_id)
        return tailsafe.scan_tolerant(path, noun="journal")

    def _ensure_scanned(self, delivery_run_id: str) -> None:
        if delivery_run_id not in self._seq_cache:
            records, repair = self._scan(delivery_run_id)
            self._seq_cache[delivery_run_id] = len(records)
            self._tail_repair[delivery_run_id] = repair

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
        # M0 scripted-context durability stance (module docstring): the
        # shared `tailsafe.append_line` primitive flushes without
        # `os.fsync(fh.fileno())` -- an explicit choice, not an oversight.
        tailsafe.append_line(path, line, repair=self._tail_repair.pop(delivery_run_id, None))
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
