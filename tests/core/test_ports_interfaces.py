"""`orc_werk.ports` scaffold tests (TASK-M0-006).

Scope is intentionally narrow -- full per-port conformance suites belong to
the adapter task cards (P3/P4/P5) that build on these interfaces. This
module only proves the P2 acceptance criteria:

- the five mandatory port interfaces are importable and abstract;
- `orc_werk.ports` imports only the standard library + `orc_werk.core`
  (extends the `orc_werk.core` import-guard pattern from
  `tests/core/test_package_imports.py` to the ports layer, and proves the
  `ports -> adapters` forbidden dependency, ARCH-REPOSITORY-STRUCTURE, is
  clean);
- the capability-advertisement surface works (INV-013/SCN-006);
- the capability-gated unsupported path returns the canonical
  `ERR-UNSUPPORTED-CAPABILITY` error value, not a Python exception shape;
- the canonical observation-shape helpers (`ExecutionObservation`,
  `AssuranceObservation`) round-trip losslessly, including unknown
  extension keys (EXT-005);
- the shared `WorkGraphPort` plan validator enforces the exact
  `PORT-WORK-001` `ERR-VALIDATION` cases.
"""

from __future__ import annotations

import importlib
import sys
import unittest
from typing import Any, Mapping, Optional, Sequence

from orc_werk.core.errors import ERR_UNSUPPORTED_CAPABILITY, ERR_VALIDATION, CoreError
from orc_werk.core.models import AssuranceRun, Candidate, Execution, Work
from orc_werk.ports.assurance import AssuranceObservation, AssurancePort
from orc_werk.ports.base import LIFECYCLE_STATE_SETTLED, Port
from orc_werk.ports.candidate import CANDIDATE_COMPARISON_SAME, CandidatePort
from orc_werk.ports.capabilities import CAP_EXEC_SEND, CAP_WORK_ATOMIC_CLAIM, validate_capabilities
from orc_werk.ports.execution import ExecutionObservation, ExecutionPort
from orc_werk.ports.journal import JournalPort
from orc_werk.ports.work_graph import WorkGraphPort, validate_plan


# ---------------------------------------------------------------------------
# Importability / dependency-direction (ARCH-REPOSITORY-STRUCTURE).
# ---------------------------------------------------------------------------


class PortsImportableTest(unittest.TestCase):
    def test_all_five_mandatory_ports_are_importable_and_abstract(self) -> None:
        for port_cls in (WorkGraphPort, ExecutionPort, CandidatePort, AssurancePort, JournalPort):
            self.assertTrue(issubclass(port_cls, Port))
            with self.assertRaises(TypeError):
                port_cls()  # abstract: cannot be instantiated directly.


class PortsImportGuardTest(unittest.TestCase):
    """Extends `tests/core/test_package_imports.py`'s import-guard pattern
    to `orc_werk.ports`."""

    def test_ports_import_pulls_in_no_third_party_modules(self) -> None:
        for name in list(sys.modules):
            if name == "orc_werk" or name.startswith("orc_werk."):
                del sys.modules[name]

        before = set(sys.modules)
        importlib.import_module("orc_werk.ports")
        after = set(sys.modules)

        new_modules = after - before
        stdlib_names = sys.stdlib_module_names
        third_party = {
            name
            for name in new_modules
            if not name.startswith("orc_werk") and name.split(".")[0] not in stdlib_names
        }
        self.assertEqual(third_party, set(), f"orc_werk.ports pulled in non-stdlib modules: {third_party}")

    def test_ports_import_pulls_in_no_forbidden_orc_werk_packages(self) -> None:
        # ports -> adapters is a forbidden edge (ARCH-REPOSITORY-STRUCTURE);
        # ports -> app/cli are equally forbidden by the same dependency table.
        for name in list(sys.modules):
            if name == "orc_werk" or name.startswith("orc_werk."):
                del sys.modules[name]

        importlib.import_module("orc_werk.ports")

        forbidden_prefixes = ("orc_werk.adapters", "orc_werk.app", "orc_werk.cli")
        leaked = {name for name in sys.modules if name.startswith(forbidden_prefixes)}
        self.assertEqual(leaked, set(), f"orc_werk.ports pulled in forbidden orc_werk packages: {leaked}")


# ---------------------------------------------------------------------------
# Fake adapters exercising the capability-gating pattern.
# ---------------------------------------------------------------------------


class _FakeWorkGraph(WorkGraphPort):
    """Advertises nothing -- exercises the unsupported-capability path for `claim`."""

    def capabilities(self) -> frozenset[str]:
        return validate_capabilities(frozenset())

    def create(self, *, delivery_run_id: str, plan: Mapping[str, Any]) -> Sequence[Work]:
        validate_plan(plan)
        return tuple(Work(id=entry["work_id"], delivery_run_id=delivery_run_id) for entry in plan["works"])

    def snapshot(self, *, delivery_run_id: str) -> Mapping[str, Any]:
        return {"delivery_run_id": delivery_run_id, "works": []}

    def ready(self, *, delivery_run_id: str) -> Sequence[Work]:
        return ()

    def claim(self, *, work_id: str) -> Mapping[str, Any]:
        self._require_capability(CAP_WORK_ATOMIC_CLAIM, operation="claim", work_id=work_id)
        raise AssertionError("unreachable: capability guard above always raises for this fake")

    def complete(self, *, work_id: str) -> Work:
        return Work(id=work_id, delivery_run_id="dr")

    def block(self, *, work_id: str, reason: str) -> Work:
        return Work(id=work_id, delivery_run_id="dr")


class _FakeExecution(ExecutionPort):
    """Advertises nothing -- exercises the unsupported-capability path for `send`."""

    def capabilities(self) -> frozenset[str]:
        return frozenset()

    def start(self, *, work_id: str, execution_request: Mapping[str, Any], idempotency_key: str) -> Execution:
        return Execution(id="e1", work_id=work_id, attempt_number=1)

    def inspect(self, *, execution_id: str) -> ExecutionObservation:
        return ExecutionObservation(state="settled", outcome="completed")

    def send(self, *, execution_id: str, message: Mapping[str, Any]) -> None:
        self._require_capability(CAP_EXEC_SEND, operation="send", execution_id=execution_id)

    def cancel(self, *, execution_id: str) -> None:
        raise NotImplementedError

    def resume(self, *, execution_id: str, resume_request: Mapping[str, Any]) -> Execution:
        raise NotImplementedError


class _FakeCandidate(CandidatePort):
    def capabilities(self) -> frozenset[str]:
        return frozenset()

    def identify(self, *, execution_id: str, artifact_refs: Optional[Mapping[str, Any]] = None) -> Optional[Candidate]:
        return None

    def current(self, *, work_id: str) -> Optional[Candidate]:
        return None

    def compare(self, *, candidate_a: Candidate, candidate_b: Candidate) -> str:
        return CANDIDATE_COMPARISON_SAME if candidate_a.fingerprint == candidate_b.fingerprint else "different"


class _FakeAssurance(AssurancePort):
    def capabilities(self) -> frozenset[str]:
        return frozenset()

    def request(self, *, candidate: Candidate, requirements: Mapping[str, Any], idempotency_key: str) -> AssuranceRun:
        return AssuranceRun(id="a1", candidate_id=candidate.id)

    def inspect(self, *, assurance_id: str) -> AssuranceObservation:
        return AssuranceObservation(state=LIFECYCLE_STATE_SETTLED, verdict="accepted", candidate_fingerprint="fp1")


class _FakeJournal(JournalPort):
    def capabilities(self) -> frozenset[str]:
        return frozenset()

    def append_fact(self, fact):  # type: ignore[override]
        raise NotImplementedError

    def append_decision(self, decision):  # type: ignore[override]
        raise NotImplementedError

    def append_effect_record(self, effect, *, dispatch_result):  # type: ignore[override]
        raise NotImplementedError

    def history(self, *, delivery_run_id: str):
        return ()

    def load_projection(self, *, delivery_run_id: str):
        return None


# ---------------------------------------------------------------------------
# Capability surface (INV-013 / SCN-006).
# ---------------------------------------------------------------------------


class CapabilitySurfaceTest(unittest.TestCase):
    def test_validate_capabilities_accepts_known_ids(self) -> None:
        caps = validate_capabilities({CAP_WORK_ATOMIC_CLAIM})
        self.assertEqual(caps, frozenset({CAP_WORK_ATOMIC_CLAIM}))

    def test_validate_capabilities_rejects_unknown_id(self) -> None:
        with self.assertRaises(ValueError):
            validate_capabilities({"CAP-NOT-A-REAL-CAPABILITY"})

    def test_supports_reflects_advertised_capabilities(self) -> None:
        adapter = _FakeExecution()
        self.assertFalse(adapter.supports(CAP_EXEC_SEND))

        class _SendCapableExecution(_FakeExecution):
            def capabilities(self) -> frozenset[str]:
                return frozenset({CAP_EXEC_SEND})

        capable = _SendCapableExecution()
        self.assertTrue(capable.supports(CAP_EXEC_SEND))
        # a capable adapter's send() does not raise (guard passes through).
        capable.send(execution_id="e1", message={"text": "hi"})

    def test_every_port_exposes_capabilities(self) -> None:
        for adapter in (_FakeWorkGraph(), _FakeExecution(), _FakeCandidate(), _FakeAssurance(), _FakeJournal()):
            self.assertIsInstance(adapter.capabilities(), frozenset)


# ---------------------------------------------------------------------------
# Unsupported-capability -> canonical ERR-UNSUPPORTED-CAPABILITY error value.
# ---------------------------------------------------------------------------


class UnsupportedCapabilityErrorTest(unittest.TestCase):
    def test_send_without_cap_exec_send_raises_canonical_error(self) -> None:
        adapter = _FakeExecution()
        with self.assertRaises(CoreError) as ctx:
            adapter.send(execution_id="e1", message={"text": "hi"})
        canonical = ctx.exception.to_canonical()
        self.assertEqual(canonical["error"], ERR_UNSUPPORTED_CAPABILITY)
        self.assertEqual(canonical["details"]["capability"], CAP_EXEC_SEND)
        self.assertEqual(canonical["details"]["operation"], "send")
        # portable, JSON-compatible -- never a Python exception/class shape.
        for forbidden in ("<class", "object at 0x", "Traceback"):
            self.assertNotIn(forbidden, repr(canonical))

    def test_claim_without_cap_work_atomic_claim_raises_canonical_error(self) -> None:
        adapter = _FakeWorkGraph()
        with self.assertRaises(CoreError) as ctx:
            adapter.claim(work_id="w1")
        canonical = ctx.exception.to_canonical()
        self.assertEqual(canonical["error"], ERR_UNSUPPORTED_CAPABILITY)
        self.assertEqual(canonical["details"]["capability"], CAP_WORK_ATOMIC_CLAIM)

    def test_unsupported_builds_without_raising(self) -> None:
        adapter = _FakeExecution()
        error = adapter._unsupported(CAP_EXEC_SEND, operation="send")
        self.assertIsInstance(error, CoreError)
        self.assertEqual(error.to_canonical()["error"], ERR_UNSUPPORTED_CAPABILITY)


# ---------------------------------------------------------------------------
# Canonical observation shapes: lossless round-trip incl. unknown extensions.
# ---------------------------------------------------------------------------


class ExecutionObservationRoundTripTest(unittest.TestCase):
    def test_round_trip_settled_completed(self) -> None:
        obs = ExecutionObservation(
            state="settled",
            outcome="completed",
            artifact_refs=("ref-1", {"kind": "diff", "path": "a.py"}),
            extensions={"some-unregistered-extension/v3": {"anything": [1, 2, None, True]}},
        )
        data = obs.to_dict()
        round_tripped = ExecutionObservation.from_dict(data)
        self.assertEqual(round_tripped, obs)
        self.assertEqual(round_tripped.extensions, obs.extensions)

    def test_rejects_unknown_state(self) -> None:
        with self.assertRaises(ValueError):
            ExecutionObservation(state="not-a-real-state")

    def test_rejects_unknown_outcome(self) -> None:
        with self.assertRaises(ValueError):
            ExecutionObservation(state="settled", outcome="not-a-real-outcome")


class AssuranceObservationRoundTripTest(unittest.TestCase):
    def test_round_trip_settled_with_final_candidate_and_unknown_extensions(self) -> None:
        obs = AssuranceObservation(
            state=LIFECYCLE_STATE_SETTLED,
            verdict="accepted",
            candidate_fingerprint="fp-c1",
            evidence_refs=("ev-1", "ev-2"),
            final_candidate={"id": "c2", "work_id": "w1", "execution_id": "e1", "fingerprint": "fp-c2"},
            extensions={
                "review-findings/v1": {"findings": []},
                "some-unregistered-extension/v9": {"nested": {"a": [1, {"b": None}]}},
            },
        )
        data = obs.to_dict()
        round_tripped = AssuranceObservation.from_dict(data)
        self.assertEqual(round_tripped, obs)
        self.assertEqual(round_tripped.extensions, obs.extensions)

    def test_settled_requires_candidate_fingerprint(self) -> None:
        with self.assertRaises(ValueError):
            AssuranceObservation(state=LIFECYCLE_STATE_SETTLED, verdict="accepted")

    def test_requested_does_not_require_candidate_fingerprint(self) -> None:
        obs = AssuranceObservation(state="requested")
        self.assertIsNone(obs.candidate_fingerprint)


# ---------------------------------------------------------------------------
# WorkGraphPort plan validation (PORT-WORK-001 ERR-VALIDATION cases).
# ---------------------------------------------------------------------------


class WorkGraphPlanValidationTest(unittest.TestCase):
    def test_valid_single_work_plan(self) -> None:
        validate_plan({"works": [{"work_id": "w1", "deps": []}]})

    def test_valid_fan_in_plan(self) -> None:
        validate_plan(
            {
                "works": [
                    {"work_id": "a", "deps": []},
                    {"work_id": "b", "deps": []},
                    {"work_id": "c", "deps": [{"work_id": "a", "condition": "accepted"}, {"work_id": "b", "condition": "accepted"}]},
                ]
            }
        )

    def test_rejects_empty_works_list(self) -> None:
        with self._assert_validation_error():
            validate_plan({"works": []})

    def test_rejects_duplicate_work_id(self) -> None:
        with self._assert_validation_error():
            validate_plan({"works": [{"work_id": "w1", "deps": []}, {"work_id": "w1", "deps": []}]})

    def test_rejects_dependency_on_unknown_work(self) -> None:
        with self._assert_validation_error():
            validate_plan({"works": [{"work_id": "w1", "deps": [{"work_id": "ghost", "condition": "accepted"}]}]})

    def test_rejects_self_dependency(self) -> None:
        with self._assert_validation_error():
            validate_plan({"works": [{"work_id": "w1", "deps": [{"work_id": "w1", "condition": "accepted"}]}]})

    def test_rejects_dependency_cycle(self) -> None:
        with self._assert_validation_error():
            validate_plan(
                {
                    "works": [
                        {"work_id": "a", "deps": [{"work_id": "b", "condition": "accepted"}]},
                        {"work_id": "b", "deps": [{"work_id": "a", "condition": "accepted"}]},
                    ]
                }
            )

    def _assert_validation_error(self):
        return _ExpectsCanonicalError(self, ERR_VALIDATION)


class _ExpectsCanonicalError:
    """Context manager asserting a `CoreError` carrying the given canonical
    `ERR-*` id is raised."""

    def __init__(self, test: unittest.TestCase, error_id: str) -> None:
        self._test = test
        self._error_id = error_id

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self._test.assertIsNotNone(exc, f"expected {self._error_id} but nothing was raised")
        self._test.assertIsInstance(exc, CoreError)
        self._test.assertEqual(exc.to_canonical()["error"], self._error_id)
        return True


if __name__ == "__main__":
    unittest.main()
