"""SCN-005 -- dependency fan-in: A and B dispatch independently; C is not
returned by `WorkGraphPort.ready` after only A completes; C becomes
eligible only once both required upstream conditions are committed
(`docs/scenarios/SCN-005-fanin.md`). Verifies INV-015, INV-016.
"""

from __future__ import annotations

import unittest

from orc_werk.core.state import STATE_ACCEPTED, STATE_EXECUTING

from tests.scenarios.support import build_run

DRID_STUCK = "scn005-stuck"
DRID_FULL = "scn005-full"

PLAN = {
    "works": [
        {"work_id": "A", "deps": []},
        {"work_id": "B", "deps": []},
        {
            "work_id": "C",
            "deps": [{"work_id": "A", "condition": "accepted"}, {"work_id": "B", "condition": "accepted"}],
        },
    ]
}


class Scn005FanInTest(unittest.TestCase):
    def test_c_ineligible_after_only_a_completes(self) -> None:
        # B is scripted to stay "running" forever, so this run can be driven
        # to "A accepted, B still in flight" and frozen there.
        orchestrator, _journal, work_graph = build_run(
            delivery_run_id=DRID_STUCK,
            plan=PLAN,
            attempts_by_work={
                "A": [{"outcome": "completed", "candidate": {"label": "A1"}, "verdict": "accepted"}],
                "B": [{"outcome": "completed", "states": ["running"]}],
                "C": [{"outcome": "completed", "candidate": {"label": "C1"}, "verdict": "accepted"}],
            },
        )

        for _ in range(200):
            projection = orchestrator.projection()
            a_done = (
                projection.works["A"].state == STATE_ACCEPTED
                and projection.works["A"].completed_confirmed
            )
            if a_done:
                break
            if not orchestrator.step():
                break

        projection = orchestrator.projection()
        # A and B dispatch independently: both reached EXECUTING/beyond with
        # no ordering dependency between them.
        self.assertTrue(projection.works["A"].completed_confirmed)
        self.assertEqual(projection.works["B"].state, STATE_EXECUTING)

        # C is not returned by WorkGraphPort.ready after only A completes.
        ready_ids = {work.id for work in work_graph.ready(delivery_run_id=DRID_STUCK)}
        self.assertNotIn("C", ready_ids)
        self.assertIsNone(projection.works["C"].claim_ref)
        self.assertIsNone(projection.works["C"].current_execution_id)

    def test_c_eligible_once_both_upstreams_accepted(self) -> None:
        orchestrator, _journal, _work_graph = build_run(
            delivery_run_id=DRID_FULL,
            plan=PLAN,
            attempts_by_work={
                "A": [{"outcome": "completed", "candidate": {"label": "A1"}, "verdict": "accepted"}],
                "B": [{"outcome": "completed", "candidate": {"label": "B1"}, "verdict": "accepted"}],
                "C": [{"outcome": "completed", "candidate": {"label": "C1"}, "verdict": "accepted"}],
            },
        )
        projection = orchestrator.run()
        for work_id in ("A", "B", "C"):
            wp = projection.works[work_id]
            self.assertEqual(wp.state, STATE_ACCEPTED)
            self.assertTrue(wp.completed_confirmed)


if __name__ == "__main__":
    unittest.main()
