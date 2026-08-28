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


if __name__ == "__main__":
    unittest.main()
