"""`JSONLJournal` runs the shared `CONF-JOURNAL-001`..`003` suite
(`tests/conformance/journal_suite.py`) via `JSONLJournalConformanceTest`,
plus JSONL-specific file-shape and reopen-after-crash assertions."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from orc_werk.adapters.jsonl.journal import JSONLJournal
from orc_werk.core.errors import CoreError
from orc_werk.core.facts import FACT_WORK_CLAIMED, FACT_WORK_CREATED, FACT_WORK_READY, make_fact
from orc_werk.core.reducer import reduce
from orc_werk.ports.journal import JournalPort

from tests.conformance.journal_suite import JournalConformanceSuite

_ENVELOPE_KEYS = {"schema_version", "seq", "delivery_run_id", "kind", "id", "data", "extensions"}


class JSONLJournalConformanceTest(JournalConformanceSuite):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self._directory = Path(self._tmpdir.name)
        self.journal_factory = lambda: JSONLJournal(self._directory)
        super().setUp()

    def reopen(self) -> JournalPort:
        # Crash-recovery: a fresh JSONLJournal instance against the same
        # directory must see everything a prior instance persisted.
        return JSONLJournal(self._directory)


class JSONLJournalFileShapeTest(unittest.TestCase):
    """JSONL-specific: file contains only valid JSON lines matching the
    envelope; reload-after-reopen equivalence (crash-recovery semantics)."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.directory = Path(self._tmpdir.name)
        self.journal = JSONLJournal(self.directory)

    def test_file_contains_one_valid_json_envelope_per_line(self) -> None:
        drid = "dr-jsonl-shape"
        self.journal.append_fact(make_fact(FACT_WORK_CREATED, delivery_run_id=drid, work_id="w1"))
        self.journal.append_fact(make_fact(FACT_WORK_READY, delivery_run_id=drid, work_id="w1"))

        path = self.directory / f"{drid}.jsonl"
        self.assertTrue(path.exists())
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        for i, line in enumerate(lines, start=1):
            envelope = json.loads(line)  # raises if not valid JSON.
            self.assertEqual(set(envelope), _ENVELOPE_KEYS)
            self.assertEqual(envelope["seq"], i)
            self.assertEqual(envelope["delivery_run_id"], drid)
            self.assertEqual(envelope["schema_version"], 1)

    def test_reload_after_reopen_reconstructs_identical_projection(self) -> None:
        drid = "dr-jsonl-crash-recovery"
        facts = [
            make_fact(FACT_WORK_CREATED, delivery_run_id=drid, work_id="w1"),
            make_fact(FACT_WORK_READY, delivery_run_id=drid, work_id="w1"),
        ]
        for fact in facts:
            self.journal.append_fact(fact)

        # Simulate crash/restart: discard the in-memory instance, open a
        # fresh JSONLJournal against the same directory, and replay.
        del self.journal
        reopened = JSONLJournal(self.directory)
        projection = reopened.load_projection(delivery_run_id=drid)
        expected = reduce(facts, delivery_run_id=drid)
        self.assertEqual(projection.to_dict(), expected.to_dict())
        self.assertEqual(len(reopened.history(delivery_run_id=drid)), len(facts))

    def test_reopen_continues_seq_assignment(self) -> None:
        drid = "dr-jsonl-continue-seq"
        self.journal.append_fact(make_fact(FACT_WORK_CREATED, delivery_run_id=drid, work_id="w1"))

        reopened = JSONLJournal(self.directory)
        second = reopened.append_fact(make_fact(FACT_WORK_READY, delivery_run_id=drid, work_id="w1"))
        self.assertEqual(second["seq"], 2)

        history = reopened.history(delivery_run_id=drid)
        self.assertEqual([r["seq"] for r in history], [1, 2])

    def test_every_persisted_line_parses_with_plain_stdlib_json(self) -> None:
        # portability rule: no orc_werk-specific decoder required.
        drid = "dr-jsonl-portable"
        self.journal.append_fact(
            make_fact(
                FACT_WORK_CREATED,
                delivery_run_id=drid,
                work_id="w1",
                extensions={"some-ext/v1": {"a": [1, 2.5, None, True, "s"]}},
            )
        )
        path = self.directory / f"{drid}.jsonl"
        for line in path.read_text(encoding="utf-8").splitlines():
            json.loads(line)

    def test_unsafe_delivery_run_id_rejected_as_filename_component(self) -> None:
        with self.assertRaises(CoreError) as ctx:
            self.journal.append_fact(
                make_fact(FACT_WORK_CREATED, delivery_run_id="../escape", work_id="w1")
            )
        self.assertEqual(ctx.exception.error["error"], "ERR-VALIDATION")

    # ------------------------------------------------------------------
    # Torn-tail recovery rule (P5 review F2, watchtower ruling).
    # ------------------------------------------------------------------

    def test_partial_trailing_line_is_ignored_on_reopen_and_next_append_continues_seq(self) -> None:
        drid = "dr-jsonl-torn-tail"
        facts = [
            make_fact(FACT_WORK_CREATED, delivery_run_id=drid, work_id="w1"),
            make_fact(FACT_WORK_READY, delivery_run_id=drid, work_id="w1"),
        ]
        for fact in facts:
            self.journal.append_fact(fact)
        path = self.directory / f"{drid}.jsonl"
        # Simulate a torn write: a flush interrupted mid-record leaves a
        # partial (non-JSON, newline-less) final line.
        with path.open("a", encoding="utf-8") as fh:
            fh.write('{"schema_version": 1, "seq": 3, "delivery_')

        reopened = JSONLJournal(self.directory)
        # Reopen succeeds with N-1 records (the torn tail is ignored) and
        # the projection replays from the good prefix.
        history = reopened.history(delivery_run_id=drid)
        self.assertEqual([r["seq"] for r in history], [1, 2])
        projection = reopened.load_projection(delivery_run_id=drid)
        self.assertEqual(projection.to_dict(), reduce(facts, delivery_run_id=drid).to_dict())

        # The next append gets the right seq (3, not 4) and heals the file
        # back to one-valid-JSON-object-per-line form.
        third = reopened.append_fact(
            make_fact(FACT_WORK_CLAIMED, delivery_run_id=drid, work_id="w1", claim_ref="claim-1")
        )
        self.assertEqual(third["seq"], 3)
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual([json.loads(line)["seq"] for line in lines], [1, 2, 3])

    # ------------------------------------------------------------------
    # #18 / amended PORT-JOURNAL durable-journal-recovery clause
    # (docs/contracts/ports/journal-port.md "Durable-journal recovery"):
    # torn-tail tolerance requires >=1 valid record preceding the
    # unparseable final line; a file with zero valid records at all is not
    # a journal.
    # ------------------------------------------------------------------

    def test_zero_valid_records_file_raises_err_validation(self) -> None:
        drid = "dr-jsonl-garbage"
        path = self.directory / f"{drid}.jsonl"
        path.write_text("hello this is not json at all, just plain text\n", encoding="utf-8")

        reopened = JSONLJournal(self.directory)
        with self.assertRaises(CoreError) as ctx:
            reopened.history(delivery_run_id=drid)
        self.assertEqual(ctx.exception.error["error"], "ERR-VALIDATION")

    def test_torn_final_line_with_no_preceding_valid_record_raises_err_validation(self) -> None:
        # A torn-looking final line with *zero* preceding good records is
        # indistinguishable from plain garbage -- the amended clause
        # requires a valid prefix before tolerating it as heal-while-use.
        drid = "dr-jsonl-torn-no-prefix"
        path = self.directory / f"{drid}.jsonl"
        path.write_text('{"seq":1,"kind":"fact","id":"FACT-BOGUS","data":{"trunca', encoding="utf-8")

        reopened = JSONLJournal(self.directory)
        with self.assertRaises(CoreError) as ctx:
            reopened.history(delivery_run_id=drid)
        self.assertEqual(ctx.exception.error["error"], "ERR-VALIDATION")

    def test_nonexistent_journal_file_is_not_the_zero_records_case(self) -> None:
        # A path that simply doesn't exist yet (a fresh run's first
        # dispatch) must still mean "no journal yet", not ERR-VALIDATION.
        drid = "dr-jsonl-brand-new"
        self.assertEqual(self.journal.history(delivery_run_id=drid), ())

    def test_malformed_non_final_line_raises_err_validation(self) -> None:
        drid = "dr-jsonl-corrupt-middle"
        self.journal.append_fact(make_fact(FACT_WORK_CREATED, delivery_run_id=drid, work_id="w1"))
        self.journal.append_fact(make_fact(FACT_WORK_READY, delivery_run_id=drid, work_id="w1"))
        path = self.directory / f"{drid}.jsonl"
        # Corrupt the FIRST line (non-final): real corruption, not a torn
        # write -- must fail closed.
        lines = path.read_text(encoding="utf-8").splitlines()
        lines[0] = "NOT-JSON-CORRUPTION"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        reopened = JSONLJournal(self.directory)
        with self.assertRaises(CoreError) as ctx:
            reopened.history(delivery_run_id=drid)
        self.assertEqual(ctx.exception.error["error"], "ERR-VALIDATION")
        with self.assertRaises(CoreError) as ctx2:
            reopened.append_fact(
                make_fact(FACT_WORK_CLAIMED, delivery_run_id=drid, work_id="w1", claim_ref="c")
            )
        self.assertEqual(ctx2.exception.error["error"], "ERR-VALIDATION")


class ObservedAtTimeSidecarTest(unittest.TestCase):
    """Issue #39, `CONTRACT-DURABILITY`'s "record observation wall-clock
    times" row: `JSONLJournal` stamps `<run_id>.times.jsonl` on each
    append, beside -- never inside -- the canonical journal, and it must
    never affect `history`/`load_projection` (SCN-007's record-identity
    guarantee is untouched by the sidecar's presence or absence)."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.directory = Path(self._tmpdir.name)
        self.journal = JSONLJournal(self.directory)

    def _times_path(self, drid: str) -> Path:
        return self.directory / f"{drid}.times.jsonl"

    def test_creation_deferred_to_first_append(self) -> None:
        drid = "dr-times-deferred"
        self.assertFalse(self._times_path(drid).exists())
        self.journal.append_fact(make_fact(FACT_WORK_CREATED, delivery_run_id=drid, work_id="w1"))
        self.assertTrue(self._times_path(drid).exists())

    def test_sidecar_lines_have_monotonically_matching_seqs(self) -> None:
        drid = "dr-times-seqs"
        self.journal.append_fact(make_fact(FACT_WORK_CREATED, delivery_run_id=drid, work_id="w1"))
        self.journal.append_fact(make_fact(FACT_WORK_READY, delivery_run_id=drid, work_id="w1"))
        self.journal.append_fact(
            make_fact(FACT_WORK_CLAIMED, delivery_run_id=drid, work_id="w1", claim_ref="c1")
        )

        journal_path = self.directory / f"{drid}.jsonl"
        journal_seqs = [json.loads(line)["seq"] for line in journal_path.read_text(encoding="utf-8").splitlines()]

        times_lines = self._times_path(drid).read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(times_lines), len(journal_seqs))
        for line, expected_seq in zip(times_lines, journal_seqs):
            record = json.loads(line)
            self.assertEqual(set(record), {"seq", "observed_at"})
            self.assertEqual(record["seq"], expected_seq)
            # ISO-8601 UTC, explicit Z suffix (module docstring).
            self.assertTrue(record["observed_at"].endswith("Z"))
            self.assertRegex(
                record["observed_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$"
            )

    def test_history_and_projection_byte_identical_with_sidecar_present_vs_deleted(self) -> None:
        drid = "dr-times-no-effect"
        facts = [
            make_fact(FACT_WORK_CREATED, delivery_run_id=drid, work_id="w1"),
            make_fact(FACT_WORK_READY, delivery_run_id=drid, work_id="w1"),
        ]
        for fact in facts:
            self.journal.append_fact(fact)

        with_sidecar_history = JSONLJournal(self.directory).history(delivery_run_id=drid)
        with_sidecar_projection = JSONLJournal(self.directory).load_projection(delivery_run_id=drid)

        self.assertTrue(self._times_path(drid).exists())
        self._times_path(drid).unlink()

        without_sidecar_history = JSONLJournal(self.directory).history(delivery_run_id=drid)
        without_sidecar_projection = JSONLJournal(self.directory).load_projection(delivery_run_id=drid)

        self.assertEqual(with_sidecar_history, without_sidecar_history)
        self.assertEqual(with_sidecar_projection.to_dict(), without_sidecar_projection.to_dict())

    def test_replay_never_reads_a_corrupt_sidecar(self) -> None:
        # A sidecar so corrupt it isn't even valid JSON at all must never
        # affect history/load_projection -- those never open this file.
        drid = "dr-times-corrupt-no-crash"
        self.journal.append_fact(make_fact(FACT_WORK_CREATED, delivery_run_id=drid, work_id="w1"))
        self._times_path(drid).write_text("not json at all\x00\x01", encoding="utf-8")

        reopened = JSONLJournal(self.directory)
        history = reopened.history(delivery_run_id=drid)  # must not raise
        self.assertEqual(len(history), 1)
        reopened.append_fact(make_fact(FACT_WORK_READY, delivery_run_id=drid, work_id="w1"))
        self.assertEqual(len(reopened.history(delivery_run_id=drid)), 2)

    def test_memory_journal_never_writes_a_sidecar(self) -> None:
        # CONTRACT-DURABILITY's row: "absent sidecar = times simply
        # unknown; the memory journal never writes one" -- MemoryJournal
        # has no times-sidecar code path at all (nothing to assert on
        # disk since it is not file-backed); this asserts the contrasting
        # positive: JSONLJournal is the only adapter that does.
        from orc_werk.adapters.memory.journal import MemoryJournal

        memory_journal = MemoryJournal()
        memory_journal.append_fact(make_fact(FACT_WORK_CREATED, delivery_run_id="dr-mem", work_id="w1"))
        # Nothing to assert on disk (MemoryJournal is not file-backed at
        # all) -- the point is simply that no such attribute/behavior
        # exists to produce one.
        self.assertFalse(hasattr(memory_journal, "_times_path_for"))


if __name__ == "__main__":
    unittest.main()
