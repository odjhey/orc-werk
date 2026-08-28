"""`CONF-EXEC-*` conformance suite (`PORT-EXECUTION`).

`ExecutionPortConformance` is a reusable mixin (not itself a `TestCase`,
so unittest discovery does not collect it directly): any current or future
`ExecutionPort` implementation runs the same suite by subclassing it
alongside `unittest.TestCase` and implementing `make_execution()`
(`docs/architecture/repository-structure.md` -- "every future real adapter
must run the applicable same suite").
"""

from __future__ import annotations

import unittest
from typing import Any, Iterable, Mapping

from orc_werk.adapters.scripted import ScriptedExecution
from orc_werk.core.errors import CoreError
from orc_werk.ports.base import LIFECYCLE_STATE_RUNNING, LIFECYCLE_STATE_SETTLED
from orc_werk.ports.capabilities import (
    CAP_EXEC_CANCEL,
    CAP_EXEC_RESUME_BEST_EFFORT,
    CAP_EXEC_RESUME_EXACT,
    CAP_EXEC_SEND,
)
from orc_werk.ports.execution import ExecutionPort


class ExecutionPortConformance:
    def make_execution(
        self, *, script: Mapping[str, Any], capabilities: Iterable[str] = ()
    ) -> ExecutionPort:
        raise NotImplementedError

    # -- CONF-EXEC-001: start returns a stable logical execution identity. --

    def test_conf_exec_001_start_returns_stable_execution_identity(self) -> None:
        adapter = self.make_execution(script={"w1": [{"outcome": "completed"}]})
        ref = adapter.start(work_id="w1", execution_request={}, idempotency_key="k1")
        # calling start again with the SAME idempotency key returns the
        # identical, stable execution identity -- not a fresh one.
        ref_again = adapter.start(work_id="w1", execution_request={}, idempotency_key="k1")
        self.assertEqual(ref.id, ref_again.id)
        observed = adapter.inspect(execution_id=ref.id)
        self.assertEqual(observed.state, LIFECYCLE_STATE_SETTLED)

    # -- CONF-EXEC-002: repeated start w/ same key does not create two logical executions. --

    def test_conf_exec_002_repeated_start_same_key_no_duplicate_execution(self) -> None:
        adapter = self.make_execution(
            script={"w1": [{"outcome": "completed"}, {"outcome": "failed"}]}
        )
        first = adapter.start(work_id="w1", execution_request={}, idempotency_key="k1")
        second = adapter.start(work_id="w1", execution_request={}, idempotency_key="k1")
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.attempt_number, second.attempt_number)
        # a genuinely new idempotency key consumes the NEXT scripted
        # attempt, proving the repeat above did not silently advance it.
        third = adapter.start(work_id="w1", execution_request={}, idempotency_key="k2")
        self.assertNotEqual(third.id, first.id)
        self.assertEqual(third.attempt_number, 2)

    # -- CONF-EXEC-003: inspect distinguishes running from terminal settlement. --

    def test_conf_exec_003_inspect_distinguishes_running_from_settled(self) -> None:
        adapter = self.make_execution(
            script={"w1": [{"states": ["running", "settled"], "outcome": "completed"}]}
        )
        ref = adapter.start(work_id="w1", execution_request={}, idempotency_key="k1")
        first = adapter.inspect(execution_id=ref.id)
        self.assertEqual(first.state, LIFECYCLE_STATE_RUNNING)
        self.assertIsNone(first.outcome)
        second = adapter.inspect(execution_id=ref.id)
        self.assertEqual(second.state, LIFECYCLE_STATE_SETTLED)
        self.assertEqual(second.outcome, "completed")
        # terminal settlement is sticky.
        third = adapter.inspect(execution_id=ref.id)
        self.assertEqual(third.state, LIFECYCLE_STATE_SETTLED)

    # -- CONF-EXEC-004: unsupported resume strength fails explicitly. --

    def test_conf_exec_004_unsupported_resume_strength_fails_explicitly(self) -> None:
        adapter = self.make_execution(
            script={"w1": [{"outcome": "completed"}]},
            capabilities={CAP_EXEC_RESUME_BEST_EFFORT},
        )
        ref = adapter.start(work_id="w1", execution_request={}, idempotency_key="k1")
        with self.assertRaises(CoreError) as ctx:
            adapter.resume(
                execution_id=ref.id, resume_request={"capability": CAP_EXEC_RESUME_EXACT}
            )
        canonical = ctx.exception.to_canonical()
        self.assertEqual(canonical["error"], "ERR-UNSUPPORTED-CAPABILITY")
        self.assertEqual(canonical["details"]["capability"], CAP_EXEC_RESUME_EXACT)

    # -- Capability honesty: every advertised CAP exercised by a passing test. --

    def test_capability_honesty_send_when_advertised(self) -> None:
        adapter = self.make_execution(
            script={"w1": [{"outcome": "completed"}]}, capabilities={CAP_EXEC_SEND}
        )
        ref = adapter.start(work_id="w1", execution_request={}, idempotency_key="k1")
        adapter.send(execution_id=ref.id, message={"text": "hi"})  # does not raise

    def test_capability_honesty_send_when_not_advertised_yields_canonical_error(self) -> None:
        adapter = self.make_execution(script={"w1": [{"outcome": "completed"}]}, capabilities=())
        ref = adapter.start(work_id="w1", execution_request={}, idempotency_key="k1")
        with self.assertRaises(CoreError) as ctx:
            adapter.send(execution_id=ref.id, message={"text": "hi"})
        self.assertEqual(ctx.exception.to_canonical()["error"], "ERR-UNSUPPORTED-CAPABILITY")

    def test_capability_honesty_cancel_when_advertised(self) -> None:
        adapter = self.make_execution(
            script={"w1": [{"states": ["running", "settled"], "outcome": "completed"}]},
            capabilities={CAP_EXEC_CANCEL},
        )
        ref = adapter.start(work_id="w1", execution_request={}, idempotency_key="k1")
        adapter.cancel(execution_id=ref.id)
        observed = adapter.inspect(execution_id=ref.id)
        self.assertEqual(observed.state, LIFECYCLE_STATE_SETTLED)
        self.assertEqual(observed.outcome, "cancelled")

    def test_capability_honesty_cancel_when_not_advertised_yields_canonical_error(self) -> None:
        adapter = self.make_execution(script={"w1": [{"outcome": "completed"}]}, capabilities=())
        ref = adapter.start(work_id="w1", execution_request={}, idempotency_key="k1")
        with self.assertRaises(CoreError) as ctx:
            adapter.cancel(execution_id=ref.id)
        self.assertEqual(ctx.exception.to_canonical()["error"], "ERR-UNSUPPORTED-CAPABILITY")

    def test_capability_honesty_resume_best_effort_when_advertised(self) -> None:
        adapter = self.make_execution(
            script={"w1": [{"outcome": "completed"}]}, capabilities={CAP_EXEC_RESUME_BEST_EFFORT}
        )
        ref = adapter.start(work_id="w1", execution_request={}, idempotency_key="k1")
        resumed = adapter.resume(
            execution_id=ref.id, resume_request={"capability": CAP_EXEC_RESUME_BEST_EFFORT}
        )
        self.assertEqual(resumed.id, ref.id)

    def test_capability_honesty_resume_exact_when_advertised(self) -> None:
        adapter = self.make_execution(
            script={"w1": [{"outcome": "completed"}]}, capabilities={CAP_EXEC_RESUME_EXACT}
        )
        ref = adapter.start(work_id="w1", execution_request={}, idempotency_key="k1")
        resumed = adapter.resume(
            execution_id=ref.id, resume_request={"capability": CAP_EXEC_RESUME_EXACT}
        )
        self.assertEqual(resumed.id, ref.id)


class ScriptedExecutionConformanceTest(ExecutionPortConformance, unittest.TestCase):
    def make_execution(
        self, *, script: Mapping[str, Any], capabilities: Iterable[str] = ()
    ) -> ExecutionPort:
        return ScriptedExecution(script=script, capabilities=capabilities)


if __name__ == "__main__":
    unittest.main()
