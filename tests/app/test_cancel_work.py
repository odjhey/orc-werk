"""Application coverage for operator cancellation (STATE-DELIVERY item 10)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from orc_werk.adapters.jsonl.journal import JSONLJournal
from orc_werk.core.errors import CoreError
from orc_werk.core.state import STATE_CANCELLED, STATE_EXECUTING
from tests.scenarios.support import build_run


class CancelWorkTest(unittest.TestCase):
    def test_cancel_records_reason_and_rejects_terminal_or_unknown_work(self) -> None:
        orchestrator, _journal, _graph = build_run(
            delivery_run_id="cancel-app-ready",
            attempts_by_work={"work-1": []},
        )

        orchestrator.cancel_work(work_id="work-1", reason="operator closed it", by="test-operator")
        work = orchestrator.projection().works["work-1"]
        self.assertEqual(work.state, STATE_CANCELLED)
        self.assertEqual(work.cancelled_reason, "operator closed it")

        with self.assertRaises(CoreError) as terminal:
            orchestrator.cancel_work(work_id="work-1", reason="again", by="test-operator")
        self.assertEqual(terminal.exception.to_canonical()["error"], "ERR-CONFLICT")

        with self.assertRaises(CoreError) as unknown:
            orchestrator.cancel_work(work_id="missing", reason="not there", by="test-operator")
        self.assertEqual(unknown.exception.to_canonical()["error"], "ERR-NOT-FOUND")


class CancelWorkReplayTest(unittest.TestCase):
    """`CONF-JOURNAL-004` / `SCN-011` items 2, 4, and 7: replaying operator
    cancellation of Work that had an Execution in flight (`EXECUTING`)
    deterministically reconstructs a clean, confirmed terminal `CANCELLED`
    projection -- no dangling `current_execution_id`, no fabricated
    `FACT-ASSURE-SETTLED`, no leftover candidate-conflict marker -- and this
    is asserted from a FRESH `JSONLJournal` instance reloading from disk (a
    true replay), not merely the live in-memory projection the cancelling
    orchestrator already held.

    Existing `tests/scenarios/test_cli_cancel.py` replay checks
    (`test_cancel_tolerates_persisted_config_naming_removed_adapter`,
    `test_cancelled_is_settled_and_excluded_from_active_index`) both cancel
    from `READY`; this is the item-2 in-flight-`EXECUTING` case the report
    driving this run flagged as having no dedicated CONF-JOURNAL-004 test."""

    def test_cancel_from_executing_replays_to_a_clean_confirmed_terminal_projection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            journal = JSONLJournal(root / ".orc")
            orchestrator, _journal, _graph = build_run(
                delivery_run_id="cancel-replay-executing",
                # `states=["running"]`: the Execution settles only on a
                # LATER `run()`/`inspect()` -- still genuinely in flight
                # (not yet settled) at the moment cancellation fires.
                attempts_by_work={"work-1": [{"outcome": "completed", "states": ["running"]}]},
                journal=journal,
            )
            in_flight = orchestrator.run()
            self.assertEqual(in_flight.works["work-1"].state, STATE_EXECUTING)
            self.assertIsNotNone(in_flight.works["work-1"].current_execution_id)

            orchestrator.cancel_work(
                work_id="work-1", reason="operator closed an in-flight execution", by="test-operator"
            )

            # No port Effect and no fabricated verdict (SCN-011 item 4):
            # the only new journal records are DEC-CANCEL/FACT-WORK-CANCELLED.
            history = journal.history(delivery_run_id="cancel-replay-executing")
            self.assertNotIn("FACT-ASSURE-SETTLED", [r["id"] for r in history])
            self.assertEqual(history[-1]["id"], "FACT-WORK-CANCELLED")
            self.assertEqual(history[-2]["id"], "DEC-CANCEL")

            # A FRESH journal instance replaying from disk -- not the live
            # orchestrator's own in-memory projection -- reconstructs the
            # identical clean, confirmed terminal state.
            replayed = JSONLJournal(root / ".orc").load_projection(delivery_run_id="cancel-replay-executing")
            work = replayed.works["work-1"]
            self.assertEqual(work.state, STATE_CANCELLED)
            self.assertTrue(work.cancelled_confirmed)
            self.assertEqual(work.cancelled_reason, "operator closed an in-flight execution")
            self.assertIsNone(work.current_execution_id)
            self.assertIsNone(work.current_assurance_id)
            self.assertIsNone(work.candidate_conflict)

            # Deterministic: replaying a second, independently-constructed
            # fresh journal instance reconstructs the exact same dict.
            replayed_again = JSONLJournal(root / ".orc").load_projection(delivery_run_id="cancel-replay-executing")
            self.assertEqual(replayed_again.works["work-1"].to_dict(), work.to_dict())


if __name__ == "__main__":
    unittest.main()
