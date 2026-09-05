"""Invariant tests: INV-003, INV-004, INV-009, INV-011/012, INV-018/019, INV-020."""

from __future__ import annotations

import unittest

from orc_werk.core.errors import CoreError
from orc_werk.core.facts import FACT_EXEC_SETTLED, FACT_EXEC_STARTED, make_fact
from orc_werk.core.idempotency import idempotency_key
from orc_werk.core.policy import decide
from orc_werk.core.reducer import reduce
from orc_werk.core.state import STATE_ACCEPTED, STATE_ASSURING, STATE_BLOCKED, STATE_EXECUTING

from tests.core import fixtures

DRID = "dr-inv"


class Inv003ExecutionSettlementIsNotAcceptanceTest(unittest.TestCase):
    """INV-003: an Execution reaching a successful terminal outcome MUST NOT
    by itself mark Work accepted."""

    def test_settled_completed_alone_does_not_accept(self) -> None:
        facts = fixtures.dispatched(delivery_run_id=DRID, work_id="w1", execution_id="e1")
        facts.append(
            make_fact(
                FACT_EXEC_SETTLED, delivery_run_id=DRID, work_id="w1", execution_id="e1", outcome="completed"
            )
        )
        wp = reduce(facts, delivery_run_id=DRID).works["w1"]
        self.assertEqual(wp.state, STATE_EXECUTING)
        self.assertNotEqual(wp.state, STATE_ACCEPTED)

    def test_candidate_without_assurance_does_not_accept(self) -> None:
        facts = fixtures.settled_completed_with_candidate(
            delivery_run_id=DRID, work_id="w1", execution_id="e1", candidate_id="c1", fingerprint="fp1"
        )
        wp = reduce(facts, delivery_run_id=DRID).works["w1"]
        self.assertEqual(wp.state, STATE_ASSURING)
        self.assertNotEqual(wp.state, STATE_ACCEPTED)


class Inv004RetryCreatesNewExecutionIdentityTest(unittest.TestCase):
    """INV-004: a retry MUST create a new Execution identity; historical
    Executions MUST NOT be overwritten."""

    def test_execution_id_reuse_rejected(self) -> None:
        facts = fixtures.dispatched(delivery_run_id=DRID, work_id="w1", execution_id="e1")
        facts.append(fixtures.exec_settled_failed(delivery_run_id=DRID, work_id="w1", execution_id="e1"))
        # reuse "e1" instead of minting a new execution id for the retry.
        reused = make_fact(FACT_EXEC_STARTED, delivery_run_id=DRID, work_id="w1", execution_id="e1")
        with self.assertRaises(CoreError) as ctx:
            reduce(facts + [reused], delivery_run_id=DRID)
        self.assertEqual(ctx.exception.error["error"], "ERR-CONFLICT")

    def test_two_attempts_preserve_both_execution_records(self) -> None:
        facts = fixtures.dispatched(delivery_run_id=DRID, work_id="w1", execution_id="e1")
        facts.append(fixtures.exec_settled_failed(delivery_run_id=DRID, work_id="w1", execution_id="e1"))
        facts.append(make_fact(FACT_EXEC_STARTED, delivery_run_id=DRID, work_id="w1", execution_id="e2"))
        wp = reduce(facts, delivery_run_id=DRID).works["w1"]
        execution_ids = [item["execution_id"] for item in wp.executions]
        self.assertEqual(execution_ids, ["e1", "e2"])
        # e1's outcome remains recorded, unmodified by e2's existence.
        self.assertEqual(wp.executions[0]["outcome"], "failed")


class Inv009RejectedInconclusiveNotAcceptanceTest(unittest.TestCase):
    """INV-009: rejected and inconclusive MUST NOT satisfy acceptance."""

    def _settle(self, verdict: str, *, max_attempts: int = 10, max_assurance_attempts: int = 1):
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
                delivery_run_id=DRID, work_id="w1", assurance_id="a1", fingerprint="fp1", verdict=verdict
            )
        )
        return reduce(
            facts,
            delivery_run_id=DRID,
            max_attempts=max_attempts,
            max_assurance_attempts=max_assurance_attempts,
        ).works["w1"]

    def test_rejected_does_not_accept(self) -> None:
        wp = self._settle("rejected")
        self.assertNotEqual(wp.state, STATE_ACCEPTED)

    def test_inconclusive_does_not_accept(self) -> None:
        # INV-009 holds at BOTH assurance-budget positions (ADR-0006):
        # exhausted, the Work blocks; within budget, it rests at ASSURING
        # for a bounded re-request. Neither is ACCEPTED -- an inconclusive
        # settlement can never satisfy acceptance.
        exhausted = self._settle("inconclusive", max_assurance_attempts=1)
        self.assertNotEqual(exhausted.state, STATE_ACCEPTED)
        self.assertEqual(exhausted.state, STATE_BLOCKED)
        within_budget = self._settle("inconclusive", max_assurance_attempts=2)
        self.assertNotEqual(within_budget.state, STATE_ACCEPTED)
        self.assertEqual(within_budget.state, STATE_ASSURING)


class Inv011Inv012AttributableDecisionsCiteBasisTest(unittest.TestCase):
    """INV-011: every state-changing action has an attributable Decision.
    INV-012: a Decision cites the facts/state it was based on."""

    def test_every_producible_decision_has_attribution_and_basis(self) -> None:
        cases = [
            fixtures.created_and_ready(delivery_run_id=DRID, work_id="w1"),
            fixtures.settled_completed_with_candidate(
                delivery_run_id=DRID, work_id="w1", execution_id="e1", candidate_id="c1", fingerprint="fp1"
            ),
        ]
        for facts in cases:
            wp = reduce(facts, delivery_run_id=DRID).works["w1"]
            outcome = decide(wp)
            assert outcome is not None
            self.assertTrue(outcome.decision.attribution)
            self.assertTrue(outcome.decision.basis)
            for fact_ref in outcome.decision.basis:
                self.assertIn("id", fact_ref)
                self.assertIn("data", fact_ref)

    def test_mechanical_facts_need_no_decision(self) -> None:
        # FX-CREATE-WORK / FX-IDENTIFY-CANDIDATE are mechanics, not policy
        # choices (INV-011's scoping note): FACT-WORK-CREATED and
        # FACT-CANDIDATE-OBSERVED are folded by the reducer without any
        # Decision object required to justify them.
        facts = fixtures.settled_completed_with_candidate(
            delivery_run_id=DRID, work_id="w1", execution_id="e1", candidate_id="c1", fingerprint="fp1"
        )
        # no exception folding these mechanical facts with no Decision involved.
        reduce(facts, delivery_run_id=DRID)


class Inv018Inv019RetryBudgetTest(unittest.TestCase):
    """INV-018: attempt_number is cumulative per Work lineage, first=1,
    reconstructable as the count of execution-start facts.
    INV-019: retry is bounded."""

    def test_attempt_number_is_cumulative_and_matches_exec_started_count(self) -> None:
        facts = fixtures.attempt_budget_exhausted_facts(delivery_run_id=DRID, work_id="w1", max_attempts=3)
        wp = reduce(facts, delivery_run_id=DRID, max_attempts=3).works["w1"]
        exec_started_count = sum(1 for f in facts if f.id == FACT_EXEC_STARTED)
        self.assertEqual(wp.attempt_number, exec_started_count)
        self.assertEqual(wp.attempt_number, 3)

    def test_first_attempt_number_is_one(self) -> None:
        facts = fixtures.dispatched(delivery_run_id=DRID, work_id="w1", execution_id="e1")
        wp = reduce(facts, delivery_run_id=DRID).works["w1"]
        self.assertEqual(wp.attempt_number, 1)

    def test_retry_bounded_rejects_exceeding_budget(self) -> None:
        facts = fixtures.attempt_budget_exhausted_facts(delivery_run_id=DRID, work_id="w1", max_attempts=2)
        fourth = make_fact(FACT_EXEC_STARTED, delivery_run_id=DRID, work_id="w1", execution_id="e3")
        with self.assertRaises(CoreError):
            reduce(facts[:-1] + [fourth], delivery_run_id=DRID, max_attempts=2)


class Inv020IdempotencyKeyDerivationTest(unittest.TestCase):
    """INV-020: deterministic key forms per effect, no randomness/time."""

    def test_fx_create_work_key_form(self) -> None:
        key = idempotency_key("FX-CREATE-WORK", delivery_run_id="dr1")
        self.assertEqual(key, "dr1|FX-CREATE-WORK")

    def test_fx_claim_work_reduced_key_form(self) -> None:
        # INV-020: FX-CLAIM-WORK is once per Work lineage -- keyed on the
        # reduced form (delivery_run_id, work_id, effect_id), with no
        # attempt_number component (analogous to FX-CREATE-WORK's reduced
        # form).
        key = idempotency_key("FX-CLAIM-WORK", delivery_run_id="dr1", work_id="w1")
        self.assertEqual(key, "dr1|w1|FX-CLAIM-WORK")

    def test_standard_tuple_effects(self) -> None:
        for effect_id in (
            "FX-START-EXECUTION",
            "FX-SEND-EXECUTION",
            "FX-CANCEL-EXECUTION",
            "FX-IDENTIFY-CANDIDATE",
            "FX-COMPLETE-WORK",
            "FX-BLOCK-WORK",
        ):
            key = idempotency_key(effect_id, delivery_run_id="dr1", work_id="w1", attempt_number=2)
            self.assertEqual(key, f"dr1|w1|2|{effect_id}")

    def test_fx_start_assurance_key_form(self) -> None:
        key = idempotency_key(
            "FX-START-ASSURANCE",
            delivery_run_id="dr1",
            work_id="w1",
            attempt_number=1,
            candidate_fingerprint="fp-abc",
        )
        self.assertEqual(key, "dr1|w1|1|FX-START-ASSURANCE|fp-abc")

    def test_deterministic_across_repeated_calls(self) -> None:
        args = dict(delivery_run_id="dr1", work_id="w1", attempt_number=3)
        self.assertEqual(
            idempotency_key("FX-START-EXECUTION", **args),
            idempotency_key("FX-START-EXECUTION", **args),
        )

    def test_replay_reproduces_identical_keys(self) -> None:
        # Simulate replay: derive keys from a reduced projection twice and
        # confirm the resulting Effect idempotency_keys are identical.
        facts = fixtures.created_and_ready(delivery_run_id=DRID, work_id="w1")
        wp1 = reduce(facts, delivery_run_id=DRID).works["w1"]
        wp2 = reduce(list(facts), delivery_run_id=DRID).works["w1"]
        outcome1 = decide(wp1)
        outcome2 = decide(wp2)
        assert outcome1 is not None and outcome2 is not None
        self.assertEqual(outcome1.effects[0].idempotency_key, outcome2.effects[0].idempotency_key)

    def test_every_producible_effect_carries_idempotency_key(self) -> None:
        for facts in (
            fixtures.created_and_ready(delivery_run_id=DRID, work_id="w1"),
            fixtures.settled_completed_with_candidate(
                delivery_run_id=DRID, work_id="w1", execution_id="e1", candidate_id="c1", fingerprint="fp1"
            ),
            fixtures.happy_path_facts(delivery_run_id=DRID, work_id="w1")[:-1],
        ):
            wp = reduce(facts, delivery_run_id=DRID).works["w1"]
            outcome = decide(wp)
            if outcome is None:
                continue
            for effect in outcome.effects:
                self.assertTrue(effect.idempotency_key)


if __name__ == "__main__":
    unittest.main()
