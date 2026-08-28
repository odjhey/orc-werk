"""`CONF-EXEC-*` conformance for `AcpExecution` (`TASK-M1-005`), driven
against a fake `acpx` executable on `PATH` (`tests/conformance/
support_acpx_stub.py`) -- no real `acpx`/Node/`pi-acp` install required.

This reuses the exact same `ExecutionPortConformance` mixin
`ScriptedExecutionConformanceTest` runs (`test_execution_conformance.py`),
via `_StubAcpxExecutionHarness`: a thin `ExecutionPort` wrapper that
pre-seeds the fake `acpx`'s per-session script (mirroring
`ScriptedExecution`'s own per-work_id attempt-counting rule) before
delegating every real operation to a genuine `AcpExecution` instance
talking to the fake binary over a real subprocess boundary.

Two mixin tests are overridden with a documented skip -- both test
behavior that only a scripted test double can honestly provide, not a
real provider-driving adapter (see each override's docstring):

- `test_inspect_transports_scripted_artifact_refs_and_extensions_losslessly`
  assumes `inspect()` echoes back caller-scripted `artifact_refs`/
  `extensions` verbatim. `AcpExecution.inspect()`'s `extensions` are
  derived from real observed session provenance (`execution-session/v1`),
  not caller-injected passthrough content -- there is no such channel in
  `PORT-EXEC-001`'s `execution_request` for a real adapter to honor.
- `test_capability_honesty_resume_exact_when_advertised` assumes
  constructing an adapter that advertises `CAP-EXEC-RESUME-EXACT` is a
  legal fixture setup. `AcpExecution` raises at construction time if asked
  to advertise it (the capability-durability rule, `CONTRACT-CAPABILITIES`
  -- unmeetable per the 2026-08-28 spike, `docs/adapters/acp/mapping.md`),
  so there is no legal way to build that fixture for a real adapter.

Every other mixin test -- including the card's explicitly named
acceptance items (idempotent start, stable identity, running-vs-settled,
`test_conf_exec_004_unsupported_resume_strength_fails_explicitly`) --
runs unmodified.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, Iterable, Mapping

from orc_werk.adapters.acp.execution import AcpExecution, session_name_for_idempotency_key
from orc_werk.core.models import Execution
from orc_werk.ports.base import LIFECYCLE_STATE_SETTLED
from orc_werk.ports.execution import ExecutionObservation, ExecutionPort
from tests.conformance.support_acpx_stub import AcpxStubWorld
from tests.conformance.test_execution_conformance import ExecutionPortConformance


class _StubAcpxExecutionHarness(ExecutionPort):
    """Pre-seeds the fake `acpx`'s per-session script from a
    `ScriptedExecution`-shaped `script` mapping, then delegates every
    `ExecutionPort` operation to a real `AcpExecution` instance talking to
    the fake binary. See module docstring."""

    def __init__(
        self,
        *,
        script: Mapping[str, Iterable[Mapping[str, Any]]],
        capabilities: Iterable[str],
        world: AcpxStubWorld,
    ) -> None:
        self._script = {work_id: list(entries) for work_id, entries in script.items()}
        self._world = world
        self._real = AcpExecution(capabilities=capabilities, env=world.env())
        self._attempts_by_work: dict[str, list[str]] = {}
        self._seeded_keys: set[str] = set()

    def capabilities(self) -> frozenset[str]:
        return self._real.capabilities()

    def start(
        self, *, work_id: str, execution_request: Mapping[str, Any], idempotency_key: str
    ) -> Execution:
        if idempotency_key not in self._seeded_keys:
            attempts = self._attempts_by_work.setdefault(work_id, [])
            attempt_index = len(attempts)
            entries = self._script.get(work_id, [])
            if attempt_index < len(entries):
                session_name = session_name_for_idempotency_key(idempotency_key)
                self._world.seed_script(session_name, [entries[attempt_index]])
            attempts.append(idempotency_key)
            self._seeded_keys.add(idempotency_key)
        request = dict(execution_request)
        request.setdefault("prompt", "conformance-fixture-prompt")
        return self._real.start(
            work_id=work_id, execution_request=request, idempotency_key=idempotency_key
        )

    def inspect(self, *, execution_id: str) -> ExecutionObservation:
        return self._real.inspect(execution_id=execution_id)

    def send(self, *, execution_id: str, message: Mapping[str, Any]) -> None:
        self._real.send(execution_id=execution_id, message=message)

    def cancel(self, *, execution_id: str) -> None:
        self._real.cancel(execution_id=execution_id)

    def resume(self, *, execution_id: str, resume_request: Mapping[str, Any]) -> Execution:
        return self._real.resume(execution_id=execution_id, resume_request=resume_request)


class AcpExecutionConformanceTest(ExecutionPortConformance, unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._world = AcpxStubWorld(Path(self._tmp.name))

    def make_execution(
        self, *, script: Mapping[str, Any], capabilities: Iterable[str] = ()
    ) -> ExecutionPort:
        return _StubAcpxExecutionHarness(script=script, capabilities=capabilities, world=self._world)

    # -- documented overrides: see module docstring. --

    def test_inspect_transports_scripted_artifact_refs_and_extensions_losslessly(self) -> None:
        self.skipTest(
            "AcpExecution derives extensions from real acpx session provenance "
            "(execution-session/v1), not from caller-scripted passthrough content "
            "-- see docs/adapters/acp/mapping.md 'Lossy mappings'."
        )

    def test_capability_honesty_resume_exact_when_advertised(self) -> None:
        self.skipTest(
            "AcpExecution raises at construction time if asked to advertise "
            "CAP-EXEC-RESUME-EXACT (capability-durability rule, unmeetable per "
            "the 2026-08-28 spike) -- there is no legal fixture for this test."
        )


class AcpExecutionCrossProcessIdempotencyTest(unittest.TestCase):
    """Issue #57 regression: `AcpExecution.start()` must be idempotent
    across processes, not just within one. Each test constructs multiple
    SEPARATE `AcpExecution` instances against one shared `AcpxStubWorld`
    -- standing in for `Orchestrator._reconcile_ports` replaying
    `FX-START-EXECUTION` from a fresh, empty-cache adapter instance on
    every ordinary `orc dispatch` process (`docs/adapters/acp/mapping.md`
    "Idempotency behavior") -- and asserts on the stub's own submission
    counter (`AcpxStubWorld.prompt_submission_count`), never on either
    instance's in-process cache, so the assertion cannot pass by
    accident via CONF-EXEC-002's same-instance fast path."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._world = AcpxStubWorld(Path(self._tmp.name))

    def _instance(self) -> AcpExecution:
        # A fresh AcpExecution with an empty in-process cache -- the
        # closest in-test stand-in for "a new orc dispatch process."
        return AcpExecution(env=self._world.env())

    def test_two_processes_racing_an_in_flight_attempt_submit_exactly_once(self) -> None:
        # Edge case (a): session exists, prompt already submitted, still
        # running -> the second "process" must not resubmit.
        key = "idem-57-race"
        session_name = session_name_for_idempotency_key(key)
        # states=["running"] only, mirroring the wiring smoke test's
        # never-advances-past-running fixture -- the outstanding turn is
        # still genuinely in flight when the second instance polls.
        self._world.seed_script(session_name, [{"states": ["running"], "outcome": "completed"}])

        first = self._instance()
        second = self._instance()

        first_execution = first.start(
            work_id="work-1", execution_request={"prompt": "reply with ping"}, idempotency_key=key
        )
        second_execution = second.start(
            work_id="work-1", execution_request={"prompt": "reply with ping"}, idempotency_key=key
        )

        self.assertEqual(self._world.prompt_submission_count(session_name), 1)
        self.assertEqual(first_execution.id, second_execution.id)

    def test_crash_between_ensure_and_submit_still_submits_exactly_once(self) -> None:
        # Edge case (d): sessions ensure ran (a session record exists)
        # but the process that ran it died before ever queuing a prompt
        # -- no lastPromptAt/messages yet. This is the legitimate replay
        # case: the next process/instance MUST still submit once, not
        # treat the bare session record as "already started."
        key = "idem-57-crash"
        session_name = session_name_for_idempotency_key(key)
        self._world.seed_script(session_name, [{"outcome": "completed"}])

        crashed = self._instance()
        # Reach only as far as `sessions ensure` -- the adapter's own
        # subprocess plumbing, exercised directly to simulate a process
        # that died between `ensure` and the prompt submit that follows
        # it in start(), without duplicating acpx's session-creation
        # protocol by hand.
        crashed._run(["sessions", "ensure", "-s", session_name])
        self.assertEqual(self._world.prompt_submission_count(session_name), 0)

        recovering = self._instance()
        recovering.start(
            work_id="work-2", execution_request={"prompt": "reply with ping"}, idempotency_key=key
        )

        self.assertEqual(self._world.prompt_submission_count(session_name), 1)

    def test_completed_turn_is_not_resubmitted(self) -> None:
        # Edge case (b): session exists, turn already completed -> no
        # resubmit; inspect() (not start()) is what settles the Work.
        key = "idem-57-done"
        session_name = session_name_for_idempotency_key(key)
        self._world.seed_script(session_name, [{"states": ["settled"], "outcome": "completed"}])

        first = self._instance()
        execution = first.start(
            work_id="work-3", execution_request={"prompt": "reply with ping"}, idempotency_key=key
        )
        observation = first.inspect(execution_id=execution.id)
        self.assertEqual(observation.state, LIFECYCLE_STATE_SETTLED)
        self.assertEqual(observation.outcome, "completed")
        self.assertEqual(self._world.prompt_submission_count(session_name), 1)

        second = self._instance()
        second.start(
            work_id="work-3", execution_request={"prompt": "reply with ping"}, idempotency_key=key
        )

        self.assertEqual(self._world.prompt_submission_count(session_name), 1)


if __name__ == "__main__":
    unittest.main()
