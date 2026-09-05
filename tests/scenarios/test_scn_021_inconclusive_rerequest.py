"""SCN-021 -- bounded assurance re-request on `inconclusive`
(`docs/scenarios/SCN-021-inconclusive-rerequest.md`, `ADR-0006`, issue
#264): an `inconclusive` assurance settlement re-requests assurance of the
*same* candidate within a bounded assurance budget (`INV-021`); exhausting
that budget blocks the Work with `reason: assurance-inconclusive`; the
execution retry budget (`INV-018`/`INV-019`) is never consumed either way;
and journals written before the budget existed replay unchanged.

One module per the scenario's four Given/Then pairs, plus:

- `CONF-ASSURE-008` (the conformance requirement the scenario verifies);
- `INV-020` key compatibility -- assurance 1 keeps the pre-`INV-021` key
  string verbatim, so every pre-decision journal replays under identical
  keys, and assurance 2 gains the `|2` component (without which the second
  `FX-START-ASSURANCE` would collide with the first and be skipped as
  already applied -- the scenario's own second mutation check);
- `INV-021`'s per-Execution `assurance_number` reconstruction, asserted on
  the reachable abandon path where a candidate-scoped count would be wrong.

Mutation check (`SCN-021`, run by hand for the PR body, not automated
here because reverting a reducer branch is not something a test suite can
assert about itself): reverting `core/reducer.py`'s `FACT-ASSURE-SETTLED`
`inconclusive` branch to the pre-`ADR-0006` unconditional `STATE_BLOCKED`
turns `ReRequestThenAcceptedTest` red -- Work A blocks after assurance 1
and no `DEC-REQUEST-ASSURANCE` is emitted.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping, Sequence

from orc_werk.adapters.jsonl.journal import JSONLJournal
from orc_werk.adapters.memory.journal import MemoryJournal
from orc_werk.core.decisions import DEC_BLOCK, DEC_REQUEST_ASSURANCE, DEC_RETRY, make_decision
from orc_werk.core.effects import FX_BLOCK_WORK, FX_CREATE_WORK, FX_START_ASSURANCE, make_effect
from orc_werk.core.facts import (
    FACT_ASSURE_SETTLED,
    FACT_ASSURE_STARTED,
    FACT_ATTEMPT_ABANDONED,
    FACT_CANDIDATE_OBSERVED,
    FACT_EXEC_SETTLED,
    FACT_EXEC_STARTED,
    FACT_INTENT_SUBMITTED,
    FACT_WORK_BLOCKED,
    FACT_WORK_CREATED,
    FACT_WORK_READY,
    make_fact,
)
from orc_werk.core.idempotency import idempotency_key
from orc_werk.core.policy import decide
from orc_werk.core.reducer import (
    DEFAULT_MAX_ASSURANCE_ATTEMPTS,
    LEGACY_MAX_ASSURANCE_ATTEMPTS,
    journaled_max_assurance_attempts,
    reduce,
)
from orc_werk.core.serialization import KIND_DECISION, KIND_EFFECT, KIND_FACT
from orc_werk.core.state import STATE_ACCEPTED, STATE_ASSURING, STATE_BLOCKED, STATE_READY

from tests.core import fixtures
from tests.scenarios.support import build_run

SRC = str(Path(__file__).resolve().parents[2] / "src")

DRID = "scn021-inconclusive-rerequest"
WORK_ID = "work-1"


def _facts(history: Sequence[Mapping[str, Any]], fact_id: str) -> list[Mapping[str, Any]]:
    return [r for r in history if r["kind"] == KIND_FACT and r["id"] == fact_id]


def _decisions(history: Sequence[Mapping[str, Any]], decision_id: str) -> list[Mapping[str, Any]]:
    return [r for r in history if r["kind"] == KIND_DECISION and r["id"] == decision_id]


def _effects(history: Sequence[Mapping[str, Any]], effect_id: str) -> list[Mapping[str, Any]]:
    return [r for r in history if r["kind"] == KIND_EFFECT and r["id"] == effect_id]


def _run_cli(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "orc_werk.cli", *args],
        cwd=cwd,
        env={"PYTHONPATH": SRC, "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=60,
    )


# ---------------------------------------------------------------------------
# Given (re-request, then accepted) -- SCN-021 items 1-7
# ---------------------------------------------------------------------------


class ReRequestThenAcceptedTest(unittest.TestCase):
    """Work A ready, `max_attempts = 3`, `max_assurance_attempts = 2`;
    execution 1 produces C1; assurance 1 settles `inconclusive`; assurance
    2 settles `accepted`."""

    def _run(self):
        orchestrator, journal, _work_graph = build_run(
            delivery_run_id=DRID,
            attempts_by_work={
                WORK_ID: [
                    {
                        "outcome": "completed",
                        "candidate": {"label": "C1"},
                        "verdicts": ["inconclusive", "accepted"],
                    }
                ]
            },
            max_attempts=3,
            max_assurance_attempts=2,
        )
        projection = orchestrator.run()
        return projection.works[WORK_ID], journal.history(delivery_run_id=DRID)

    def test_item_1_inconclusive_leaves_work_assuring_with_nothing_in_flight(self) -> None:
        # Folded directly, so the resting point item 1 names is observable
        # (the orchestrator advances straight past it in one pass).
        facts = fixtures.assuring(
            delivery_run_id=DRID,
            work_id=WORK_ID,
            execution_id="e1",
            candidate_id="c1",
            fingerprint="fp-1",
            assurance_id="a1",
        )
        facts.append(
            fixtures.assure_settled(
                delivery_run_id=DRID,
                work_id=WORK_ID,
                assurance_id="a1",
                fingerprint="fp-1",
                verdict="inconclusive",
            )
        )
        wp = reduce(
            facts, delivery_run_id=DRID, max_attempts=3, max_assurance_attempts=2
        ).works[WORK_ID]
        self.assertEqual(wp.state, STATE_ASSURING)
        self.assertFalse(wp.assurance_started_for_current)
        self.assertEqual(wp.current_candidate_id, "c1")

    def test_item_2_policy_re_requests_the_same_candidate_citing_the_settlement(self) -> None:
        wp, history = self._run()
        requests = _decisions(history, DEC_REQUEST_ASSURANCE)
        self.assertEqual(len(requests), 2)
        second = requests[1]
        # basis cites the inconclusive FACT-ASSURE-SETTLED (INV-012).
        self.assertEqual([b["id"] for b in second["data"]["basis"]], [FACT_ASSURE_SETTLED])
        self.assertEqual(second["data"]["basis"][0]["data"]["verdict"], "inconclusive")
        # ...for the SAME candidate_id / fingerprint (INV-007).
        started = _effects(history, FX_START_ASSURANCE)
        self.assertEqual(len(started), 2)
        self.assertEqual(
            started[0]["data"]["candidate_id"], started[1]["data"]["candidate_id"]
        )
        self.assertEqual(
            started[0]["data"]["candidate_fingerprint"],
            started[1]["data"]["candidate_fingerprint"],
        )
        self.assertEqual(second["data"]["assurance_number"], 2)

    def test_item_3_second_effect_key_is_the_first_plus_an_assurance_number_component(self) -> None:
        _wp, history = self._run()
        started = _effects(history, FX_START_ASSURANCE)
        first_key = started[0]["data"]["idempotency_key"]
        second_key = started[1]["data"]["idempotency_key"]
        self.assertEqual(second_key, f"{first_key}|2")
        # ...and assurance 1's key is unchanged from the pre-INV-021 form.
        fingerprint = started[0]["data"]["candidate_fingerprint"]
        self.assertEqual(first_key, f"{DRID}|{WORK_ID}|1|{FX_START_ASSURANCE}|{fingerprint}")

    def test_item_4_new_assurance_identity_and_the_first_record_is_retained(self) -> None:
        wp, history = self._run()
        started = _facts(history, FACT_ASSURE_STARTED)
        self.assertEqual(len(started), 2)
        self.assertNotEqual(started[0]["data"]["assurance_id"], started[1]["data"]["assurance_id"])
        settlements = _facts(history, FACT_ASSURE_SETTLED)
        self.assertEqual([r["data"]["verdict"] for r in settlements], ["inconclusive", "accepted"])
        # P-008/INV-007: the first assurance's record is never overwritten
        # or relabelled -- both survive in the projection too.
        self.assertEqual([a["verdict"] for a in wp.assurances], ["inconclusive", "accepted"])

    def test_item_5_attempt_number_stays_1_and_the_retry_budget_is_untouched(self) -> None:
        wp, history = self._run()
        self.assertEqual(wp.attempt_number, 1)
        self.assertEqual(len(_facts(history, FACT_EXEC_STARTED)), 1)
        self.assertEqual(_decisions(history, DEC_RETRY), [])

    def test_item_6_second_settlement_accepts_the_work(self) -> None:
        wp, history = self._run()
        self.assertEqual(wp.state, STATE_ACCEPTED)
        self.assertTrue(wp.completed_confirmed)

    def test_item_7_two_assurance_lifecycles_for_one_candidate_in_one_attempt(self) -> None:
        _wp, history = self._run()
        candidates = _facts(history, FACT_CANDIDATE_OBSERVED)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(len(_facts(history, FACT_ASSURE_STARTED)), 2)

    def test_assurance_number_is_reconstructable_per_execution(self) -> None:
        # INV-021: the reducer tags each assurance entry with the Execution
        # current when it was appended, so the index is derivable from the
        # projection alone.
        wp, history = self._run()
        execution_id = _facts(history, FACT_EXEC_STARTED)[0]["data"]["execution_id"]
        self.assertEqual([a["execution_id"] for a in wp.assurances], [execution_id, execution_id])
        self.assertEqual(wp.assurance_number(), 2)


# ---------------------------------------------------------------------------
# Given (budget exhausted) -- SCN-021 items 8-10
# ---------------------------------------------------------------------------


class BudgetExhaustedTest(unittest.TestCase):
    def _run(self):
        orchestrator, journal, _work_graph = build_run(
            delivery_run_id=f"{DRID}-exhausted",
            attempts_by_work={
                WORK_ID: [
                    {
                        "outcome": "completed",
                        "candidate": {"label": "C1"},
                        "verdicts": ["inconclusive", "inconclusive"],
                    }
                ]
            },
            max_attempts=3,
            max_assurance_attempts=2,
        )
        projection = orchestrator.run()
        return (
            projection.works[WORK_ID],
            journal.history(delivery_run_id=f"{DRID}-exhausted"),
        )

    def test_item_8_blocks_with_assurance_inconclusive_citing_the_second_settlement(self) -> None:
        wp, history = self._run()
        self.assertEqual(wp.state, STATE_BLOCKED)
        self.assertEqual(wp.blocked_reason, "assurance-inconclusive")
        blocks = _decisions(history, DEC_BLOCK)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["data"]["reason"], "assurance-inconclusive")
        basis = blocks[0]["data"]["basis"]
        self.assertEqual([b["id"] for b in basis], [FACT_ASSURE_SETTLED])
        # The SECOND inconclusive settlement, not the first.
        settlements = _facts(history, FACT_ASSURE_SETTLED)
        self.assertEqual(len(settlements), 2)
        self.assertEqual(
            basis[0]["data"]["assurance_id"], settlements[1]["data"]["assurance_id"]
        )
        self.assertEqual(blocks[0]["data"]["max_assurance_attempts"], 2)
        self.assertEqual(blocks[0]["data"]["assurance_number"], 2)

    def test_item_9_no_third_assurance_and_blocked_is_confirmed(self) -> None:
        wp, history = self._run()
        self.assertEqual(len(_effects(history, FX_START_ASSURANCE)), 2)
        self.assertEqual(len(_facts(history, FACT_ASSURE_STARTED)), 2)
        self.assertEqual(len(_effects(history, FX_BLOCK_WORK)), 1)
        self.assertEqual(len(_facts(history, FACT_WORK_BLOCKED)), 1)
        self.assertTrue(wp.blocked_confirmed)

    def test_item_10_attempt_number_is_still_1(self) -> None:
        wp, history = self._run()
        self.assertEqual(wp.attempt_number, 1)
        self.assertEqual(len(_facts(history, FACT_EXEC_STARTED)), 1)

    def test_budget_1_blocks_on_the_first_inconclusive(self) -> None:
        # The pre-ADR-0006 shape, still reachable by configuring the
        # budget explicitly -- one inconclusive, straight to BLOCKED, no
        # re-request at all.
        orchestrator, journal, _work_graph = build_run(
            delivery_run_id=f"{DRID}-budget1",
            attempts_by_work={
                WORK_ID: [
                    {"outcome": "completed", "candidate": {"label": "C1"}, "verdict": "inconclusive"}
                ]
            },
            max_attempts=3,
            max_assurance_attempts=1,
        )
        wp = orchestrator.run().works[WORK_ID]
        history = journal.history(delivery_run_id=f"{DRID}-budget1")
        self.assertEqual(wp.state, STATE_BLOCKED)
        self.assertEqual(wp.blocked_reason, "assurance-inconclusive")
        self.assertEqual(len(_effects(history, FX_START_ASSURANCE)), 1)
        self.assertEqual(len(_decisions(history, DEC_REQUEST_ASSURANCE)), 1)


# ---------------------------------------------------------------------------
# Given (legacy journal) -- SCN-021 items 11-12
# ---------------------------------------------------------------------------


class LegacyJournalTest(unittest.TestCase):
    """A journal whose `FX-CREATE-WORK` record carries `data.max_attempts`
    but no `data.max_assurance_attempts` -- the pre-`ADR-0006` shape --
    containing `FACT-ASSURE-SETTLED(inconclusive)` followed by
    `DEC-BLOCK`/`FACT-WORK-BLOCKED`."""

    RUN_ID = f"{DRID}-legacy"

    def _legacy_journal(self, journal) -> None:
        journal.append_fact(
            make_fact(
                FACT_INTENT_SUBMITTED,
                delivery_run_id=self.RUN_ID,
                intent_id=self.RUN_ID,
                text="legacy",
            )
        )
        journal.append_effect_record(
            make_effect(
                FX_CREATE_WORK,
                delivery_run_id=self.RUN_ID,
                work_id="",
                idempotency_key=f"{self.RUN_ID}|{FX_CREATE_WORK}",
                # NOTE the deliberate omission: no max_assurance_attempts.
                data={"plan": {"works": [{"work_id": WORK_ID, "deps": []}]}, "max_attempts": 3},
            ),
            dispatch_result={"works": []},
        )
        for fact in (
            make_fact(FACT_WORK_CREATED, delivery_run_id=self.RUN_ID, work_id=WORK_ID),
            make_fact(FACT_WORK_READY, delivery_run_id=self.RUN_ID, work_id=WORK_ID),
            make_fact(
                FACT_EXEC_STARTED, delivery_run_id=self.RUN_ID, work_id=WORK_ID, execution_id="e1"
            ),
            make_fact(
                FACT_EXEC_SETTLED,
                delivery_run_id=self.RUN_ID,
                work_id=WORK_ID,
                execution_id="e1",
                outcome="completed",
            ),
            make_fact(
                FACT_CANDIDATE_OBSERVED,
                delivery_run_id=self.RUN_ID,
                work_id=WORK_ID,
                candidate_id="c1",
                fingerprint="fp-1",
                execution_id="e1",
            ),
            make_fact(
                FACT_ASSURE_STARTED,
                delivery_run_id=self.RUN_ID,
                work_id=WORK_ID,
                assurance_id="a1",
                candidate_id="c1",
            ),
            make_fact(
                FACT_ASSURE_SETTLED,
                delivery_run_id=self.RUN_ID,
                work_id=WORK_ID,
                assurance_id="a1",
                candidate_fingerprint="fp-1",
                verdict="inconclusive",
            ),
        ):
            journal.append_fact(fact)
        journal.append_decision(
            make_decision(
                DEC_BLOCK,
                delivery_run_id=self.RUN_ID,
                work_id=WORK_ID,
                basis=[{"id": FACT_ASSURE_SETTLED, "data": {"verdict": "inconclusive"}}],
                data={"reason": "assurance-inconclusive"},
            )
        )
        journal.append_fact(
            make_fact(
                FACT_WORK_BLOCKED,
                delivery_run_id=self.RUN_ID,
                work_id=WORK_ID,
                reason="assurance-inconclusive",
            )
        )

    def test_read_fallback_is_1_not_the_schema_default(self) -> None:
        self.assertEqual(LEGACY_MAX_ASSURANCE_ATTEMPTS, 1)
        self.assertEqual(DEFAULT_MAX_ASSURANCE_ATTEMPTS, 2)
        journal = MemoryJournal()
        self._legacy_journal(journal)
        history = journal.history(delivery_run_id=self.RUN_ID)
        self.assertEqual(journaled_max_assurance_attempts(history), 1)

    def test_item_11_legacy_journal_replays_clean_through_load_projection(self) -> None:
        for factory in (lambda: MemoryJournal(), None):
            with tempfile.TemporaryDirectory() as tmp:
                journal = factory() if factory else JSONLJournal(Path(tmp) / ".orc")
                self._legacy_journal(journal)
                # No ERR-CONFLICT from a wrongly derived ASSURING.
                projection = journal.load_projection(delivery_run_id=self.RUN_ID)
                wp = projection.works[WORK_ID]
                self.assertEqual(wp.state, STATE_BLOCKED)
                self.assertTrue(wp.blocked_confirmed)
                self.assertEqual(wp.blocked_reason, "assurance-inconclusive")

    def test_a_post_adr_journal_records_the_budget_at_creation(self) -> None:
        _orchestrator, journal, _work_graph = build_run(
            delivery_run_id=f"{DRID}-recorded",
            attempts_by_work={WORK_ID: [{"outcome": "failed"}]},
            max_assurance_attempts=2,
        )
        history = journal.history(delivery_run_id=f"{DRID}-recorded")
        create_work = next(
            r for r in history if r["kind"] == KIND_EFFECT and r["id"] == FX_CREATE_WORK
        )
        self.assertEqual(create_work["data"]["max_assurance_attempts"], 2)
        self.assertEqual(journaled_max_assurance_attempts(history), 2)


class MatchOrRefuseTest(unittest.TestCase):
    """SCN-021 item 12: an explicit later `max_assurance_attempts` that
    disagrees with the journaled value is refused with `ERR-VALIDATION`
    naming both -- exactly as `SCN-008`'s issue #240 R2 refuses a
    disagreeing `max_attempts`."""

    def test_disagreeing_flag_on_resume_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {
                "run_id": "mor-run",
                "max_assurance_attempts": 2,
                "attempts": {WORK_ID: [{"outcome": "completed", "candidate": {"label": "A"}}]},
            }
            config_path = tmp_dir / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            first = _run_cli(tmp_dir, "dispatch", "match or refuse", "--config", str(config_path))
            self.assertEqual(first.returncode, 3, msg=first.stdout + first.stderr)

            refused = _run_cli(
                tmp_dir, "dispatch", "--run-id", "mor-run", "--max-assurance-attempts", "5"
            )
            self.assertEqual(refused.returncode, 2, msg=refused.stdout + refused.stderr)
            payload = json.loads(refused.stderr)
            self.assertEqual(payload["error"], "ERR-VALIDATION")
            self.assertEqual(payload["details"]["journaled_max_assurance_attempts"], 2)
            self.assertEqual(payload["details"]["requested_max_assurance_attempts"], 5)

            # A matching value is a no-op, never a refusal.
            agreeing = _run_cli(
                tmp_dir, "dispatch", "--run-id", "mor-run", "--max-assurance-attempts", "2"
            )
            self.assertEqual(agreeing.returncode, 3, msg=agreeing.stdout + agreeing.stderr)


# ---------------------------------------------------------------------------
# Given (re-observed candidate with inconclusive-only history) -- item 13
# ---------------------------------------------------------------------------


class InconclusiveOnlyReObservationTest(unittest.TestCase):
    """SCN-021 item 13, reached by the ordinary v0 abandon path (the #263
    verify audit's finding B): assurance 1 settles `inconclusive` ->
    re-request -> assurance 2 never settles -> operator `--abandon-work`
    (legal at `ASSURING` with the current assurance unsettled, item 9) ->
    `READY` -> execution 2 re-produces the identical candidate. The only
    settled assurance is `inconclusive`, so this is neither an inheritance
    (item 8) nor an item 9 conflict: the Work enters `ASSURING` afresh with
    `assurance_number` restarting at 1 for execution 2."""

    def _facts_up_to_reobservation(self) -> list:
        facts = fixtures.assuring(
            delivery_run_id=DRID,
            work_id=WORK_ID,
            execution_id="e1",
            candidate_id="c1",
            fingerprint="fp-1",
            assurance_id="a1",
        )
        facts.append(
            fixtures.assure_settled(
                delivery_run_id=DRID,
                work_id=WORK_ID,
                assurance_id="a1",
                fingerprint="fp-1",
                verdict="inconclusive",
            )
        )
        # bounded re-request: assurance 2 starts and never settles.
        facts.append(
            make_fact(
                FACT_ASSURE_STARTED,
                delivery_run_id=DRID,
                work_id=WORK_ID,
                assurance_id="a2",
                candidate_id="c1",
            )
        )
        # operator abandons the attempt (STATE-DELIVERY item 9).
        facts.append(
            make_fact(
                FACT_ATTEMPT_ABANDONED,
                delivery_run_id=DRID,
                work_id=WORK_ID,
                reason="verifier environment never came back",
            )
        )
        # execution 2 re-produces the IDENTICAL candidate.
        facts.extend(
            [
                make_fact(
                    FACT_EXEC_STARTED, delivery_run_id=DRID, work_id=WORK_ID, execution_id="e2"
                ),
                make_fact(
                    FACT_EXEC_SETTLED,
                    delivery_run_id=DRID,
                    work_id=WORK_ID,
                    execution_id="e2",
                    outcome="completed",
                ),
                make_fact(
                    FACT_CANDIDATE_OBSERVED,
                    delivery_run_id=DRID,
                    work_id=WORK_ID,
                    candidate_id="c1",
                    fingerprint="fp-1",
                    execution_id="e2",
                ),
            ]
        )
        return facts

    def _fold(self):
        return reduce(
            self._facts_up_to_reobservation(),
            delivery_run_id=DRID,
            max_attempts=3,
            max_assurance_attempts=2,
        ).works[WORK_ID]

    def test_abandon_is_legal_at_assuring_and_returns_the_work_to_ready(self) -> None:
        facts = self._facts_up_to_reobservation()[:-3]  # stop right after the abandon
        wp = reduce(
            facts, delivery_run_id=DRID, max_attempts=3, max_assurance_attempts=2
        ).works[WORK_ID]
        self.assertEqual(wp.state, STATE_READY)
        self.assertEqual([a["verdict"] for a in wp.assurances], ["inconclusive", "abandoned"])

    def test_item_13_re_observation_enters_assuring_afresh(self) -> None:
        wp = self._fold()
        self.assertEqual(wp.state, STATE_ASSURING)
        self.assertIsNone(wp.candidate_conflict)
        self.assertFalse(wp.assurance_started_for_current)
        self.assertEqual(wp.current_candidate_id, "c1")

    def test_item_13_assurance_number_restarts_at_1_for_the_new_execution(self) -> None:
        # The reason `assurance_number` is per-Execution and not
        # per-Candidate: a candidate-scoped count would be 2 here (or 3
        # after the next start) and would block immediately, contradicting
        # item 11's "a new attempt's full assurance budget".
        wp = self._fold()
        self.assertEqual(wp.assurance_number(), 0)
        outcome = decide(wp, max_attempts=3, max_assurance_attempts=2)
        assert outcome is not None
        self.assertEqual(outcome.decision.id, DEC_REQUEST_ASSURANCE)
        self.assertEqual(outcome.decision.data["assurance_number"], 1)
        # ...and the key for that first assurance of execution 2 carries no
        # assurance_number component (INV-020), only the new attempt number.
        self.assertEqual(
            outcome.effects[0].idempotency_key,
            f"{DRID}|{WORK_ID}|2|{FX_START_ASSURANCE}|fp-1",
        )

    def test_inconclusive_is_never_inherited(self) -> None:
        # STATE-DELIVERY item 8 as amended: the Work does NOT go straight
        # to BLOCKED (which is what inheriting an inconclusive verdict used
        # to do), and no new FACT-ASSURE-SETTLED is fabricated (INV-003).
        wp = self._fold()
        self.assertNotEqual(wp.state, STATE_BLOCKED)
        self.assertEqual(len([a for a in wp.assurances if a["verdict"] == "inconclusive"]), 1)

    def test_a_candidate_with_no_settled_assurance_is_still_an_item_9_conflict(self) -> None:
        # Guard: the new branch is scoped to inconclusive-only history. A
        # re-observed candidate whose only prior assurance never settled
        # remains the item 9 conflict it always was.
        facts = fixtures.assuring(
            delivery_run_id=DRID,
            work_id=WORK_ID,
            execution_id="e1",
            candidate_id="c1",
            fingerprint="fp-1",
            assurance_id="a1",
        )
        facts.append(
            make_fact(
                FACT_ATTEMPT_ABANDONED, delivery_run_id=DRID, work_id=WORK_ID, reason="stuck"
            )
        )
        facts.extend(
            [
                make_fact(
                    FACT_EXEC_STARTED, delivery_run_id=DRID, work_id=WORK_ID, execution_id="e2"
                ),
                make_fact(
                    FACT_EXEC_SETTLED,
                    delivery_run_id=DRID,
                    work_id=WORK_ID,
                    execution_id="e2",
                    outcome="completed",
                ),
                make_fact(
                    FACT_CANDIDATE_OBSERVED,
                    delivery_run_id=DRID,
                    work_id=WORK_ID,
                    candidate_id="c1",
                    fingerprint="fp-1",
                    execution_id="e2",
                ),
            ]
        )
        wp = reduce(
            facts, delivery_run_id=DRID, max_attempts=3, max_assurance_attempts=2
        ).works[WORK_ID]
        self.assertIsNotNone(wp.candidate_conflict)
        self.assertEqual(wp.candidate_conflict["reason"], "no-inheritable-verdict")

    def test_an_accepted_settlement_still_inherits(self) -> None:
        # Guard the other side: inconclusive history does not shadow an
        # inheritable verdict when one exists for the same candidate.
        facts = fixtures.assuring(
            delivery_run_id=DRID,
            work_id=WORK_ID,
            execution_id="e1",
            candidate_id="c1",
            fingerprint="fp-1",
            assurance_id="a1",
        )
        facts.append(
            fixtures.assure_settled(
                delivery_run_id=DRID,
                work_id=WORK_ID,
                assurance_id="a1",
                fingerprint="fp-1",
                verdict="inconclusive",
            )
        )
        facts.append(
            make_fact(
                FACT_ASSURE_STARTED,
                delivery_run_id=DRID,
                work_id=WORK_ID,
                assurance_id="a2",
                candidate_id="c1",
            )
        )
        facts.append(
            fixtures.assure_settled(
                delivery_run_id=DRID,
                work_id=WORK_ID,
                assurance_id="a2",
                fingerprint="fp-1",
                verdict="rejected",
            )
        )
        facts.extend(
            [
                make_fact(
                    FACT_EXEC_STARTED, delivery_run_id=DRID, work_id=WORK_ID, execution_id="e2"
                ),
                make_fact(
                    FACT_EXEC_SETTLED,
                    delivery_run_id=DRID,
                    work_id=WORK_ID,
                    execution_id="e2",
                    outcome="completed",
                ),
                make_fact(
                    FACT_CANDIDATE_OBSERVED,
                    delivery_run_id=DRID,
                    work_id=WORK_ID,
                    candidate_id="c1",
                    fingerprint="fp-1",
                    execution_id="e2",
                ),
            ]
        )
        wp = reduce(
            facts, delivery_run_id=DRID, max_attempts=3, max_assurance_attempts=2
        ).works[WORK_ID]
        # rejected inherited, budget remaining -> READY (SCN-009's rule).
        self.assertEqual(wp.state, STATE_READY)


# ---------------------------------------------------------------------------
# CONF-ASSURE-008 and INV-020 key compatibility
# ---------------------------------------------------------------------------


class ConfAssure008Test(unittest.TestCase):
    """`CONF-ASSURE-008`: bounded re-request -- an `inconclusive`
    settlement with assurance budget remaining MUST re-request assurance of
    the identical candidate fingerprint under a new assurance identity and
    MUST NOT journal an execution start or advance `attempt_number`; with
    the budget exhausted it MUST resolve to `BLOCKED` with reason
    `assurance-inconclusive`; a journal lacking a recorded assurance budget
    MUST fold under a budget of `1`."""

    def test_re_request_targets_the_identical_fingerprint_under_a_new_identity(self) -> None:
        run_id = f"{DRID}-conf008"
        orchestrator, journal, _wg = build_run(
            delivery_run_id=run_id,
            attempts_by_work={
                WORK_ID: [
                    {
                        "outcome": "completed",
                        "candidate": {"label": "C1"},
                        "verdicts": ["inconclusive", "accepted"],
                    }
                ]
            },
            max_assurance_attempts=2,
        )
        wp = orchestrator.run().works[WORK_ID]
        history = journal.history(delivery_run_id=run_id)
        settlements = _facts(history, FACT_ASSURE_SETTLED)
        self.assertEqual(
            {r["data"]["candidate_fingerprint"] for r in settlements},
            {wp.current_candidate_fingerprint()},
        )
        started = _facts(history, FACT_ASSURE_STARTED)
        self.assertEqual(len({r["data"]["assurance_id"] for r in started}), 2)
        self.assertEqual(len(_facts(history, FACT_EXEC_STARTED)), 1)
        self.assertEqual(wp.attempt_number, 1)

    def test_exhausted_budget_resolves_to_blocked_assurance_inconclusive(self) -> None:
        run_id = f"{DRID}-conf008-block"
        orchestrator, _journal, _wg = build_run(
            delivery_run_id=run_id,
            attempts_by_work={
                WORK_ID: [
                    {
                        "outcome": "completed",
                        "candidate": {"label": "C1"},
                        "verdicts": ["inconclusive", "inconclusive"],
                    }
                ]
            },
            max_assurance_attempts=2,
        )
        wp = orchestrator.run().works[WORK_ID]
        self.assertEqual(wp.state, STATE_BLOCKED)
        self.assertEqual(wp.blocked_reason, "assurance-inconclusive")

    def test_absent_recorded_budget_folds_under_1(self) -> None:
        self.assertEqual(journaled_max_assurance_attempts([]), 1)
        self.assertEqual(
            journaled_max_assurance_attempts(
                [
                    {
                        "kind": KIND_EFFECT,
                        "id": FX_CREATE_WORK,
                        "data": {"plan": {}, "max_attempts": 3},
                    }
                ]
            ),
            1,
        )


class Inv020KeyCompatibilityTest(unittest.TestCase):
    def test_assurance_1_key_equals_the_pre_change_literal_form(self) -> None:
        # The exact string every pre-ADR-0006 journal already contains:
        # (delivery_run_id, work_id, attempt_number, effect_id) +
        # candidate_fingerprint, joined by "|", with NO trailing component.
        expected = "run-1|work-1|2|FX-START-ASSURANCE|fp-abc"
        self.assertEqual(
            idempotency_key(
                FX_START_ASSURANCE,
                delivery_run_id="run-1",
                work_id="work-1",
                attempt_number=2,
                candidate_fingerprint="fp-abc",
            ),
            expected,
        )
        # ...and an explicit assurance_number of 1 derives the same string.
        self.assertEqual(
            idempotency_key(
                FX_START_ASSURANCE,
                delivery_run_id="run-1",
                work_id="work-1",
                attempt_number=2,
                candidate_fingerprint="fp-abc",
                assurance_number=1,
            ),
            expected,
        )

    def test_later_assurances_append_the_number_component(self) -> None:
        base = "run-1|work-1|2|FX-START-ASSURANCE|fp-abc"
        for number in (2, 3, 7):
            self.assertEqual(
                idempotency_key(
                    FX_START_ASSURANCE,
                    delivery_run_id="run-1",
                    work_id="work-1",
                    attempt_number=2,
                    candidate_fingerprint="fp-abc",
                    assurance_number=number,
                ),
                f"{base}|{number}",
            )

    def test_non_positive_assurance_number_is_rejected(self) -> None:
        for bad in (0, -1, True):
            with self.assertRaises(ValueError):
                idempotency_key(
                    FX_START_ASSURANCE,
                    delivery_run_id="run-1",
                    work_id="work-1",
                    attempt_number=1,
                    candidate_fingerprint="fp-abc",
                    assurance_number=bad,
                )


# ---------------------------------------------------------------------------
# CLI: the verify seat's `inconclusive` verdict, end to end
# ---------------------------------------------------------------------------


class CliInconclusiveRecordingTest(unittest.TestCase):
    def test_record_inconclusive_then_accepted_reaches_accepted_in_one_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {
                "run_id": "cli-inconclusive",
                "attempts": {WORK_ID: [{"outcome": "completed", "candidate": {"label": "A"}}]},
            }
            config_path = tmp_dir / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            first = _run_cli(tmp_dir, "dispatch", "cli inconclusive", "--config", str(config_path))
            self.assertEqual(first.returncode, 3, msg=first.stdout + first.stderr)
            self.assertIn("assurance=1", first.stdout)

            recorded = _run_cli(
                tmp_dir,
                "record",
                "cli-inconclusive",
                "--work",
                WORK_ID,
                "--verdict",
                "inconclusive",
                "--evidence-ref",
                "verifier.log",
            )
            self.assertEqual(recorded.returncode, 0, msg=recorded.stdout + recorded.stderr)
            self.assertIn("verdict=inconclusive assurance=1", recorded.stdout)

            second = _run_cli(tmp_dir, "dispatch", "--run-id", "cli-inconclusive")
            self.assertEqual(second.returncode, 3, msg=second.stdout + second.stderr)
            # the re-request is in flight and named by index.
            self.assertIn("assurance 2 of 2", second.stdout)

            recorded2 = _run_cli(
                tmp_dir, "record", "cli-inconclusive", "--work", WORK_ID, "--verdict", "accepted"
            )
            self.assertEqual(recorded2.returncode, 0, msg=recorded2.stdout + recorded2.stderr)
            self.assertIn("assurance=2", recorded2.stdout)

            persisted = json.loads(
                (tmp_dir / ".orc" / "cli-inconclusive" / "config.json").read_text(encoding="utf-8")
            )
            entry = persisted["attempts"][WORK_ID][0]
            self.assertNotIn("assurance", entry)
            self.assertEqual(
                [item["verdict"] for item in entry["assurances"]], ["inconclusive", "accepted"]
            )

            third = _run_cli(tmp_dir, "dispatch", "--run-id", "cli-inconclusive")
            self.assertEqual(third.returncode, 0, msg=third.stdout + third.stderr)
            self.assertIn("state=ACCEPTED", third.stdout)

            # attempt_number never advanced: no retry budget was spent.
            self.assertIn("attempts=1", third.stdout)

            verdicts = _run_cli(tmp_dir, "verdict", "cli-inconclusive")
            self.assertEqual(verdicts.returncode, 0, msg=verdicts.stdout + verdicts.stderr)
            self.assertIn("verdict=accepted", verdicts.stdout)
            self.assertIn("earlier: inconclusive", verdicts.stdout)

            shown = _run_cli(tmp_dir, "show", "cli-inconclusive")
            self.assertEqual(shown.returncode, 0, msg=shown.stdout + shown.stderr)
            self.assertIn("verdict=inconclusive [assurance 1 of 2]", shown.stdout)
            self.assertIn("verdict=accepted [assurance 2 of 2]", shown.stdout)

    def test_two_inconclusive_verdicts_block_with_assurance_inconclusive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {
                "run_id": "cli-block",
                "attempts": {
                    WORK_ID: [
                        {
                            "outcome": "completed",
                            "candidate": {"label": "A"},
                            "assurances": [
                                {"verdict": "inconclusive"},
                                {"verdict": "inconclusive"},
                            ],
                        }
                    ]
                },
            }
            config_path = tmp_dir / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch = _run_cli(tmp_dir, "dispatch", "cli block", "--config", str(config_path))
            self.assertEqual(dispatch.returncode, 1, msg=dispatch.stdout + dispatch.stderr)
            self.assertIn("blocked_reason=assurance-inconclusive", dispatch.stdout)
            self.assertIn("attempts=1", dispatch.stdout)
            self.assertIn("assurance budget exhausted", dispatch.stdout)

    def test_supplying_both_assurance_and_assurances_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {
                "attempts": {
                    WORK_ID: [
                        {
                            "outcome": "completed",
                            "candidate": {"label": "A"},
                            "assurance": {"verdict": "accepted"},
                            "assurances": [{"verdict": "accepted"}],
                        }
                    ]
                }
            }
            config_path = tmp_dir / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            result = _run_cli(tmp_dir, "validate", str(config_path))
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            payload = json.loads(result.stderr)
            self.assertEqual(payload["error"], "ERR-VALIDATION")
            self.assertIn("both 'assurance' and 'assurances'", payload["message"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
