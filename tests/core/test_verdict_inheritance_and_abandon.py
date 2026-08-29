"""SCN-009 (verdict inheritance) / SCN-010 (abandoned-attempt recovery)
(`TASK-M3B-001`, issues #76/#95): reducer-level coverage of `STATE-DELIVERY`
mechanical fact sequencing items 8 and 9.

Mutation honesty: every "resolves without ERR-CONFLICT" assertion below
fails on `master` (pre-`TASK-M3B-001`), where a re-observed `candidate_id`
raises `ERR-CONFLICT` unconditionally and `FACT-ATTEMPT-ABANDONED` is not a
known fact id at all.
"""

from __future__ import annotations

import unittest

from orc_werk.core.decisions import DEC_ABANDON_ATTEMPT, DEC_BLOCK, DEC_RETRY
from orc_werk.core.effects import FX_BLOCK_WORK, FX_START_EXECUTION
from orc_werk.core.errors import CoreError
from orc_werk.core.facts import FACT_ATTEMPT_ABANDONED, FACT_EXEC_STARTED, make_fact
from orc_werk.core.policy import decide
from orc_werk.core.reducer import apply_fact, reduce
from orc_werk.core.state import (
    STATE_ACCEPTED,
    STATE_ASSURING,
    STATE_BLOCKED,
    STATE_EXECUTING,
    STATE_READY,
    replace_projection,
)

from tests.core import fixtures

DRID = "dr-inheritance-abandon"


def _rejected_then_retried_facts(*, work_id: str = "w1"):
    """Attempt 1: Candidate C1 (fp-c1) rejected. Attempt 2: the exact same
    Candidate C1 re-produced (identical `candidate_id`/`fingerprint`) by a
    new Execution `e2` -- the fix-69-status-resolver/trivia-sweep specimen
    shape (an unchanged worktree re-executed after a rejection)."""
    facts = fixtures.assuring(
        delivery_run_id=DRID,
        work_id=work_id,
        execution_id="e1",
        candidate_id="c1",
        fingerprint="fp-c1",
        assurance_id="a1",
    )
    facts.append(
        fixtures.assure_settled(
            delivery_run_id=DRID, work_id=work_id, assurance_id="a1", fingerprint="fp-c1", verdict="rejected"
        )
    )
    # DEC-RETRY (budget permitting) returns the Work to READY; attempt 2 starts.
    facts.append(make_fact(FACT_EXEC_STARTED, delivery_run_id=DRID, work_id=work_id, execution_id="e2"))
    facts.append(
        make_fact("FACT-EXEC-SETTLED", delivery_run_id=DRID, work_id=work_id, execution_id="e2", outcome="completed")
    )
    facts.append(
        make_fact(
            "FACT-CANDIDATE-OBSERVED",
            delivery_run_id=DRID,
            work_id=work_id,
            candidate_id="c1",
            fingerprint="fp-c1",
            execution_id="e2",
        )
    )
    return facts


class RejectedThenInheritedTest(unittest.TestCase):
    """SCN-009 "rejected-then-inherited": item 8's inheritance rule."""

    def test_no_conflict_and_inherits_toward_blocked_when_budget_exhausted(self) -> None:
        facts = _rejected_then_retried_facts()
        # max_attempts=2: attempt 2 (the re-observation) exhausts the budget.
        proj = reduce(facts, delivery_run_id=DRID, max_attempts=2)  # must not raise ERR-CONFLICT.
        wp = proj.works["w1"]
        self.assertEqual(wp.state, STATE_BLOCKED)
        self.assertIsNone(wp.candidate_conflict)
        # No second FACT-ASSURE-SETTLED was fabricated (INV-003): the only
        # settled assurance entry is attempt 1's.
        settled = [a for a in wp.assurances if a.get("verdict") is not None]
        self.assertEqual(len(settled), 1)
        self.assertEqual(settled[0]["assurance_id"], "a1")

        outcome = decide(wp, max_attempts=2)
        assert outcome is not None
        self.assertEqual(outcome.decision.id, DEC_BLOCK)
        self.assertEqual([e.id for e in outcome.effects], [FX_BLOCK_WORK])
        self.assertEqual(outcome.decision.data["reason"], "retry-budget-exhausted")
        # basis cites the INHERITED (attempt-1) settlement (INV-012) --
        # the inherited-settlement basis shape (PROTOCOL-FACTS).
        basis_ids = {item["id"] for item in outcome.decision.basis}
        self.assertEqual(basis_ids, {"FACT-ASSURE-SETTLED"})
        self.assertEqual(outcome.decision.basis[0]["data"]["assurance_id"], "a1")
        self.assertEqual(outcome.decision.basis[0]["data"]["verdict"], "rejected")

    def test_no_conflict_and_inherits_toward_retry_when_budget_available(self) -> None:
        facts = _rejected_then_retried_facts()
        proj = reduce(facts, delivery_run_id=DRID, max_attempts=5)
        wp = proj.works["w1"]
        self.assertEqual(wp.state, STATE_READY)
        self.assertTrue(wp.ready_confirmed)  # INV-015 persists across retries (item 2).

        outcome = decide(wp, max_attempts=5)
        assert outcome is not None
        self.assertEqual(outcome.decision.id, DEC_RETRY)
        self.assertEqual([e.id for e in outcome.effects], [FX_START_EXECUTION])

    def test_replay_is_deterministic_across_repeated_reads(self) -> None:
        facts = _rejected_then_retried_facts()
        proj1 = reduce(facts, delivery_run_id=DRID, max_attempts=2)
        proj2 = reduce(facts, delivery_run_id=DRID, max_attempts=2)
        self.assertEqual(proj1.to_dict(), proj2.to_dict())


class AcceptedThenReobservedTest(unittest.TestCase):
    """SCN-009 "accepted-then-reobserved": defensive white-box coverage of
    `apply_fact` alone (not the ordinary `reduce()` loop -- ACCEPTED has no
    v0 transition row back to EXECUTING, so this shape cannot arise through
    normal fact sequencing; it exercises the reducer rule directly, as the
    scenario doc's step 6 describes)."""

    def test_reobserving_an_accepted_candidate_is_idempotent_harmless(self) -> None:
        facts = fixtures.assuring(
            delivery_run_id=DRID,
            work_id="w1",
            execution_id="e1",
            candidate_id="c2",
            fingerprint="fp-c2",
            assurance_id="a1",
        )
        facts.append(
            fixtures.assure_settled(
                delivery_run_id=DRID, work_id="w1", assurance_id="a1", fingerprint="fp-c2", verdict="accepted"
            )
        )
        accepted_wp = reduce(facts, delivery_run_id=DRID).works["w1"]
        self.assertEqual(accepted_wp.state, STATE_ACCEPTED)

        # Simulate a hand-constructed/corrective-run re-observation of the
        # same candidate against a fresh Execution e2 (bypassing the
        # ordinary reduce() sequencing, which the scenario doc notes never
        # produces this shape on its own).
        conflict_free_wp = replace_projection(
            accepted_wp,
            state=STATE_EXECUTING,
            current_execution_id="e2",
            executions=accepted_wp.executions
            + ({"execution_id": "e2", "outcome": "completed", "settled_fact": None},),
        )
        reobserved = make_fact(
            "FACT-CANDIDATE-OBSERVED",
            delivery_run_id=DRID,
            work_id="w1",
            candidate_id="c2",
            fingerprint="fp-c2",
            execution_id="e2",
        )
        wp = apply_fact(conflict_free_wp, reobserved, max_attempts=3)  # must not raise.
        self.assertEqual(wp.state, STATE_ACCEPTED)
        self.assertIsNone(wp.candidate_conflict)
        settled = [a for a in wp.assurances if a.get("verdict") is not None]
        self.assertEqual(len(settled), 1)  # still exactly one real acceptance (INV-003).


class AbandonCandidateConflictShapeTest(unittest.TestCase):
    """SCN-010 candidate-observation-conflict shape: a re-observed
    candidate with nothing settled to inherit rests at EXECUTING,
    conflicted, until DEC-ABANDON-ATTEMPT consumes it."""

    def test_reused_candidate_with_no_settled_verdict_rests_conflicted_not_raised(self) -> None:
        # Attempt 1: candidate observed, assurance started, never settled.
        facts = fixtures.assuring(
            delivery_run_id=DRID,
            work_id="w1",
            execution_id="e1",
            candidate_id="c1",
            fingerprint="fp-c1",
            assurance_id="a1",
        )
        proj = reduce(facts, delivery_run_id=DRID, max_attempts=2)
        wp = proj.works["w1"]
        self.assertEqual(wp.state, STATE_ASSURING)

        # Operator abandons the unsettleable assurance (issue #95 shape) --
        # attempt 1 of 2 consumed, budget remains: READY.
        abandoned = make_fact(FACT_ATTEMPT_ABANDONED, delivery_run_id=DRID, work_id="w1", reason="orphaned session")
        wp = apply_fact(wp, abandoned, max_attempts=2)
        self.assertEqual(wp.state, STATE_READY)
        self.assertIsNone(wp.candidate_conflict)

        # Attempt 2 re-produces the exact same candidate C1 -- but this
        # time there is nothing settled to inherit from (attempt 1's only
        # assurance record is now "abandoned", not a real verdict).
        wp = apply_fact(wp, make_fact(FACT_EXEC_STARTED, delivery_run_id=DRID, work_id="w1", execution_id="e2"), max_attempts=2)
        wp = apply_fact(
            wp,
            make_fact("FACT-EXEC-SETTLED", delivery_run_id=DRID, work_id="w1", execution_id="e2", outcome="completed"),
            max_attempts=2,
        )
        reobserved = make_fact(
            "FACT-CANDIDATE-OBSERVED",
            delivery_run_id=DRID,
            work_id="w1",
            candidate_id="c1",
            fingerprint="fp-c1",
            execution_id="e2",
        )
        wp = apply_fact(wp, reobserved, max_attempts=2)  # must not raise ERR-CONFLICT.
        self.assertEqual(wp.state, STATE_EXECUTING)
        self.assertIsNotNone(wp.candidate_conflict)
        self.assertEqual(wp.candidate_conflict["candidate_id"], "c1")
        self.assertEqual(wp.candidate_conflict["reason"], "no-inheritable-verdict")
        # decide() has no row for a conflicted EXECUTING Work -- no silent progress.
        self.assertIsNone(decide(wp, max_attempts=2))

        # Second abandon consumes the conflict; attempt 2 of 2 now
        # exhausted: BLOCKED, reason attempt-abandoned.
        abandoned_2 = make_fact(FACT_ATTEMPT_ABANDONED, delivery_run_id=DRID, work_id="w1", reason="identity collision")
        wp = apply_fact(wp, abandoned_2, max_attempts=2)
        self.assertEqual(wp.state, STATE_BLOCKED)
        self.assertIsNone(wp.candidate_conflict)

        outcome = decide(wp, max_attempts=2)
        assert outcome is not None
        self.assertEqual(outcome.decision.id, DEC_BLOCK)
        self.assertEqual(outcome.decision.data["reason"], "attempt-abandoned")


class AbandonUnsettleableAssuranceShapeTest(unittest.TestCase):
    """SCN-010 unsettleable-assurance shape (#95): a started Assurance
    that never settles rests at ASSURING (ordinary `is_pending`); the
    operator's out-of-band judgment that it never will settle makes
    DEC-ABANDON-ATTEMPT legal from that same rest."""

    def test_abandon_from_pending_assurance_retries_honestly(self) -> None:
        facts = fixtures.assuring(
            delivery_run_id=DRID,
            work_id="w1",
            execution_id="e1",
            candidate_id="c2",
            fingerprint="fp-c2",
            assurance_id="a1",
        )
        wp = reduce(facts, delivery_run_id=DRID, max_attempts=3).works["w1"]
        self.assertEqual(wp.state, STATE_ASSURING)

        abandoned = make_fact(FACT_ATTEMPT_ABANDONED, delivery_run_id=DRID, work_id="w1", reason="adapter orphaned")
        wp = apply_fact(wp, abandoned, max_attempts=3)
        self.assertEqual(wp.state, STATE_READY)
        # No FACT-ASSURE-SETTLED was ever fabricated for c2 (INV-003/INV-009).
        self.assertTrue(all(a.get("verdict") in (None, "abandoned") for a in wp.assurances))

        outcome = decide(wp, max_attempts=3)
        assert outcome is not None
        self.assertEqual(outcome.decision.id, DEC_RETRY)


class AbandonIllegalTest(unittest.TestCase):
    """DEC-ABANDON-ATTEMPT/FACT-ATTEMPT-ABANDONED is legal *exactly* when
    STATE-DELIVERY item 9 applies -- nowhere else."""

    def test_abandon_illegal_from_ordinary_ready(self) -> None:
        wp = reduce(fixtures.created_and_ready(delivery_run_id=DRID, work_id="w1"), delivery_run_id=DRID).works["w1"]
        abandoned = make_fact(FACT_ATTEMPT_ABANDONED, delivery_run_id=DRID, work_id="w1", reason="nope")
        with self.assertRaises(CoreError):
            apply_fact(wp, abandoned, max_attempts=3)

    def test_abandon_illegal_from_ordinary_pending_execution(self) -> None:
        wp = reduce(
            fixtures.dispatched(delivery_run_id=DRID, work_id="w1", execution_id="e1"), delivery_run_id=DRID
        ).works["w1"]
        self.assertEqual(wp.state, STATE_EXECUTING)
        self.assertIsNone(wp.candidate_conflict)  # ordinary pending, not conflicted.
        abandoned = make_fact(FACT_ATTEMPT_ABANDONED, delivery_run_id=DRID, work_id="w1", reason="nope")
        with self.assertRaises(CoreError):
            apply_fact(wp, abandoned, max_attempts=3)


if __name__ == "__main__":
    unittest.main()
