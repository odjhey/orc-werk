"""Reducer transition-table coverage (STATE-DELIVERY).

Every row of the v0/M0 transition table, including the budget-available vs
budget-exhausted split (INV-018/INV-019), plus proof that the reserved
FAILED/CANCELLED states and DEC-ESCALATE/DEC-CANCEL/FX-NOTIFY-OPERATOR are
unreachable through the reducer/policy.
"""

from __future__ import annotations

import unittest

from orc_werk.core.decisions import DEC_ACCEPT, DEC_BLOCK, DEC_DISPATCH, DEC_REQUEST_ASSURANCE, DEC_RETRY
from orc_werk.core.effects import FX_BLOCK_WORK, FX_COMPLETE_WORK, FX_START_ASSURANCE, FX_START_EXECUTION
from orc_werk.core.errors import CoreError
from orc_werk.core.facts import (
    FACT_ASSURE_STARTED,
    FACT_EXEC_STARTED,
    FACT_WORK_CANCELLED,
    FACT_WORK_CLAIMED,
    make_fact,
)
from orc_werk.core.policy import decide
from orc_werk.core.reducer import apply_fact, reduce
from orc_werk.core.state import (
    STATE_ACCEPTED,
    STATE_ASSURING,
    STATE_BLOCKED,
    STATE_CANCELLED,
    STATE_EXECUTING,
    STATE_FAILED,
    STATE_READY,
)

from tests.core import fixtures

DRID = "dr-transitions"


class ReadyToExecutingTest(unittest.TestCase):
    """READY | FACT-WORK-READY | DEC-DISPATCH | EXECUTING | FX-START-EXECUTION."""

    def test_dispatch_on_ready(self) -> None:
        facts = fixtures.created_and_ready(delivery_run_id=DRID, work_id="w1")
        proj = reduce(facts, delivery_run_id=DRID)
        wp = proj.works["w1"]
        self.assertEqual(wp.state, STATE_READY)
        self.assertTrue(wp.ready_confirmed)

        outcome = decide(wp)
        assert outcome is not None
        self.assertEqual(outcome.decision.id, DEC_DISPATCH)
        self.assertEqual([e.id for e in outcome.effects], [FX_START_EXECUTION])

        facts.append(make_fact(FACT_EXEC_STARTED, delivery_run_id=DRID, work_id="w1", execution_id="e1"))
        proj = reduce(facts, delivery_run_id=DRID)
        self.assertEqual(proj.works["w1"].state, STATE_EXECUTING)


class ReadyClaimTest(unittest.TestCase):
    """READY | FACT-WORK-CLAIMED | (no policy Decision) | READY, claim_ref recorded.

    PORT-WORK-004 `claim` is orchestration/execution bookkeeping, not a
    STATE-DELIVERY transition row: it is legal only from READY, does not
    move the Work to a different state, and simply records `claim_ref` on
    the projection (imported by fixtures.py but previously exercised by no
    test -- P1 review nit)."""

    def test_claim_from_ready_is_non_transitioning_and_records_claim_ref(self) -> None:
        facts = fixtures.created_and_ready(delivery_run_id=DRID, work_id="w1")
        facts.append(
            make_fact(FACT_WORK_CLAIMED, delivery_run_id=DRID, work_id="w1", claim_ref="claim-1")
        )
        proj = reduce(facts, delivery_run_id=DRID)
        wp = proj.works["w1"]
        self.assertEqual(wp.state, STATE_READY)
        self.assertEqual(wp.claim_ref, "claim-1")

    def test_claim_illegal_outside_ready(self) -> None:
        facts = fixtures.dispatched(delivery_run_id=DRID, work_id="w1", execution_id="e1")
        claimed = make_fact(FACT_WORK_CLAIMED, delivery_run_id=DRID, work_id="w1", claim_ref="claim-1")
        with self.assertRaises(CoreError):
            reduce(facts + [claimed], delivery_run_id=DRID)


class ExecutingToAssuringTest(unittest.TestCase):
    """EXECUTING | settled(completed)+candidate | DEC-REQUEST-ASSURANCE | ASSURING | FX-START-ASSURANCE."""

    def test_request_assurance_once_candidate_observed(self) -> None:
        facts = fixtures.settled_completed_with_candidate(
            delivery_run_id=DRID, work_id="w1", execution_id="e1", candidate_id="c1", fingerprint="fp1"
        )
        proj = reduce(facts, delivery_run_id=DRID)
        wp = proj.works["w1"]
        self.assertEqual(wp.state, STATE_ASSURING)

        outcome = decide(wp)
        assert outcome is not None
        self.assertEqual(outcome.decision.id, DEC_REQUEST_ASSURANCE)
        self.assertEqual([e.id for e in outcome.effects], [FX_START_ASSURANCE])
        # basis cites both the settlement and the candidate observation (INV-012).
        basis_ids = {item["id"] for item in outcome.decision.basis}
        self.assertEqual(basis_ids, {"FACT-EXEC-SETTLED", "FACT-CANDIDATE-OBSERVED"})


class ExecutingFailedTest(unittest.TestCase):
    """EXECUTING | settled(failed) | DEC-RETRY/DEC-BLOCK | READY/BLOCKED | FX-START-EXECUTION/FX-BLOCK-WORK."""

    def test_retry_when_budget_available(self) -> None:
        facts = fixtures.dispatched(delivery_run_id=DRID, work_id="w1", execution_id="e1")
        facts.append(fixtures.exec_settled_failed(delivery_run_id=DRID, work_id="w1", execution_id="e1"))
        proj = reduce(facts, delivery_run_id=DRID, max_attempts=3)
        wp = proj.works["w1"]
        self.assertEqual(wp.state, STATE_READY)

        outcome = decide(wp, max_attempts=3)
        assert outcome is not None
        self.assertEqual(outcome.decision.id, DEC_RETRY)
        self.assertEqual([e.id for e in outcome.effects], [FX_START_EXECUTION])

    def test_block_when_budget_exhausted(self) -> None:
        facts = fixtures.dispatched(delivery_run_id=DRID, work_id="w1", execution_id="e1")
        facts.append(fixtures.exec_settled_failed(delivery_run_id=DRID, work_id="w1", execution_id="e1"))
        proj = reduce(facts, delivery_run_id=DRID, max_attempts=1)
        wp = proj.works["w1"]
        self.assertEqual(wp.state, STATE_BLOCKED)

        outcome = decide(wp, max_attempts=1)
        assert outcome is not None
        self.assertEqual(outcome.decision.id, DEC_BLOCK)
        self.assertEqual([e.id for e in outcome.effects], [FX_BLOCK_WORK])


class AssuringAcceptedTest(unittest.TestCase):
    """ASSURING | settled(accepted) | DEC-ACCEPT | ACCEPTED | FX-COMPLETE-WORK."""

    def test_accept(self) -> None:
        facts = fixtures.assuring(
            delivery_run_id=DRID,
            work_id="w1",
            execution_id="e1",
            candidate_id="c1",
            fingerprint="fp1",
            assurance_id="a1",
        )
        facts.append(
            fixtures.assure_settled(
                delivery_run_id=DRID, work_id="w1", assurance_id="a1", fingerprint="fp1", verdict="accepted"
            )
        )
        proj = reduce(facts, delivery_run_id=DRID)
        wp = proj.works["w1"]
        self.assertEqual(wp.state, STATE_ACCEPTED)

        outcome = decide(wp)
        assert outcome is not None
        self.assertEqual(outcome.decision.id, DEC_ACCEPT)
        self.assertEqual([e.id for e in outcome.effects], [FX_COMPLETE_WORK])


class AssuringRejectedTest(unittest.TestCase):
    """ASSURING | settled(rejected) | DEC-RETRY/DEC-BLOCK | READY/BLOCKED."""

    def _rejected_projection(self, *, max_attempts: int):
        facts = fixtures.assuring(
            delivery_run_id=DRID,
            work_id="w1",
            execution_id="e1",
            candidate_id="c1",
            fingerprint="fp1",
            assurance_id="a1",
        )
        facts.append(
            fixtures.assure_settled(
                delivery_run_id=DRID, work_id="w1", assurance_id="a1", fingerprint="fp1", verdict="rejected"
            )
        )
        return reduce(facts, delivery_run_id=DRID, max_attempts=max_attempts).works["w1"]

    def test_retry_when_budget_available(self) -> None:
        wp = self._rejected_projection(max_attempts=3)
        self.assertEqual(wp.state, STATE_READY)
        outcome = decide(wp, max_attempts=3)
        assert outcome is not None
        self.assertEqual(outcome.decision.id, DEC_RETRY)
        self.assertEqual([e.id for e in outcome.effects], [FX_START_EXECUTION])

    def test_block_when_budget_exhausted(self) -> None:
        wp = self._rejected_projection(max_attempts=1)
        self.assertEqual(wp.state, STATE_BLOCKED)
        outcome = decide(wp, max_attempts=1)
        assert outcome is not None
        self.assertEqual(outcome.decision.id, DEC_BLOCK)
        self.assertEqual([e.id for e in outcome.effects], [FX_BLOCK_WORK])


class AssuringInconclusiveTest(unittest.TestCase):
    """ASSURING | settled(inconclusive), assurance budget exhausted |
    DEC-BLOCK | BLOCKED | FX-BLOCK-WORK -- and the RETRY budget is never
    what decides it (STATE-DELIVERY's two `inconclusive` rows, INV-021).

    Restated for `ADR-0006` (issue #264): this test previously asserted
    that an `inconclusive` settlement blocks unconditionally. It still
    blocks under the same retry-budget-irrelevance the original test
    named -- what changed is that the ASSURANCE budget now decides when.
    Both budget positions are covered: `max_assurance_attempts=1` (the
    pre-ADR-0006 budget, and the read-fallback every legacy journal folds
    under) and the default `2` after a second inconclusive settlement."""

    def _inconclusive_facts(self, *, second: bool = False) -> list:
        facts = fixtures.assuring(
            delivery_run_id=DRID,
            work_id="w1",
            execution_id="e1",
            candidate_id="c1",
            fingerprint="fp1",
            assurance_id="a1",
        )
        facts.append(
            fixtures.assure_settled(
                delivery_run_id=DRID, work_id="w1", assurance_id="a1", fingerprint="fp1", verdict="inconclusive"
            )
        )
        if second:
            facts.append(
                make_fact(
                    FACT_ASSURE_STARTED,
                    delivery_run_id=DRID,
                    work_id="w1",
                    assurance_id="a2",
                    candidate_id="c1",
                )
            )
            facts.append(
                fixtures.assure_settled(
                    delivery_run_id=DRID,
                    work_id="w1",
                    assurance_id="a2",
                    fingerprint="fp1",
                    verdict="inconclusive",
                )
            )
        return facts

    def _assert_blocks(self, wp) -> None:
        self.assertEqual(wp.state, STATE_BLOCKED)
        outcome = decide(wp, max_attempts=10)
        assert outcome is not None
        self.assertEqual(outcome.decision.id, DEC_BLOCK)
        self.assertEqual([e.id for e in outcome.effects], [FX_BLOCK_WORK])
        self.assertEqual(outcome.decision.data["reason"], "assurance-inconclusive")

    def test_block_regardless_of_retry_budget_under_assurance_budget_1(self) -> None:
        # plenty of RETRY budget left -- an inconclusive verdict never
        # consumes it, and with the assurance budget at 1 (pre-ADR-0006
        # behavior, and every legacy journal's read-fallback) the very
        # first inconclusive settlement blocks.
        proj = reduce(
            self._inconclusive_facts(),
            delivery_run_id=DRID,
            max_attempts=10,
            max_assurance_attempts=1,
        )
        self._assert_blocks(proj.works["w1"])

    def test_block_regardless_of_retry_budget_after_second_inconclusive(self) -> None:
        # Same row, reached under the default assurance budget of 2 after
        # the bounded re-request also settled inconclusive. attempt_number
        # is still 1: no FACT-EXEC-STARTED was journaled (INV-018/INV-021).
        proj = reduce(self._inconclusive_facts(second=True), delivery_run_id=DRID, max_attempts=10)
        wp = proj.works["w1"]
        self.assertEqual(wp.attempt_number, 1)
        self._assert_blocks(wp)


class ReservedUnreachableTest(unittest.TestCase):
    """FAILED/DEC-ESCALATE/FX-NOTIFY-OPERATOR remain reserved; policy never
    emits operator-only DEC-CANCEL."""

    def test_reducer_never_produces_reserved_states(self) -> None:
        all_states_seen = set()
        for facts in (
            fixtures.happy_path_facts(delivery_run_id=DRID, work_id="w1"),
            fixtures.attempt_budget_exhausted_facts(delivery_run_id=DRID, work_id="w2", max_attempts=3),
        ):
            proj = reduce(facts, delivery_run_id=DRID, max_attempts=3)
            for wp in proj.works.values():
                all_states_seen.add(wp.state)
        self.assertNotIn(STATE_FAILED, all_states_seen)

    def test_fact_work_cancelled_is_reachable(self) -> None:
        facts = fixtures.created_and_ready(delivery_run_id=DRID, work_id="w1")
        projection = reduce(
            facts
            + [
                make_fact(
                    FACT_WORK_CANCELLED,
                    delivery_run_id=DRID,
                    work_id="w1",
                    reason="operator closure",
                )
            ],
            delivery_run_id=DRID,
        )
        self.assertEqual(projection.works["w1"].state, STATE_CANCELLED)
        self.assertTrue(projection.works["w1"].cancelled_confirmed)
        self.assertEqual(projection.works["w1"].cancelled_reason, "operator closure")

    def test_cancel_from_executing_and_assuring_is_clean_terminal(self) -> None:
        paths = (
            fixtures.dispatched(delivery_run_id=DRID, work_id="w1", execution_id="e1"),
            fixtures.assuring(
                delivery_run_id=DRID,
                work_id="w1",
                execution_id="e1",
                candidate_id="c1",
                fingerprint="fp1",
                assurance_id="a1",
            ),
        )
        for facts in paths:
            cancelled = make_fact(
                FACT_WORK_CANCELLED,
                delivery_run_id=DRID,
                work_id="w1",
                reason="stop",
            )
            first = reduce(facts + [cancelled], delivery_run_id=DRID)
            replay = reduce(facts + [cancelled], delivery_run_id=DRID)
            wp = first.works["w1"]
            self.assertEqual(first.to_dict(), replay.to_dict())
            self.assertEqual(wp.state, STATE_CANCELLED)
            self.assertIsNone(wp.current_execution_id)
            self.assertIsNone(wp.current_assurance_id)
            self.assertFalse(wp.assurance_started_for_current)

    def test_cancel_from_terminal_or_twice_conflicts(self) -> None:
        terminal_paths = (
            fixtures.happy_path_facts(delivery_run_id=DRID, work_id="w1"),
            fixtures.attempt_budget_exhausted_facts(
                delivery_run_id=DRID, work_id="w1", max_attempts=3
            ),
        )
        cancelled = make_fact(
            FACT_WORK_CANCELLED,
            delivery_run_id=DRID,
            work_id="w1",
            reason="stop",
        )
        for facts in terminal_paths:
            with self.assertRaises(CoreError) as caught:
                reduce(facts + [cancelled], delivery_run_id=DRID, max_attempts=3)
            self.assertEqual(caught.exception.error["error"], "ERR-CONFLICT")
        ready = fixtures.created_and_ready(delivery_run_id=DRID, work_id="w1")
        with self.assertRaises(CoreError) as caught:
            reduce(ready + [cancelled, cancelled], delivery_run_id=DRID)
        self.assertEqual(caught.exception.error["error"], "ERR-CONFLICT")

    def test_exec_settled_cancelled_has_no_transition_row(self) -> None:
        facts = fixtures.dispatched(delivery_run_id=DRID, work_id="w1", execution_id="e1")
        cancelled = make_fact(
            "FACT-EXEC-SETTLED",
            delivery_run_id=DRID,
            work_id="w1",
            execution_id="e1",
            outcome="cancelled",
        )
        with self.assertRaises(CoreError):
            reduce(facts + [cancelled], delivery_run_id=DRID)

    def test_policy_never_emits_reserved_decisions_or_effects(self) -> None:
        reserved_decisions = {"DEC-ESCALATE", "DEC-CANCEL"}
        reserved_effects = {"FX-NOTIFY-OPERATOR"}
        for facts in (
            fixtures.created_and_ready(delivery_run_id=DRID, work_id="w1"),
            fixtures.dispatched(delivery_run_id=DRID, work_id="w1", execution_id="e1"),
            fixtures.settled_completed_with_candidate(
                delivery_run_id=DRID, work_id="w1", execution_id="e1", candidate_id="c1", fingerprint="fp1"
            ),
            fixtures.assuring(
                delivery_run_id=DRID,
                work_id="w1",
                execution_id="e1",
                candidate_id="c1",
                fingerprint="fp1",
                assurance_id="a1",
            ),
            fixtures.happy_path_facts(delivery_run_id=DRID, work_id="w1"),
            fixtures.attempt_budget_exhausted_facts(delivery_run_id=DRID, work_id="w1", max_attempts=3),
        ):
            proj = reduce(facts, delivery_run_id=DRID, max_attempts=3)
            for wp in proj.works.values():
                outcome = decide(wp, max_attempts=3)
                if outcome is None:
                    continue
                self.assertNotIn(outcome.decision.id, reserved_decisions)
                for effect in outcome.effects:
                    self.assertNotIn(effect.id, reserved_effects)


if __name__ == "__main__":
    unittest.main()
