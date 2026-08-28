"""SCN-004 -- attempt budget exhausted: a fourth Execution is not
dispatched, Work transitions to BLOCKED via `DEC-BLOCK`, `FX-BLOCK-WORK`/
`FACT-WORK-BLOCKED` is recorded (`docs/scenarios/SCN-004-attempt-
budget.md`). Verifies INV-018, INV-019.
"""

from __future__ import annotations

import unittest

from orc_werk.core.decisions import DEC_BLOCK
from orc_werk.core.effects import FX_BLOCK_WORK
from orc_werk.core.state import STATE_BLOCKED

from tests.scenarios.support import build_run

DRID = "scn004"
WORK_ID = "A"
MAX_ATTEMPTS = 3


class Scn004AttemptBudgetTest(unittest.TestCase):
    def test_no_fourth_dispatch_and_blocked(self) -> None:
        orchestrator, journal, _work_graph = build_run(
            delivery_run_id=DRID,
            attempts_by_work={WORK_ID: [{"outcome": "failed"} for _ in range(MAX_ATTEMPTS)]},
            max_attempts=MAX_ATTEMPTS,
        )
        projection = orchestrator.run()
        wp = projection.works[WORK_ID]

        self.assertEqual(wp.state, STATE_BLOCKED)
        self.assertTrue(wp.blocked_confirmed)
        self.assertEqual(wp.attempt_number, MAX_ATTEMPTS)
        self.assertEqual(len(wp.executions), MAX_ATTEMPTS)

        history = journal.history(delivery_run_id=DRID)
        exec_started = [r for r in history if r["kind"] == "fact" and r["id"] == "FACT-EXEC-STARTED"]
        self.assertEqual(len(exec_started), MAX_ATTEMPTS)

        block_decisions = [r for r in history if r["kind"] == "decision" and r["id"] == DEC_BLOCK]
        self.assertEqual(len(block_decisions), 1)
        block_effects = [r for r in history if r["kind"] == "effect" and r["id"] == FX_BLOCK_WORK]
        self.assertEqual(len(block_effects), 1)
        block_facts = [r for r in history if r["kind"] == "fact" and r["id"] == "FACT-WORK-BLOCKED"]
        self.assertEqual(len(block_facts), 1)
        self.assertEqual(block_facts[0]["data"]["reason"], "retry-budget-exhausted")


if __name__ == "__main__":
    unittest.main()
