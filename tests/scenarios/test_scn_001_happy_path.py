"""SCN-001 -- happy path: Work A dispatched once, one Execution retained,
Candidate C1's exact fingerprint carried through to accepted assurance
evidence, completion only after acceptance (`docs/scenarios/SCN-001-happy-
path.md`). Verifies INV-003, INV-005, INV-007, INV-011, INV-020.
"""

from __future__ import annotations

import unittest

from orc_werk.core.decisions import DEC_ACCEPT
from orc_werk.core.effects import FX_COMPLETE_WORK
from orc_werk.core.state import STATE_ACCEPTED

from tests.scenarios.support import build_run

DRID = "scn001"
WORK_ID = "A"


class Scn001HappyPathTest(unittest.TestCase):
    def _run(self):
        orchestrator, journal, _work_graph = build_run(
            delivery_run_id=DRID,
            attempts_by_work={
                WORK_ID: [{"outcome": "completed", "candidate": {"label": "C1"}, "verdict": "accepted"}]
            },
        )
        projection = orchestrator.run()
        return projection, journal

    def test_work_accepted_after_single_dispatch(self) -> None:
        projection, journal = self._run()
        wp = projection.works[WORK_ID]

        # 1. Work A is dispatched once.
        exec_started = [
            r
            for r in journal.history(delivery_run_id=DRID)
            if r["kind"] == "fact" and r["id"] == "FACT-EXEC-STARTED"
        ]
        self.assertEqual(len(exec_started), 1)

        # 2. One Execution is retained.
        self.assertEqual(len(wp.executions), 1)

        # 3. Candidate C1 has an exact fingerprint.
        fingerprint = wp.current_candidate_fingerprint()
        self.assertIsNotNone(fingerprint)
        self.assertTrue(fingerprint.startswith("fp-"))

        # 4. Assurance evidence references C1's fingerprint.
        assure_settled = next(
            r
            for r in journal.history(delivery_run_id=DRID)
            if r["kind"] == "fact" and r["id"] == "FACT-ASSURE-SETTLED"
        )
        self.assertEqual(assure_settled["data"]["candidate_fingerprint"], fingerprint)

        # 5. Work A completes only after assurance acceptance.
        self.assertEqual(wp.state, STATE_ACCEPTED)
        self.assertTrue(wp.completed_confirmed)
        history = journal.history(delivery_run_id=DRID)
        settled_seq = assure_settled["seq"]
        completed_seq = next(
            r["seq"] for r in history if r["kind"] == "fact" and r["id"] == "FACT-WORK-COMPLETED"
        )
        self.assertLess(settled_seq, completed_seq)

        # 6. Facts, Decisions, and Effects are present in the Journal.
        kinds = {r["kind"] for r in history}
        self.assertEqual(kinds, {"fact", "decision", "effect"})
        decision_ids = [r["id"] for r in history if r["kind"] == "decision"]
        self.assertIn(DEC_ACCEPT, decision_ids)
        complete_effects = [r for r in history if r["kind"] == "effect" and r["id"] == FX_COMPLETE_WORK]
        self.assertEqual(len(complete_effects), 1)
        self.assertNotIn("error", complete_effects[0]["data"]["dispatch_result"])


if __name__ == "__main__":
    unittest.main()
