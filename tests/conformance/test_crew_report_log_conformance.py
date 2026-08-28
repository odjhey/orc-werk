"""`TASK-M1-007` conformance addition for `CrewReportLog`
(`orc_werk.adapters.jsonl.crew_report`), the file-based reference
implementation of `EXT-CREW-REPORT-V1`'s adapter-owned append-only log:

- **file shape / torn-tail recovery** -- the same rule `JSONLJournal`
  implements, reused via `orc_werk.adapters.jsonl.tailsafe` and applied
  here "by reference" per the task card;
- **append-only** -- no operation the log exposes can mutate or remove an
  already-appended record;
- **ordered** -- reports read back in the same order they were appended;
- **lossless round-trip** (`CONF-EXT-001`, `CONF-EXT-003`) -- a
  `crew-report/v1` payload, including unknown/reserved-adjacent keys
  tolerated per `EXT-005`, survives an append/reopen/read cycle unchanged.

`CONF-EXT-006` (`claimed_verdict` never affects the canonical projection)
is a separate scenario-level test:
`tests/scenarios/test_crew_report_core_ignorance.py`, since it needs both
a `JournalPort` and this log side by side to demonstrate the two are
independent.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from orc_werk.adapters.jsonl.crew_report import CrewReportLog
from orc_werk.core.errors import CoreError

DRID = "dr-crew-report"


class CrewReportLogFileShapeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.directory = Path(self._tmpdir.name)
        self.log = CrewReportLog(self.directory)

    def test_append_writes_distinct_reports_suffix_beside_where_a_journal_would_live(self) -> None:
        self.log.append(
            delivery_run_id=DRID, execution_id="e1", report={"turn": 1, "claimed_verdict": "waiting"}
        )
        report_path = self.directory / f"{DRID}.reports.jsonl"
        journal_path = self.directory / f"{DRID}.jsonl"
        self.assertTrue(report_path.exists())
        self.assertFalse(journal_path.exists())  # never created/merged by this adapter

    def test_file_contains_one_valid_json_record_per_line(self) -> None:
        self.log.append(
            delivery_run_id=DRID, execution_id="e1", report={"turn": 1, "claimed_verdict": "waiting"}
        )
        self.log.append(
            delivery_run_id=DRID, execution_id="e1", report={"turn": 2, "claimed_verdict": "done"}
        )
        path = self.directory / f"{DRID}.reports.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        for line in lines:
            record = json.loads(line)  # raises if not valid JSON
            self.assertEqual(
                set(record), {"schema_version", "delivery_run_id", "execution_id", "report"}
            )
            self.assertEqual(record["schema_version"], 1)
            self.assertEqual(record["delivery_run_id"], DRID)

    def test_unsafe_delivery_run_id_rejected_as_filename_component(self) -> None:
        with self.assertRaises(CoreError) as ctx:
            self.log.append(
                delivery_run_id="../escape", execution_id="e1", report={"turn": 1, "claimed_verdict": "done"}
            )
        self.assertEqual(ctx.exception.error["error"], "ERR-VALIDATION")

    def test_nonexistent_report_log_is_empty_not_an_error(self) -> None:
        self.assertEqual(self.log.list_reports(delivery_run_id="dr-brand-new"), ())

    def test_partial_trailing_line_is_ignored_on_reopen_and_next_append_continues(self) -> None:
        self.log.append(
            delivery_run_id=DRID, execution_id="e1", report={"turn": 1, "claimed_verdict": "waiting"}
        )
        self.log.append(
            delivery_run_id=DRID, execution_id="e1", report={"turn": 2, "claimed_verdict": "needs-action"}
        )
        path = self.directory / f"{DRID}.reports.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write('{"schema_version": 1, "delivery_run_id": "dr-crew-')  # torn write

        reopened = CrewReportLog(self.directory)
        records = reopened.list_reports(delivery_run_id=DRID)
        self.assertEqual([r["report"]["turn"] for r in records], [1, 2])

        # Next append heals the file back to one-valid-record-per-line form.
        reopened.append(
            delivery_run_id=DRID, execution_id="e1", report={"turn": 3, "claimed_verdict": "done"}
        )
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual([json.loads(line)["report"]["turn"] for line in lines], [1, 2, 3])

    def test_zero_valid_records_file_raises_err_validation(self) -> None:
        path = self.directory / f"{DRID}.reports.jsonl"
        path.write_text("hello this is not json at all, just plain text\n", encoding="utf-8")

        reopened = CrewReportLog(self.directory)
        with self.assertRaises(CoreError) as ctx:
            reopened.list_reports(delivery_run_id=DRID)
        self.assertEqual(ctx.exception.error["error"], "ERR-VALIDATION")

    def test_torn_final_line_with_no_preceding_valid_record_raises_err_validation(self) -> None:
        path = self.directory / f"{DRID}.reports.jsonl"
        path.write_text('{"schema_version": 1, "delivery_run_id": "dr-trunca', encoding="utf-8")

        reopened = CrewReportLog(self.directory)
        with self.assertRaises(CoreError) as ctx:
            reopened.list_reports(delivery_run_id=DRID)
        self.assertEqual(ctx.exception.error["error"], "ERR-VALIDATION")

    def test_malformed_non_final_line_raises_err_validation(self) -> None:
        self.log.append(
            delivery_run_id=DRID, execution_id="e1", report={"turn": 1, "claimed_verdict": "waiting"}
        )
        self.log.append(
            delivery_run_id=DRID, execution_id="e1", report={"turn": 2, "claimed_verdict": "done"}
        )
        path = self.directory / f"{DRID}.reports.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        lines[0] = "NOT-JSON-CORRUPTION"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        reopened = CrewReportLog(self.directory)
        with self.assertRaises(CoreError) as ctx:
            reopened.list_reports(delivery_run_id=DRID)
        self.assertEqual(ctx.exception.error["error"], "ERR-VALIDATION")


class CrewReportValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.log = CrewReportLog(Path(self._tmpdir.name))

    def test_missing_required_fields_rejected(self) -> None:
        with self.assertRaises(CoreError) as ctx:
            self.log.append(delivery_run_id=DRID, execution_id="e1", report={"turn": 1})
        self.assertEqual(ctx.exception.error["error"], "ERR-VALIDATION")

    def test_invalid_claimed_verdict_rejected(self) -> None:
        with self.assertRaises(CoreError) as ctx:
            self.log.append(
                delivery_run_id=DRID, execution_id="e1", report={"turn": 1, "claimed_verdict": "bogus"}
            )
        self.assertEqual(ctx.exception.error["error"], "ERR-VALIDATION")

    def test_reserved_verdict_key_is_not_a_substitute_for_claimed_verdict(self) -> None:
        # examples.md: a payload with `verdict` instead of `claimed_verdict`
        # is missing its required field.
        with self.assertRaises(CoreError) as ctx:
            self.log.append(delivery_run_id=DRID, execution_id="e1", report={"turn": 2, "verdict": "done"})
        self.assertEqual(ctx.exception.error["error"], "ERR-VALIDATION")

    def test_non_string_execution_id_rejected(self) -> None:
        with self.assertRaises(CoreError):
            self.log.append(
                delivery_run_id=DRID, execution_id="", report={"turn": 1, "claimed_verdict": "done"}
            )


class CrewReportAppendOnlyOrderedLosslessTest(unittest.TestCase):
    """`TASK-M1-007`'s conformance addition: append-only, ordered,
    lossless round-trip including unknown keys (`CONF-EXT-001`,
    `CONF-EXT-003`)."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.directory = Path(self._tmpdir.name)
        self.log = CrewReportLog(self.directory)

    def test_log_exposes_no_mutation_or_removal_operation(self) -> None:
        public_ops = {name for name in vars(CrewReportLog) if not name.startswith("_")}
        self.assertEqual(public_ops, {"append", "list_reports"})

    def test_ordered_read_back_matches_append_order(self) -> None:
        turns = [1, 2, 3, 4, 5]
        for turn in turns:
            self.log.append(
                delivery_run_id=DRID, execution_id="e1", report={"turn": turn, "claimed_verdict": "waiting"}
            )
        records = self.log.list_reports(delivery_run_id=DRID)
        self.assertEqual([r["report"]["turn"] for r in records], turns)

    def test_repeated_reads_never_change_already_appended_records(self) -> None:
        self.log.append(
            delivery_run_id=DRID, execution_id="e1", report={"turn": 1, "claimed_verdict": "waiting"}
        )
        first_read = self.log.list_reports(delivery_run_id=DRID)
        self.log.append(
            delivery_run_id=DRID, execution_id="e1", report={"turn": 2, "claimed_verdict": "done"}
        )
        second_read = self.log.list_reports(delivery_run_id=DRID)
        # The first record is byte-identical across reads and across an
        # intervening append -- append-only means no in-place mutation.
        self.assertEqual(first_read[0], second_read[0])

    def test_lossless_round_trip_including_unknown_keys(self) -> None:
        payload = {
            "turn": 3,
            "claimed_verdict": "waiting",
            "reason": "blocked on operator input",
            "did": "opened the migration draft PR",
            "pending": "awaiting review sign-off",
            "inputs_needed": ["opaque-input-ref-1"],
            "artifact_refs": ["opaque-artifact-ref-1"],
            "future_field_v2": {"nested": [1, 2.5, None, True, "s"]},
            "another_unknown": "value",
        }
        self.log.append(delivery_run_id=DRID, execution_id="e1", report=payload)

        # Reopen with a fresh instance -- crash-recovery-equivalent reload.
        reopened = CrewReportLog(self.directory)
        records = reopened.list_reports(delivery_run_id=DRID)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["report"], payload)
        self.assertEqual(records[0]["execution_id"], "e1")
        self.assertEqual(records[0]["delivery_run_id"], DRID)

    def test_execution_id_filter_scopes_list_without_losing_other_reports(self) -> None:
        self.log.append(
            delivery_run_id=DRID, execution_id="e1", report={"turn": 1, "claimed_verdict": "waiting"}
        )
        self.log.append(
            delivery_run_id=DRID, execution_id="e2", report={"turn": 1, "claimed_verdict": "done"}
        )
        self.log.append(
            delivery_run_id=DRID, execution_id="e1", report={"turn": 2, "claimed_verdict": "done"}
        )
        all_records = self.log.list_reports(delivery_run_id=DRID)
        e1_records = self.log.list_reports(delivery_run_id=DRID, execution_id="e1")
        self.assertEqual(len(all_records), 3)
        self.assertEqual([r["report"]["turn"] for r in e1_records], [1, 2])
        self.assertTrue(all(r["execution_id"] == "e1" for r in e1_records))


if __name__ == "__main__":
    unittest.main()
