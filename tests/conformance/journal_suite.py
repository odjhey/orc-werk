"""Reusable `CONF-JOURNAL-001`..`003` conformance suite for `PORT-JOURNAL`
adapters, parameterized over a journal factory.

Not a test module itself -- no `test_` prefix, so `unittest discover`
(default pattern `test*.py`) skips this file, mirroring
`tests/core/fixtures.py`'s "helper module imported by the actual test
modules" pattern. This is the reusable form `ARCH-REPOSITORY-STRUCTURE`
describes for `tests/conformance/`: "Memory/scripted adapters run them
first; every future real adapter must run the applicable same suite."

Concrete adapter test modules subclass `JournalConformanceSuite` and, in
`setUp`, set `self.journal_factory` before calling `super().setUp()`.
Adapters with a separate persistence layer to reopen after a crash/restart
(e.g. `JSONLJournal`) additionally override `reopen()`.
"""

from __future__ import annotations

import unittest
from typing import Callable

from orc_werk.core.decisions import DEC_DISPATCH, make_decision
from orc_werk.core.effects import FX_CREATE_WORK, FX_START_EXECUTION, make_effect
from orc_werk.core.errors import CoreError
from orc_werk.core.facts import (
    FACT_CANDIDATE_OBSERVED,
    FACT_EXEC_SETTLED,
    FACT_EXEC_STARTED,
    FACT_WORK_BLOCKED,
    FACT_WORK_CREATED,
    FACT_WORK_READY,
    make_fact,
)
from orc_werk.core.reducer import DEFAULT_MAX_ATTEMPTS, reduce
from orc_werk.core.serialization import fact_from_envelope
from orc_werk.ports.journal import JournalPort


def _dispatch_idempotency_key(delivery_run_id: str, work_id: str, attempt: int = 1) -> str:
    return f"{delivery_run_id}|{work_id}|{attempt}|{FX_START_EXECUTION}"


# Sentinel for `_append_create_work`'s `max_attempts` parameter: "omit the
# key entirely" is a distinct case from "the key is present with some int
# value", so `None` (a legal-looking-but-wrong value) would not do.
_OMIT = object()


class JournalConformanceSuite(unittest.TestCase):
    """Abstract base -- see module docstring. `journal_factory` and
    `journal` are set by concrete subclasses' `setUp`."""

    journal_factory: Callable[[], JournalPort]
    journal: JournalPort

    def setUp(self) -> None:
        if type(self) is JournalConformanceSuite:
            self.skipTest("abstract base -- run via a concrete adapter subclass")
        self.journal = self.journal_factory()

    def reopen(self) -> JournalPort:
        """Return a `JournalPort` reading the same underlying store as
        `self.journal`. Default: the same instance (an in-memory journal
        has no separate persistence layer to reopen -- it *is* the store).
        Durable adapters (e.g. `JSONLJournal`) override this to construct a
        fresh instance against the same backing storage, exercising
        crash-recovery replay (`ARCH-REPOSITORY-STRUCTURE`'s "restart ->
        replay durable canonical facts ... -> reconstruct projection")."""
        return self.journal

    # ------------------------------------------------------------------
    # CONF-JOURNAL-001: append order is deterministic.
    # ------------------------------------------------------------------

    def test_seq_starts_at_one_and_increments_in_append_order(self) -> None:
        drid = "dr-conf-seq"
        r1 = self.journal.append_fact(make_fact(FACT_WORK_CREATED, delivery_run_id=drid, work_id="w1"))
        r2 = self.journal.append_fact(make_fact(FACT_WORK_READY, delivery_run_id=drid, work_id="w1"))
        r3 = self.journal.append_fact(
            make_fact(FACT_EXEC_STARTED, delivery_run_id=drid, work_id="w1", execution_id="e1")
        )
        self.assertEqual([r1["seq"], r2["seq"], r3["seq"]], [1, 2, 3])

    def test_seq_is_independent_and_deterministic_per_delivery_run(self) -> None:
        # ordering is scoped per delivery_run_id -- two runs interleaved
        # each start their own sequence at 1 (CONF-JOURNAL-001 "across ...
        # runs").
        a1 = self.journal.append_fact(make_fact(FACT_WORK_CREATED, delivery_run_id="dr-a", work_id="w1"))
        b1 = self.journal.append_fact(make_fact(FACT_WORK_CREATED, delivery_run_id="dr-b", work_id="w1"))
        a2 = self.journal.append_fact(make_fact(FACT_WORK_READY, delivery_run_id="dr-a", work_id="w1"))
        b2 = self.journal.append_fact(make_fact(FACT_WORK_READY, delivery_run_id="dr-b", work_id="w1"))
        self.assertEqual([a1["seq"], a2["seq"]], [1, 2])
        self.assertEqual([b1["seq"], b2["seq"]], [1, 2])
        self.assertEqual(
            [record["seq"] for record in self.journal.history(delivery_run_id="dr-a")], [1, 2]
        )
        self.assertEqual(
            [record["seq"] for record in self.journal.history(delivery_run_id="dr-b")], [1, 2]
        )

    def test_history_ordered_by_seq_across_fact_decision_effect(self) -> None:
        drid = "dr-conf-mixed"
        fact = make_fact(FACT_WORK_CREATED, delivery_run_id=drid, work_id="w1")
        self.journal.append_fact(fact)
        decision = make_decision(
            DEC_DISPATCH, delivery_run_id=drid, work_id="w1", basis=[fact.to_dict()]
        )
        self.journal.append_decision(decision)
        effect = make_effect(
            FX_START_EXECUTION,
            delivery_run_id=drid,
            work_id="w1",
            idempotency_key=_dispatch_idempotency_key(drid, "w1"),
        )
        self.journal.append_effect_record(effect, dispatch_result={"status": "ok"})

        history = self.journal.history(delivery_run_id=drid)
        self.assertEqual([r["seq"] for r in history], [1, 2, 3])
        self.assertEqual([r["kind"] for r in history], ["fact", "decision", "effect"])
        self.assertEqual(history[2]["data"]["dispatch_result"], {"status": "ok"})

    # ------------------------------------------------------------------
    # CONF-JOURNAL-002: history is immutable/append-preserving.
    # ------------------------------------------------------------------

    def test_mutating_a_history_return_value_does_not_affect_the_journal(self) -> None:
        drid = "dr-conf-immutable-history"
        self.journal.append_fact(make_fact(FACT_WORK_CREATED, delivery_run_id=drid, work_id="w1"))
        history = self.journal.history(delivery_run_id=drid)
        # Mutate the RETURNED record itself, in place -- top-level and a
        # nested field -- so this actually proves defensive copying rather
        # than copy-then-mutate.
        history[0]["seq"] = 999
        history[0]["data"]["injected"] = True
        history[0]["extensions"]["injected-ext/v1"] = {"evil": True}

        history_again = self.journal.history(delivery_run_id=drid)
        self.assertEqual(history_again[0]["seq"], 1)
        self.assertNotIn("injected", history_again[0]["data"])
        self.assertNotIn("injected-ext/v1", history_again[0]["extensions"])

    def test_mutating_an_append_return_value_does_not_affect_the_journal(self) -> None:
        drid = "dr-conf-immutable-append"
        returned = self.journal.append_fact(make_fact(FACT_WORK_CREATED, delivery_run_id=drid, work_id="w1"))
        # Mutate the RETURNED envelope itself, in place, including a nested field.
        returned["seq"] = 999
        returned["data"]["injected"] = True

        history = self.journal.history(delivery_run_id=drid)
        self.assertEqual(history[0]["seq"], 1)
        self.assertNotIn("injected", history[0]["data"])

    def test_earlier_records_unchanged_after_later_appends(self) -> None:
        drid = "dr-conf-append-only"
        first = self.journal.append_fact(make_fact(FACT_WORK_CREATED, delivery_run_id=drid, work_id="w1"))
        self.journal.append_fact(make_fact(FACT_WORK_READY, delivery_run_id=drid, work_id="w1"))
        self.journal.append_fact(
            make_fact(FACT_EXEC_STARTED, delivery_run_id=drid, work_id="w1", execution_id="e1")
        )

        history = self.journal.history(delivery_run_id=drid)
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0]["seq"], first["seq"])
        self.assertEqual(history[0]["id"], first["id"])
        self.assertEqual(history[0]["data"], first["data"])

    # ------------------------------------------------------------------
    # CONF-JOURNAL-003: replay reconstructs the same canonical projection.
    # ------------------------------------------------------------------

    def test_load_projection_matches_direct_reduce(self) -> None:
        drid = "dr-conf-replay"
        facts = [
            make_fact(FACT_WORK_CREATED, delivery_run_id=drid, work_id="w1"),
            make_fact(FACT_WORK_READY, delivery_run_id=drid, work_id="w1"),
            make_fact(FACT_EXEC_STARTED, delivery_run_id=drid, work_id="w1", execution_id="e1"),
            make_fact(
                FACT_EXEC_SETTLED,
                delivery_run_id=drid,
                work_id="w1",
                execution_id="e1",
                outcome="completed",
            ),
            make_fact(
                FACT_CANDIDATE_OBSERVED,
                delivery_run_id=drid,
                work_id="w1",
                candidate_id="c1",
                fingerprint="fp1",
                execution_id="e1",
            ),
        ]
        for fact in facts:
            self.journal.append_fact(fact)

        expected = reduce(facts, delivery_run_id=drid)
        projection = self.journal.load_projection(delivery_run_id=drid)
        self.assertEqual(projection.to_dict(), expected.to_dict())

    def test_replay_of_history_via_core_reducer_matches_load_projection(self) -> None:
        # PORT-JOURNAL-005: load_projection is "typically" replaying
        # history() through orc_werk.core.reducer.reduce -- prove both
        # paths agree rather than just trusting the adapter's internals.
        drid = "dr-conf-replay-equivalence"
        facts = [
            make_fact(FACT_WORK_CREATED, delivery_run_id=drid, work_id="w1"),
            make_fact(FACT_WORK_READY, delivery_run_id=drid, work_id="w1"),
        ]
        for fact in facts:
            self.journal.append_fact(fact)

        replayed_facts = [
            fact_from_envelope(record)
            for record in self.journal.history(delivery_run_id=drid)
            if record["kind"] == "fact"
        ]
        via_history_replay = reduce(replayed_facts, delivery_run_id=drid)
        via_load_projection = self.journal.load_projection(delivery_run_id=drid)
        self.assertEqual(via_history_replay.to_dict(), via_load_projection.to_dict())

    def test_decision_and_effect_records_do_not_affect_the_projection(self) -> None:
        # Only Fact records fold through the reducer (PORT-JOURNAL-005);
        # interleaved Decision/Effect records must be transparent to it.
        drid = "dr-conf-replay-mixed"
        fact1 = make_fact(FACT_WORK_CREATED, delivery_run_id=drid, work_id="w1")
        self.journal.append_fact(fact1)
        decision = make_decision(
            DEC_DISPATCH, delivery_run_id=drid, work_id="w1", basis=[fact1.to_dict()]
        )
        self.journal.append_decision(decision)
        effect = make_effect(
            FX_START_EXECUTION,
            delivery_run_id=drid,
            work_id="w1",
            idempotency_key=_dispatch_idempotency_key(drid, "w1"),
        )
        self.journal.append_effect_record(effect, dispatch_result={"status": "ok"})
        fact2 = make_fact(FACT_WORK_READY, delivery_run_id=drid, work_id="w1")
        self.journal.append_fact(fact2)

        projection = self.journal.load_projection(delivery_run_id=drid)
        expected = reduce([fact1, fact2], delivery_run_id=drid)
        self.assertEqual(projection.to_dict(), expected.to_dict())

    # ------------------------------------------------------------------
    # CONF-JOURNAL-003 / PORT-JOURNAL-005 (issue #52): replay folds under
    # the run's own recorded retry budget, not the reducer's schema
    # default -- including for a run that reached BLOCKED, mirroring the
    # topology-durability precedent (issue #41) for FX-CREATE-WORK's
    # journaled `data.max_attempts` alongside `data.plan`.
    # ------------------------------------------------------------------

    def _append_create_work(self, drid: str, *, max_attempts: object, work_id: str = "w1") -> None:
        """Append a minimal `FX-CREATE-WORK` effect record carrying
        `data.max_attempts` -- `object` (not `int`) lets the legacy-fallback
        test below omit the key entirely by passing a sentinel that never
        gets included."""
        plan = {"works": [{"work_id": work_id, "deps": []}]}
        data: dict[str, object] = {"plan": plan}
        if max_attempts is not _OMIT:
            data["max_attempts"] = max_attempts
        effect = make_effect(
            FX_CREATE_WORK,
            delivery_run_id=drid,
            work_id="",
            idempotency_key=f"{drid}|{FX_CREATE_WORK}",
            data=data,
        )
        self.journal.append_effect_record(
            effect, dispatch_result={"works": [{"delivery_run_id": drid, "id": work_id}]}
        )

    def test_load_projection_folds_under_recorded_non_default_max_attempts(self) -> None:
        drid = "dr-conf-replay-budget"
        work_id = "w1"
        non_default_budget = 2
        self.assertNotEqual(non_default_budget, DEFAULT_MAX_ATTEMPTS)
        self._append_create_work(drid, max_attempts=non_default_budget, work_id=work_id)

        facts = [
            make_fact(FACT_WORK_CREATED, delivery_run_id=drid, work_id=work_id),
            make_fact(FACT_WORK_READY, delivery_run_id=drid, work_id=work_id),
            make_fact(FACT_EXEC_STARTED, delivery_run_id=drid, work_id=work_id, execution_id="e1"),
            make_fact(
                FACT_EXEC_SETTLED, delivery_run_id=drid, work_id=work_id, execution_id="e1", outcome="failed"
            ),
            make_fact(FACT_EXEC_STARTED, delivery_run_id=drid, work_id=work_id, execution_id="e2"),
            make_fact(
                FACT_EXEC_SETTLED, delivery_run_id=drid, work_id=work_id, execution_id="e2", outcome="failed"
            ),
            make_fact(
                FACT_WORK_BLOCKED, delivery_run_id=drid, work_id=work_id, reason="retry-budget-exhausted"
            ),
        ]
        for fact in facts:
            self.journal.append_fact(fact)

        # A replay that (wrongly) folded under the reducer's own default
        # would derive READY, not BLOCKED, after the second failed
        # attempt (2 < DEFAULT_MAX_ATTEMPTS), and then reject the trailing
        # FACT-WORK-BLOCKED as illegal from READY -- exactly the issue #52
        # ERR-CONFLICT. A correct replay folds under the run's own
        # recorded budget and reaches BLOCKED cleanly, matching a direct
        # reduce() call given that same budget explicitly.
        expected = reduce(facts, delivery_run_id=drid, max_attempts=non_default_budget)
        projection = self.journal.load_projection(delivery_run_id=drid)
        self.assertEqual(projection.to_dict(), expected.to_dict())
        self.assertTrue(projection.works[work_id].blocked_confirmed)

        reopened = self.reopen()
        reopened_projection = reopened.load_projection(delivery_run_id=drid)
        self.assertEqual(reopened_projection.to_dict(), expected.to_dict())

    def test_load_projection_falls_back_to_schema_default_without_recorded_max_attempts(
        self,
    ) -> None:
        # Legacy journal precedent (issue #55 layout fallback): a
        # FX-CREATE-WORK record written before this field existed carries
        # `data.plan` but no `data.max_attempts` -- load_projection must
        # fall back to the reducer's schema default rather than raising or
        # inventing a budget.
        drid = "dr-conf-replay-budget-legacy"
        work_id = "w1"
        self._append_create_work(drid, max_attempts=_OMIT, work_id=work_id)

        facts = [
            make_fact(FACT_WORK_CREATED, delivery_run_id=drid, work_id=work_id),
            make_fact(FACT_WORK_READY, delivery_run_id=drid, work_id=work_id),
            make_fact(FACT_EXEC_STARTED, delivery_run_id=drid, work_id=work_id, execution_id="e1"),
            make_fact(
                FACT_EXEC_SETTLED, delivery_run_id=drid, work_id=work_id, execution_id="e1", outcome="completed"
            ),
        ]
        for fact in facts:
            self.journal.append_fact(fact)

        expected = reduce(facts, delivery_run_id=drid, max_attempts=DEFAULT_MAX_ATTEMPTS)
        projection = self.journal.load_projection(delivery_run_id=drid)
        self.assertEqual(projection.to_dict(), expected.to_dict())

    def test_load_projection_falls_back_to_schema_default_with_no_create_work_record(self) -> None:
        # Degenerate case: a run with no FX-CREATE-WORK effect record at
        # all (nothing bootstrapped yet) has nothing to read a budget from
        # -- falls back to the schema default rather than erroring.
        drid = "dr-conf-replay-budget-empty"
        projection = self.journal.load_projection(delivery_run_id=drid)
        self.assertEqual(projection.to_dict(), reduce([], delivery_run_id=drid).to_dict())

    # ------------------------------------------------------------------
    # EXT-005 / CONF-EXT-003: lossless unknown-extensions round-trip
    # through append/history/persist/reload.
    # ------------------------------------------------------------------

    def test_unknown_extensions_round_trip_losslessly_through_append_history_persist_reload(
        self,
    ) -> None:
        drid = "dr-conf-ext-reload"
        extensions = {
            "some-unregistered-extension/v7": {"anything": [1, 2, {"nested": True, "n": None}]},
        }
        fact = make_fact(
            FACT_WORK_CREATED, delivery_run_id=drid, work_id="w1", extensions=extensions
        )

        appended = self.journal.append_fact(fact)
        self.assertEqual(appended["extensions"], extensions)
        self.assertEqual(self.journal.history(delivery_run_id=drid)[0]["extensions"], extensions)

        reopened = self.reopen()
        reloaded_history = reopened.history(delivery_run_id=drid)
        self.assertEqual(reloaded_history[0]["extensions"], extensions)

    # ------------------------------------------------------------------
    # Portability: non-finite floats must never persist (P5 review F1).
    # ------------------------------------------------------------------

    def test_record_containing_non_finite_float_is_rejected(self) -> None:
        # nan/inf/-inf have no JSON literal, so a persisted record carrying
        # one would poison the canonical journal for non-Python readers.
        # `Fact.__post_init__` already rejects them at construction; smuggle
        # one past that guard (frozen-dataclass bypass) to prove the
        # journal's own serialization path is defense in depth, not just a
        # pass-through.
        drid = "dr-conf-nan"
        for bad in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(bad=repr(bad)):
                fact = make_fact(FACT_WORK_CREATED, delivery_run_id=drid, work_id="w1")
                object.__setattr__(fact, "data", {**fact.data, "metric": bad})
                with self.assertRaises((TypeError, CoreError)):
                    self.journal.append_fact(fact)
        # nothing was persisted by the rejected appends.
        self.assertEqual(len(self.journal.history(delivery_run_id=drid)), 0)


__all__ = ["JournalConformanceSuite"]


if __name__ == "__main__":
    unittest.main()
