"""`CONF-EXT-006` (core ignorance), the log-level instance `TASK-M1-007`'s
card requires: appending `crew-report/v1` records -- including a
`claimed_verdict` of `"done"` -- to a run's adapter-owned `CrewReportLog`
MUST NOT change `PORT-JOURNAL-005`'s canonical projection for that same
run when the underlying canonical facts (the `JournalPort`'s own file) are
held constant.

This is a scenario-level test, not a `tests/core/` reducer-only test like
`tests/core/test_extensions_core_ignorance.py`, because the guarantee
being proven here is structural/adapter-level (`CrewReportLog` and
`JournalPort` are two independent files the core reducer never reads
together), not a reducer-input-shape guarantee -- both are worth having,
and neither substitutes for the other.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from orc_werk.adapters.jsonl.crew_report import CLAIMED_VERDICT_VALUES, CrewReportLog
from orc_werk.adapters.jsonl.journal import JSONLJournal
from orc_werk.core.facts import FACT_WORK_CLAIMED, FACT_WORK_CREATED, FACT_WORK_READY, make_fact

DRID = "dr-crew-report-core-ignorance"


class CrewReportCoreIgnoranceTest(unittest.TestCase):
    def test_claimed_verdict_never_affects_canonical_projection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            journal = JSONLJournal(directory)
            facts = [
                make_fact(FACT_WORK_CREATED, delivery_run_id=DRID, work_id="w1"),
                make_fact(FACT_WORK_READY, delivery_run_id=DRID, work_id="w1"),
                make_fact(FACT_WORK_CLAIMED, delivery_run_id=DRID, work_id="w1", claim_ref="claim-1"),
            ]
            for fact in facts:
                journal.append_fact(fact)

            baseline_projection = journal.load_projection(delivery_run_id=DRID).to_dict()
            baseline_history = journal.history(delivery_run_id=DRID)

            # Same directory, distinct file/suffix -- the report log lives
            # beside, not inside, the journal (EXT-CREW-REPORT-V1 README's
            # "Durable ownership" section).
            report_log = CrewReportLog(directory)
            self.assertNotEqual(
                directory / f"{DRID}.jsonl", directory / f"{DRID}.reports.jsonl"
            )

            for turn, claimed_verdict in enumerate(sorted(CLAIMED_VERDICT_VALUES), start=1):
                report_log.append(
                    delivery_run_id=DRID,
                    execution_id="e1",
                    report={
                        "turn": turn,
                        "claimed_verdict": claimed_verdict,
                        "did": f"turn {turn} narration",
                    },
                )
            # Explicitly exercise the "done" claim CONF-EXT-006 names by
            # example -- appended last so it is the most recent report.
            report_log.append(
                delivery_run_id=DRID,
                execution_id="e1",
                report={"turn": 99, "claimed_verdict": "done", "did": "claims completion"},
            )
            self.assertEqual(len(report_log.list_reports(delivery_run_id=DRID)), len(CLAIMED_VERDICT_VALUES) + 1)

            # Canonical facts held constant throughout -- the journal file
            # was never touched again after the initial three facts.
            variant_projection = journal.load_projection(delivery_run_id=DRID).to_dict()
            variant_history = journal.history(delivery_run_id=DRID)

            self.assertEqual(variant_projection, baseline_projection)
            self.assertEqual(variant_history, baseline_history)

            # Also true for a freshly reopened JournalPort instance, so
            # this isn't merely an artifact of in-memory caching on the
            # same `journal` object.
            reopened_projection = JSONLJournal(directory).load_projection(delivery_run_id=DRID).to_dict()
            self.assertEqual(reopened_projection, baseline_projection)


if __name__ == "__main__":
    unittest.main()
