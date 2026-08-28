"""SCN-003 -- execution failure: Execution 1 remains immutable history,
Execution 2 has a new identity, Work acceptance occurs only after
assurance of Execution 2's candidate (`docs/scenarios/SCN-003-execution-
failure.md`). Verifies INV-003, INV-004, INV-018.
"""

from __future__ import annotations

import unittest

from orc_werk.core.state import STATE_ACCEPTED

from tests.scenarios.support import build_run

DRID = "scn003"
WORK_ID = "A"


class Scn003ExecutionFailureTest(unittest.TestCase):
    def test_failed_execution_retried_and_history_preserved(self) -> None:
        orchestrator, journal, _work_graph = build_run(
            delivery_run_id=DRID,
            attempts_by_work={
                WORK_ID: [
                    {"outcome": "failed"},
                    {"outcome": "completed", "candidate": {"label": "C2"}, "verdict": "accepted"},
                ]
            },
        )
        projection = orchestrator.run()
        wp = projection.works[WORK_ID]

        # Execution 1 remains immutable history: failed, never overwritten.
        self.assertEqual(len(wp.executions), 2)
        first, second = wp.executions
        self.assertEqual(first["outcome"], "failed")
        self.assertEqual(second["outcome"], "completed")
        self.assertNotEqual(first["execution_id"], second["execution_id"])

        # Work acceptance occurs only after assurance of Execution 2's candidate.
        self.assertEqual(wp.state, STATE_ACCEPTED)
        self.assertTrue(wp.completed_confirmed)
        (candidate_entry,) = wp.candidates.values()
        self.assertEqual(candidate_entry["execution_id"], second["execution_id"])

        history = journal.history(delivery_run_id=DRID)
        exec_settled = [r for r in history if r["kind"] == "fact" and r["id"] == "FACT-EXEC-SETTLED"]
        self.assertEqual([r["data"]["outcome"] for r in exec_settled], ["failed", "completed"])


if __name__ == "__main__":
    unittest.main()
