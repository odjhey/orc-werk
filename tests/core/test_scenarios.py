"""Golden-scenario fact sequences through the core reducer/policy.

SCN-001 (happy path) and SCN-004 (attempt budget exhausted) drive the
reducer tests per TASK-M0-001's acceptance criteria; the full scenarios
(exercised through the app/CLI surface) belong to TASK-M0-005 /
tests/scenarios/.
"""

from __future__ import annotations

import unittest

from orc_werk.core.decisions import DEC_ACCEPT, DEC_BLOCK, DEC_DISPATCH
from orc_werk.core.effects import FX_COMPLETE_WORK
from orc_werk.core.errors import CoreError
from orc_werk.core.facts import FACT_EXEC_STARTED, make_fact
from orc_werk.core.policy import decide
from orc_werk.core.reducer import reduce
from orc_werk.core.state import STATE_ACCEPTED, STATE_BLOCKED

from tests.core import fixtures

DRID = "dr-scn"


class Scn001HappyPathTest(unittest.TestCase):
    """SCN-001: Work A dispatched once, one Execution retained, Candidate C1's
    exact fingerprint carried through to accepted assurance, completion only
    after acceptance."""

    def test_terminal_accepted(self) -> None:
        facts = fixtures.happy_path_facts(delivery_run_id=DRID, work_id="A")
        proj = reduce(facts, delivery_run_id=DRID)
        wp = proj.works["A"]

        self.assertEqual(wp.state, STATE_ACCEPTED)
        self.assertTrue(wp.completed_confirmed)

        # dispatched once: exactly one FACT-EXEC-STARTED, one retained Execution.
        exec_started = [f for f in facts if f.id == FACT_EXEC_STARTED]
        self.assertEqual(len(exec_started), 1)
        self.assertEqual(wp.attempt_number, 1)
        self.assertEqual(len(wp.executions), 1)

        # Candidate C1's exact fingerprint carried through to assurance evidence.
        self.assertEqual(wp.current_candidate_fingerprint(), "fp-c1")
        self.assertEqual(wp.assurances[-1]["verdict"], "accepted")

        # completion only after acceptance -- decide() must have offered
        # DEC-ACCEPT/FX-COMPLETE-WORK immediately before FACT-WORK-COMPLETED.
        pre_completion = reduce(facts[:-1], delivery_run_id=DRID).works["A"]
        outcome = decide(pre_completion)
        assert outcome is not None
        self.assertEqual(outcome.decision.id, DEC_ACCEPT)
        self.assertEqual([e.id for e in outcome.effects], [FX_COMPLETE_WORK])

    def test_single_dispatch(self) -> None:
        facts = fixtures.created_and_ready(delivery_run_id=DRID, work_id="A")
        wp = reduce(facts, delivery_run_id=DRID).works["A"]
        outcome = decide(wp)
        assert outcome is not None
        self.assertEqual(outcome.decision.id, DEC_DISPATCH)
        self.assertEqual(outcome.decision.data["attempt_number"], 1)


class Scn004AttemptBudgetTest(unittest.TestCase):
    """SCN-004: max_attempts=3, three failing executions -> no 4th dispatch,
    DEC-BLOCK, BLOCKED."""

    MAX_ATTEMPTS = 3

    def test_blocked_after_three_failures(self) -> None:
        facts = fixtures.attempt_budget_exhausted_facts(
            delivery_run_id=DRID, work_id="A", max_attempts=self.MAX_ATTEMPTS
        )
        proj = reduce(facts, delivery_run_id=DRID, max_attempts=self.MAX_ATTEMPTS)
        wp = proj.works["A"]

        self.assertEqual(wp.state, STATE_BLOCKED)
        self.assertTrue(wp.blocked_confirmed)
        self.assertEqual(wp.blocked_reason, "retry-budget-exhausted")
        self.assertEqual(wp.attempt_number, self.MAX_ATTEMPTS)

        exec_started = [f for f in facts if f.id == FACT_EXEC_STARTED]
        self.assertEqual(len(exec_started), self.MAX_ATTEMPTS)

    def test_no_fourth_dispatch(self) -> None:
        facts = fixtures.attempt_budget_exhausted_facts(
            delivery_run_id=DRID, work_id="A", max_attempts=self.MAX_ATTEMPTS
        )
        # drop the trailing FACT-WORK-BLOCKED to inspect the pending decision.
        pre_block = reduce(facts[:-1], delivery_run_id=DRID, max_attempts=self.MAX_ATTEMPTS).works["A"]
        outcome = decide(pre_block, max_attempts=self.MAX_ATTEMPTS)
        assert outcome is not None
        self.assertEqual(outcome.decision.id, DEC_BLOCK)

        # a 4th FACT-EXEC-STARTED must be structurally rejected (INV-018/019).
        fourth = make_fact(FACT_EXEC_STARTED, delivery_run_id=DRID, work_id="A", execution_id="e4")
        with self.assertRaises(CoreError):
            reduce(facts[:-1] + [fourth], delivery_run_id=DRID, max_attempts=self.MAX_ATTEMPTS)


if __name__ == "__main__":
    unittest.main()
