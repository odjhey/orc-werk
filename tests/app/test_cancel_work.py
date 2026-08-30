"""Application coverage for operator cancellation (STATE-DELIVERY item 10)."""

from __future__ import annotations

import unittest

from orc_werk.core.errors import CoreError
from orc_werk.core.state import STATE_CANCELLED
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


if __name__ == "__main__":
    unittest.main()
