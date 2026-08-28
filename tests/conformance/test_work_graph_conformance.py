"""`CONF-WORK-001` through `CONF-WORK-004` conformance suite for
`WorkGraphPort` (`TASK-M0-002`).

`WorkGraphConformanceMixin` is reusable and provider-independent
(`ARCH-REPOSITORY-STRUCTURE`, `tests/conformance/`): a future real
WorkGraphPort adapter combines this mixin with `unittest.TestCase` and
implements `make_graph()` to run the same suite `MemoryWorkGraphConformance`
runs below. The mixin itself does not subclass `unittest.TestCase`, so
`unittest discover` never tries to run it directly (it has no assertion
methods of its own -- those come from whichever concrete `TestCase`
subclass mixes it in).
"""

from __future__ import annotations

import unittest
from typing import Any, Mapping

from orc_werk.adapters.memory import MemoryWorkGraph
from orc_werk.core.errors import (
    ERR_CONFLICT,
    ERR_UNSUPPORTED_CAPABILITY,
    ERR_VALIDATION,
    CoreError,
)
from orc_werk.ports.capabilities import CAP_WORK_ATOMIC_CLAIM
from orc_werk.ports.work_graph import WorkGraphPort

DELIVERY_RUN_ID = "dr-conf-1"


def _dep(work_id: str) -> Mapping[str, Any]:
    return {"work_id": work_id, "condition": "accepted"}


def _fanin_plan() -> Mapping[str, Any]:
    """SCN-005 shape: A, B independently ready; C requires both accepted."""
    return {
        "works": [
            {"work_id": "a", "deps": []},
            {"work_id": "b", "deps": []},
            {"work_id": "c", "deps": [_dep("a"), _dep("b")]},
        ]
    }


def _chain_plan() -> Mapping[str, Any]:
    """Single dependency edge: x depends on w."""
    return {
        "works": [
            {"work_id": "w", "deps": []},
            {"work_id": "x", "deps": [_dep("w")]},
        ]
    }


class _ExpectsCanonicalError:
    """Context manager asserting a `CoreError` carrying the given canonical
    `ERR-*` id is raised (mirrors `tests/core/test_ports_interfaces.py`)."""

    def __init__(self, test: unittest.TestCase, error_id: str) -> None:
        self._test = test
        self._error_id = error_id

    def __enter__(self) -> "_ExpectsCanonicalError":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._test.assertIsNotNone(exc, f"expected {self._error_id} but nothing was raised")
        self._test.assertIsInstance(exc, CoreError)
        self._test.assertEqual(exc.to_canonical()["error"], self._error_id)
        return True


class WorkGraphConformanceMixin:
    """Reusable `CONF-WORK-001`..`004` + `SCN-005` + plan-rejection suite.

    Subclasses combine this with `unittest.TestCase` and implement
    `make_graph()` returning a fresh `WorkGraphPort` instance.
    """

    def make_graph(self) -> WorkGraphPort:
        raise NotImplementedError

    def _assert_validation_error(self) -> _ExpectsCanonicalError:
        return _ExpectsCanonicalError(self, ERR_VALIDATION)  # type: ignore[arg-type]

    def _assert_conflict(self) -> _ExpectsCanonicalError:
        return _ExpectsCanonicalError(self, ERR_CONFLICT)  # type: ignore[arg-type]

    def _assert_unsupported_capability(self) -> _ExpectsCanonicalError:
        return _ExpectsCanonicalError(self, ERR_UNSUPPORTED_CAPABILITY)  # type: ignore[arg-type]

    # -- CONF-WORK-001: ready excludes works with incomplete/blocked deps. --

    def test_conf_work_001_ready_excludes_incomplete_and_blocked_deps(self) -> None:
        graph = self.make_graph()
        graph.create(delivery_run_id=DELIVERY_RUN_ID, plan=_fanin_plan())

        ready_ids = {w.id for w in graph.ready(delivery_run_id=DELIVERY_RUN_ID)}
        self.assertEqual(ready_ids, {"a", "b"})  # type: ignore[attr-defined]

        graph.block(work_id="a", reason="blocked-for-test")
        ready_ids = {w.id for w in graph.ready(delivery_run_id=DELIVERY_RUN_ID)}
        self.assertNotIn("a", ready_ids)  # type: ignore[attr-defined]
        self.assertNotIn("c", ready_ids)  # type: ignore[attr-defined]

    # -- CONF-WORK-002: dependents unlock only after committed completion. --

    def test_conf_work_002_dependents_unlock_only_after_committed_completion(self) -> None:
        graph = self.make_graph()
        graph.create(delivery_run_id=DELIVERY_RUN_ID, plan=_chain_plan())

        ready_ids = {w.id for w in graph.ready(delivery_run_id=DELIVERY_RUN_ID)}
        self.assertEqual(ready_ids, {"w"})  # type: ignore[attr-defined]

        graph.complete(work_id="w")
        ready_ids = {w.id for w in graph.ready(delivery_run_id=DELIVERY_RUN_ID)}
        self.assertIn("x", ready_ids)  # type: ignore[attr-defined]

    def test_conf_work_002_blocking_upstream_never_unlocks_a_dependent(self) -> None:
        # Mere terminal settlement of the upstream Work (blocked, not
        # completed) MUST NOT unlock a dependent -- only a committed
        # "accepted" completion does (INV-016).
        graph = self.make_graph()
        graph.create(delivery_run_id=DELIVERY_RUN_ID, plan=_chain_plan())

        graph.block(work_id="w", reason="blocked-for-test")
        ready_ids = {w.id for w in graph.ready(delivery_run_id=DELIVERY_RUN_ID)}
        self.assertNotIn("x", ready_ids)  # type: ignore[attr-defined]

    # -- CONF-WORK-003: duplicate completion is idempotent or --
    # -- deterministically conflicting (adapter's choice; see PR body). --

    def test_conf_work_003_duplicate_completion(self) -> None:
        graph = self.make_graph()
        graph.create(delivery_run_id=DELIVERY_RUN_ID, plan=_chain_plan())

        graph.complete(work_id="w")
        # MemoryWorkGraph chooses idempotent: a second complete() is a
        # no-op, not an error.
        graph.complete(work_id="w")

        snapshot = graph.snapshot(delivery_run_id=DELIVERY_RUN_ID)
        w_entry = next(entry for entry in snapshot["works"] if entry["work_id"] == "w")
        self.assertTrue(w_entry["completed"])  # type: ignore[attr-defined]

    # -- CONF-WORK-004: atomic claim, run because CAP-WORK-ATOMIC-CLAIM --
    # -- is advertised; unsupported-capability discipline otherwise. --

    def test_conf_work_004_atomic_claim(self) -> None:
        graph = self.make_graph()
        graph.create(delivery_run_id=DELIVERY_RUN_ID, plan=_chain_plan())

        if graph.supports(CAP_WORK_ATOMIC_CLAIM):
            claimed = graph.claim(work_id="w")
            self.assertEqual(claimed["work_id"], "w")  # type: ignore[attr-defined]
            self.assertIsInstance(claimed["claim_ref"], str)  # type: ignore[attr-defined]
            self.assertTrue(claimed["claim_ref"])  # type: ignore[attr-defined]

            with self._assert_conflict():
                graph.claim(work_id="w")
        else:
            # Unsupported-capability discipline (INV-013): declining an op
            # this adapter does not support MUST surface the canonical
            # ERR-UNSUPPORTED-CAPABILITY error value, not a bare
            # NotImplementedError.
            with self._assert_unsupported_capability():
                graph.claim(work_id="w")

    def test_conf_work_004_claim_requires_current_eligibility(self) -> None:
        # Fail-closed claim (watchtower ruling on the TASK-M0-002 review):
        # claim MUST reject with ERR-CONFLICT when the Work is not
        # currently eligible per the same criteria ready() uses, so an
        # early claim can never poison a not-yet-unlocked Work.
        graph = self.make_graph()
        graph.create(delivery_run_id=DELIVERY_RUN_ID, plan=_fanin_plan())

        if not graph.supports(CAP_WORK_ATOMIC_CLAIM):
            with self._assert_unsupported_capability():
                graph.claim(work_id="c")
            return

        # C's deps (A, B) are not committed-complete yet.
        with self._assert_conflict():
            graph.claim(work_id="c")

        graph.complete(work_id="a")
        # Still ineligible: B has not committed completion.
        with self._assert_conflict():
            graph.claim(work_id="c")

        graph.complete(work_id="b")
        claimed = graph.claim(work_id="c")
        self.assertEqual(claimed["work_id"], "c")  # type: ignore[attr-defined]

    def test_conf_work_004_claim_rejects_completed_and_blocked_work(self) -> None:
        graph = self.make_graph()
        graph.create(delivery_run_id=DELIVERY_RUN_ID, plan=_fanin_plan())

        if not graph.supports(CAP_WORK_ATOMIC_CLAIM):
            with self._assert_unsupported_capability():
                graph.claim(work_id="a")
            return

        graph.complete(work_id="a")
        graph.block(work_id="b", reason="blocked-for-test")

        with self._assert_conflict():
            graph.claim(work_id="a")
        with self._assert_conflict():
            graph.claim(work_id="b")

    # -- SCN-005 fan-in shape. --

    def test_scn_005_fanin_c_waits_for_both_a_and_b(self) -> None:
        graph = self.make_graph()
        graph.create(delivery_run_id=DELIVERY_RUN_ID, plan=_fanin_plan())

        ready_ids = {w.id for w in graph.ready(delivery_run_id=DELIVERY_RUN_ID)}
        self.assertEqual(ready_ids, {"a", "b"})  # type: ignore[attr-defined]

        graph.complete(work_id="a")
        ready_ids = {w.id for w in graph.ready(delivery_run_id=DELIVERY_RUN_ID)}
        self.assertNotIn("c", ready_ids)  # type: ignore[attr-defined]

        graph.complete(work_id="b")
        ready_ids = {w.id for w in graph.ready(delivery_run_id=DELIVERY_RUN_ID)}
        self.assertIn("c", ready_ids)  # type: ignore[attr-defined]

    # -- Plan rejection through the adapter's create() (PORT-WORK-001). --

    def test_create_rejects_empty_works_list(self) -> None:
        graph = self.make_graph()
        with self._assert_validation_error():
            graph.create(delivery_run_id="dr-reject-1", plan={"works": []})

    def test_create_rejects_duplicate_work_id(self) -> None:
        graph = self.make_graph()
        with self._assert_validation_error():
            graph.create(
                delivery_run_id="dr-reject-2",
                plan={"works": [{"work_id": "w1", "deps": []}, {"work_id": "w1", "deps": []}]},
            )

    def test_create_rejects_dependency_on_unknown_work(self) -> None:
        graph = self.make_graph()
        with self._assert_validation_error():
            graph.create(
                delivery_run_id="dr-reject-3",
                plan={"works": [{"work_id": "w1", "deps": [_dep("ghost")]}]},
            )

    def test_create_rejects_self_dependency(self) -> None:
        graph = self.make_graph()
        with self._assert_validation_error():
            graph.create(
                delivery_run_id="dr-reject-4",
                plan={"works": [{"work_id": "w1", "deps": [_dep("w1")]}]},
            )

    def test_create_rejects_dependency_cycle(self) -> None:
        graph = self.make_graph()
        with self._assert_validation_error():
            graph.create(
                delivery_run_id="dr-reject-5",
                plan={
                    "works": [
                        {"work_id": "a", "deps": [_dep("b")]},
                        {"work_id": "b", "deps": [_dep("a")]},
                    ]
                },
            )

    def test_create_rejects_non_accepted_condition(self) -> None:
        graph = self.make_graph()
        with self._assert_validation_error():
            graph.create(
                delivery_run_id="dr-reject-6",
                plan={
                    "works": [
                        {"work_id": "a", "deps": []},
                        {"work_id": "b", "deps": [{"work_id": "a", "condition": "settled"}]},
                    ]
                },
            )

    # -- Structurally malformed plans through the adapter's create(). --

    def test_create_rejects_missing_works_key(self) -> None:
        graph = self.make_graph()
        with self._assert_validation_error():
            graph.create(delivery_run_id="dr-malformed-1", plan={})

    def test_create_rejects_non_list_deps(self) -> None:
        graph = self.make_graph()
        with self._assert_validation_error():
            graph.create(
                delivery_run_id="dr-malformed-2",
                plan={"works": [{"work_id": "w1", "deps": "not-a-list"}]},
            )

    def test_create_rejects_non_mapping_works_entry(self) -> None:
        graph = self.make_graph()
        with self._assert_validation_error():
            graph.create(delivery_run_id="dr-malformed-3", plan={"works": ["not-a-mapping"]})

    # -- One plan per DeliveryRun (INV-020). --

    def test_create_rejects_second_plan_for_same_delivery_run(self) -> None:
        graph = self.make_graph()
        graph.create(delivery_run_id="dr-once", plan=_chain_plan())
        with self._assert_conflict():
            graph.create(delivery_run_id="dr-once", plan=_chain_plan())

    # -- PORT-WORK-002 v0 snapshot shape (exact, as amended). --

    def test_snapshot_matches_the_v0_shape_exactly(self) -> None:
        graph = self.make_graph()
        graph.create(delivery_run_id=DELIVERY_RUN_ID, plan=_fanin_plan())

        snapshot = graph.snapshot(delivery_run_id=DELIVERY_RUN_ID)
        self.assertEqual(set(snapshot.keys()), {"works"})  # type: ignore[attr-defined]

        by_id = {entry["work_id"]: entry for entry in snapshot["works"]}
        self.assertEqual(set(by_id.keys()), {"a", "b", "c"})  # type: ignore[attr-defined]
        for work_id, entry in by_id.items():
            self.assertEqual(  # type: ignore[attr-defined]
                set(entry.keys()), {"work_id", "deps", "completed", "blocked_reason"}
            )
            self.assertFalse(entry["completed"])  # type: ignore[attr-defined]
            self.assertIsNone(entry["blocked_reason"])  # type: ignore[attr-defined]

        self.assertEqual(by_id["c"]["deps"], [_dep("a"), _dep("b")])  # type: ignore[attr-defined]


class MemoryWorkGraphConformanceTest(WorkGraphConformanceMixin, unittest.TestCase):
    def make_graph(self) -> WorkGraphPort:
        return MemoryWorkGraph()


# ---------------------------------------------------------------------------
# MemoryWorkGraph-specific behavior: not part of the reusable conformance
# mixin because these are this adapter's own least-commitment stopgap
# choices (see the module docstring on MemoryWorkGraph), not requirements
# every WorkGraphPort adapter must share verbatim.
# ---------------------------------------------------------------------------


class MemoryWorkGraphAdapterTest(unittest.TestCase):
    def test_capabilities_advertises_only_atomic_claim(self) -> None:
        graph = MemoryWorkGraph()
        self.assertEqual(graph.capabilities(), frozenset({CAP_WORK_ATOMIC_CLAIM}))

    def test_claim_ref_is_deterministic_no_randomness_or_clock(self) -> None:
        # Once-per-lineage claim: exactly one claim ever per Work, so the
        # claim_ref is a counterless pure function of work_id -- identical
        # across independent instances/replays (INV-020).
        first = MemoryWorkGraph()
        first.create(delivery_run_id="dr-det", plan=_chain_plan())
        second = MemoryWorkGraph()
        second.create(delivery_run_id="dr-det", plan=_chain_plan())

        claimed_first = first.claim(work_id="w")
        claimed_second = second.claim(work_id="w")
        self.assertEqual(claimed_first["claim_ref"], claimed_second["claim_ref"])
        self.assertEqual(claimed_first["claim_ref"], "claim:w")

    def test_ready_raises_not_found_for_unknown_delivery_run(self) -> None:
        graph = MemoryWorkGraph()
        with self.assertRaises(CoreError) as ctx:
            graph.ready(delivery_run_id="no-such-run")
        self.assertEqual(ctx.exception.to_canonical()["error"], "ERR-NOT-FOUND")

    def test_claim_raises_not_found_for_unknown_work_id(self) -> None:
        graph = MemoryWorkGraph()
        graph.create(delivery_run_id="dr-nf", plan=_chain_plan())
        with self.assertRaises(CoreError) as ctx:
            graph.claim(work_id="no-such-work")
        self.assertEqual(ctx.exception.to_canonical()["error"], "ERR-NOT-FOUND")

    def test_complete_on_blocked_work_conflicts(self) -> None:
        graph = MemoryWorkGraph()
        graph.create(delivery_run_id="dr-cb", plan=_chain_plan())
        graph.block(work_id="w", reason="blocked-for-test")
        with self.assertRaises(CoreError) as ctx:
            graph.complete(work_id="w")
        self.assertEqual(ctx.exception.to_canonical()["error"], "ERR-CONFLICT")

    def test_block_on_completed_work_conflicts(self) -> None:
        graph = MemoryWorkGraph()
        graph.create(delivery_run_id="dr-bc", plan=_chain_plan())
        graph.complete(work_id="w")
        with self.assertRaises(CoreError) as ctx:
            graph.block(work_id="w", reason="too-late")
        self.assertEqual(ctx.exception.to_canonical()["error"], "ERR-CONFLICT")

    def test_claim_on_completed_or_blocked_work_conflicts(self) -> None:
        graph = MemoryWorkGraph()
        graph.create(delivery_run_id="dr-clc", plan=_fanin_plan())
        graph.complete(work_id="a")
        graph.block(work_id="b", reason="blocked-for-test")

        with self.assertRaises(CoreError) as ctx:
            graph.claim(work_id="a")
        self.assertEqual(ctx.exception.to_canonical()["error"], "ERR-CONFLICT")

        with self.assertRaises(CoreError) as ctx:
            graph.claim(work_id="b")
        self.assertEqual(ctx.exception.to_canonical()["error"], "ERR-CONFLICT")

    def test_block_records_reason_verbatim(self) -> None:
        graph = MemoryWorkGraph()
        graph.create(delivery_run_id="dr-reason", plan=_chain_plan())
        graph.block(work_id="w", reason="retry-budget-exhausted")

        snapshot = graph.snapshot(delivery_run_id="dr-reason")
        entry = next(e for e in snapshot["works"] if e["work_id"] == "w")
        self.assertEqual(entry["blocked_reason"], "retry-budget-exhausted")


if __name__ == "__main__":
    unittest.main()
