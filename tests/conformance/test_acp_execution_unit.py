"""Unit tests for `AcpExecution`'s unobservability-determination branches
and cancel post-verification (`TASK-M1-005` acceptance item: "unit tests
for the unobservability check branches ... plus cancel post-verification"),
against the fake `acpx` executable (`tests/conformance/
support_acpx_stub.py`).

The three branches from the task card's ruling and the spike's
"Determining unobservability" procedure
(`docs/reports/2026-08-28-acpx-pi-spike.md`):

1. **daemon dead, no recorded result** -> settle `failed` (an honest
   observation of a lost outcome, not a fabrication).
2. **result present** -> settle using it, regardless of daemon liveness
   (`running` status must never override a recorded `stopReason`).
3. **daemon alive, no recorded result yet** -> still `running`, never a
   timeout.

Each is exercised with a *fresh* `AcpExecution` instance for `inspect()`
(no local `_submitted_turns` cache), simulating the cross-process
crash-recovery case the card cares about: the process that submitted the
turn is gone, so `inspect()` must reconnect and reason from `acpx`'s
durable state alone.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from orc_werk.adapters.acp.execution import AcpExecution, session_name_for_idempotency_key
from orc_werk.cli.config import validate_config
from orc_werk.core.errors import CoreError, ERR_VALIDATION
from orc_werk.ports.base import LIFECYCLE_STATE_RUNNING, LIFECYCLE_STATE_SETTLED
from tests.conformance.support_acpx_stub import AcpxStubWorld


class AcpExecutionModelPinTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._world = AcpxStubWorld(Path(self._tmp.name))
        self._adapter = AcpExecution(env=self._world.env())

    def _start(self, requested: str, *, key: str, models: list[str]) -> str:
        session_name = session_name_for_idempotency_key(key)
        self._world.seed_models(session_name, models)
        self._adapter.start(
            work_id="model-work",
            execution_request={"prompt": "hi", "model": requested},
            idempotency_key=key,
        )
        return session_name

    def test_exact_match_pins_exact_advertised_id(self) -> None:
        exact = "openai-codex/gpt-5.6-luna"
        session_name = self._start(exact, key="model-exact", models=[exact, "vendor/sol"])
        record = self._world.session_record(session_name)
        self.assertIn({"key": "model", "value": exact}, record["config_sets"])

    def test_unique_case_insensitive_substring_resolves_and_pins(self) -> None:
        resolved = "openai-codex/gpt-5.6-luna"
        session_name = self._start(
            "LUNA", key="model-substring", models=[resolved, "openai-codex/gpt-5.6-sol"]
        )
        record = self._world.session_record(session_name)
        self.assertIn({"key": "model", "value": resolved}, record["config_sets"])

    def test_unknown_model_fails_closed_and_lists_advertised_ids(self) -> None:
        models = ["vendor/luna", "vendor/sol"]
        with self.assertRaises(CoreError) as caught:
            self._start("terra", key="model-unknown", models=models)
        self.assertIn("advertised ids", str(caught.exception))
        for model_id in models:
            self.assertIn(model_id, str(caught.exception))

    def test_ambiguous_model_fails_closed_and_lists_advertised_ids(self) -> None:
        models = ["vendor/luna", "vendor/luna-preview", "vendor/sol"]
        with self.assertRaises(CoreError) as caught:
            self._start("luna", key="model-ambiguous", models=models)
        self.assertIn("ambiguous", str(caught.exception))
        for model_id in models:
            self.assertIn(model_id, str(caught.exception))


class AcpExecutionTtlAndConfigTest(unittest.TestCase):
    def test_default_ttl_is_top_level_before_agent(self) -> None:
        argv = AcpExecution()._base_argv()
        self.assertEqual(argv[:5], ["acpx", "--format", "json", "--ttl", "0"])
        self.assertLess(argv.index("--ttl"), argv.index("pi"))

    def test_configured_ttl_is_top_level_before_agent(self) -> None:
        argv = AcpExecution(agent="pi", ttl=47)._base_argv()
        self.assertEqual(argv[argv.index("--ttl") : argv.index("--ttl") + 2], ["--ttl", "47"])
        self.assertLess(argv.index("--ttl"), argv.index("pi"))

    def test_negative_ttl_is_canonical_validation_error(self) -> None:
        with self.assertRaises(CoreError) as caught:
            validate_config({"execution": {"adapter": "acp", "cwd": "/tmp", "ttl": -1},
                             "candidate": {"adapter": "git", "repo_path": "/tmp"}})
        self.assertEqual(caught.exception.error["error"], ERR_VALIDATION)

    def test_non_integer_ttl_is_canonical_validation_error(self) -> None:
        with self.assertRaises(CoreError) as caught:
            validate_config({"execution": {"adapter": "acp", "cwd": "/tmp", "ttl": 1.5},
                             "candidate": {"adapter": "git", "repo_path": "/tmp"}})
        self.assertEqual(caught.exception.error["error"], ERR_VALIDATION)

    def test_ttl_is_rejected_for_non_acp_execution(self) -> None:
        with self.assertRaises(CoreError) as caught:
            validate_config({"execution": {"adapter": "scripted", "ttl": 0}})
        self.assertEqual(caught.exception.error["error"], ERR_VALIDATION)


class AcpExecutionUnobservabilityTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._world = AcpxStubWorld(Path(self._tmp.name))
        self._submitter = AcpExecution(env=self._world.env())

    def _start(self, *, work_id: str, idempotency_key: str, states):
        session_name = session_name_for_idempotency_key(idempotency_key)
        self._world.seed_script(session_name, [{"states": states, "outcome": "completed"}])
        ref = self._submitter.start(
            work_id=work_id,
            execution_request={"prompt": "hi"},
            idempotency_key=idempotency_key,
        )
        return ref, session_name

    # -- branch 1: daemon dead, no recorded result -> failed -----------------

    def test_daemon_dead_with_no_recorded_result_settles_failed(self) -> None:
        ref, session_name = self._start(
            work_id="w1", idempotency_key="dead-1", states=["running"]
        )
        # The turn never settles on its own (states never reach "settled");
        # force the daemon into the confirmed-dead state instead of ever
        # letting the turn complete.
        self._world.mark_daemon_dead(session_name, exit_code=137)

        fresh = AcpExecution(env=self._world.env())  # a different process
        observed = fresh.inspect(execution_id=ref.id)

        self.assertEqual(observed.state, LIFECYCLE_STATE_SETTLED)
        self.assertEqual(observed.outcome, "failed")
        provenance = observed.extensions["execution-session/v1"]
        self.assertNotIn("_orcw_unobservable", provenance)
        self.assertNotIn("unobservability", provenance)
        evidence = observed.extensions["acp-settlement/v1"]["unobservability"]
        self.assertEqual(evidence["lastAgentExitCode"], 137)

    def test_no_session_after_mid_turn_activity_settles_failed(self) -> None:
        ref, session_name = self._start(
            work_id="vanished", idempotency_key="vanished-mid-turn", states=["running"]
        )
        self._world.append_stream(
            session_name,
            {"jsonrpc": "2.0", "method": "session/update", "params": {
                "update": {"sessionUpdate": "agent_message_chunk", "content": {"text": "working"}}
            }},
        )
        record = self._world.session_record(session_name)
        assert record is not None
        record["closed"] = True
        self._world._save(session_name, record)

        observed = AcpExecution(env=self._world.env()).inspect(execution_id=ref.id)
        self.assertEqual(observed.state, LIFECYCLE_STATE_SETTLED)
        self.assertEqual(observed.outcome, "failed")
        self.assertEqual(
            observed.extensions["acp-settlement/v1"]["unobservability"],
            {"reason": "worker-vanished-mid-turn", "status": "no-session",
             "prompted": True, "stream_activity_seen": True},
        )

    def test_no_session_during_startup_with_empty_stream_stays_running(self) -> None:
        ref, session_name = self._start(
            work_id="startup-no-session", idempotency_key="startup-no-session", states=["running"]
        )
        record = self._world.session_record(session_name)
        assert record is not None
        record["closed"] = True
        self._world._save(session_name, record)

        observed = AcpExecution(env=self._world.env()).inspect(execution_id=ref.id)
        self.assertEqual(observed.state, LIFECYCLE_STATE_RUNNING)
        self.assertIsNone(observed.outcome)

    def test_startup_window_dead_with_live_owner_runs_then_completes(self) -> None:
        ref, session_name = self._start(
            work_id="startup", idempotency_key="startup-window", states=["running"]
        )
        # Exact false-fail signature from #157: no result frame, null exit,
        # and acpx's dead status while the lease-owning process is alive.
        self._world.set_dead_status(session_name, pid_alive=True, has_lease=True)

        fresh = AcpExecution(env=self._world.env())
        observed = fresh.inspect(execution_id=ref.id)
        self.assertEqual(observed.state, LIFECYCLE_STATE_RUNNING)
        self.assertIsNone(observed.outcome)

        self._world.append_stream(
            session_name,
            {"jsonrpc": "2.0", "id": 10, "result": {"stopReason": "end_turn"}},
        )
        completed = fresh.inspect(execution_id=ref.id)
        self.assertEqual(completed.state, LIFECYCLE_STATE_SETTLED)
        self.assertEqual(completed.outcome, "completed")

    def test_dead_with_owner_process_gone_settles_failed(self) -> None:
        ref, session_name = self._start(
            work_id="dead-pid", idempotency_key="dead-pid", states=["running"]
        )
        self._world.set_dead_status(session_name, pid_alive=False, has_lease=True)

        observed = AcpExecution(env=self._world.env()).inspect(execution_id=ref.id)
        self.assertEqual(observed.state, LIFECYCLE_STATE_SETTLED)
        self.assertEqual(observed.outcome, "failed")
        evidence = observed.extensions["acp-settlement/v1"]["unobservability"]
        self.assertEqual(evidence["status"], "dead")
        self.assertIs(evidence["pidAlive"], False)

    def test_nonzero_agent_exit_code_settles_failed(self) -> None:
        ref, session_name = self._start(
            work_id="dead-exit", idempotency_key="dead-exit", states=["running"]
        )
        self._world.set_agent_exit(session_name, exit_code=9)

        observed = AcpExecution(env=self._world.env()).inspect(execution_id=ref.id)
        self.assertEqual(observed.state, LIFECYCLE_STATE_SETTLED)
        self.assertEqual(observed.outcome, "failed")
        evidence = observed.extensions["acp-settlement/v1"]["unobservability"]
        self.assertEqual(evidence["lastAgentExitCode"], 9)

    def test_dead_status_omitting_pid_alive_stays_running(self) -> None:
        ref, session_name = self._start(
            work_id="dead-no-pid", idempotency_key="dead-no-pid", states=["running"]
        )
        # Production-realistic acpx 0.13.1 shape: dead status, no pidAlive
        # key, no stopReason, and null exit evidence.
        self._world.set_dead_status(session_name, omit_pid_alive=True)

        observed = AcpExecution(env=self._world.env()).inspect(execution_id=ref.id)
        self.assertEqual(observed.state, LIFECYCLE_STATE_RUNNING)
        self.assertIsNone(observed.outcome)

    def test_zero_exit_and_dead_with_live_owner_stays_running(self) -> None:
        ref, session_name = self._start(
            work_id="zero-exit", idempotency_key="zero-exit", states=["running"]
        )
        self._world.set_agent_exit(session_name, exit_code=0)
        self._world.set_dead_status(session_name, pid_alive=True, has_lease=True)

        observed = AcpExecution(env=self._world.env()).inspect(execution_id=ref.id)
        self.assertEqual(observed.state, LIFECYCLE_STATE_RUNNING)
        self.assertIsNone(observed.outcome)

    # -- branch 2: result present -> settle using it, regardless of status --

    def test_result_present_settles_even_though_status_would_read_alive(self) -> None:
        ref, session_name = self._start(
            work_id="w1", idempotency_key="settled-1", states=["settled"]
        )
        # Materialize the recorded result via the same-instance path first
        # (mirrors ScriptedExecution's "call inspect enough times").
        self._submitter.inspect(execution_id=ref.id)

        # Sanity: the stub reports the daemon as ordinarily alive -- this
        # is the "running can persist after settlement" trap the spike
        # documented; a fresh inspect() must not be fooled by it.
        record = self._world.session_record(session_name)
        self.assertFalse(record["force_daemon_dead"])

        fresh = AcpExecution(env=self._world.env())
        observed = fresh.inspect(execution_id=ref.id)
        self.assertEqual(observed.state, LIFECYCLE_STATE_SETTLED)
        self.assertEqual(observed.outcome, "completed")

    def test_end_turn_followed_by_retry_activity_stays_running(self) -> None:
        ref, session_name = self._start(
            work_id="retry", idempotency_key="retry-after-result", states=["running"]
        )
        self._world.append_stream(
            session_name,
            {"jsonrpc": "2.0", "id": 10, "result": {"stopReason": "end_turn"}},
        )
        self._world.append_stream(
            session_name,
            {
                "jsonrpc": "2.0",
                "method": "session/update",
                "params": {
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": "Retrying (attempt 1/3, waiting 2s)..."},
                    }
                },
            },
        )

        observed = AcpExecution(env=self._world.env()).inspect(execution_id=ref.id)
        self.assertEqual(observed.state, LIFECYCLE_STATE_RUNNING)
        self.assertIsNone(observed.outcome)
        evidence = observed.extensions["acp-settlement/v1"]["suppression"]
        self.assertEqual(evidence["stopReason"], "end_turn")
        self.assertEqual(evidence["laterRecordClass"], "agent_message_chunk")

    def test_terminal_end_turn_still_settles_completed(self) -> None:
        ref, session_name = self._start(
            work_id="terminal", idempotency_key="terminal-result", states=["running"]
        )
        self._world.append_stream(
            session_name,
            {"jsonrpc": "2.0", "id": 10, "result": {"stopReason": "end_turn"}},
        )

        observed = AcpExecution(env=self._world.env()).inspect(execution_id=ref.id)
        self.assertEqual(observed.state, LIFECYCLE_STATE_SETTLED)
        self.assertEqual(observed.outcome, "completed")

    def test_passive_reconnect_records_after_end_turn_do_not_block_settlement(self) -> None:
        ref, session_name = self._start(
            work_id="passive", idempotency_key="passive-after-result", states=["running"]
        )
        self._world.append_stream(
            session_name,
            {"jsonrpc": "2.0", "id": 10, "result": {"stopReason": "end_turn"}},
        )
        self._world.append_stream(
            session_name,
            {"jsonrpc": "2.0", "id": 20, "method": "initialize", "params": {}},
        )
        self._world.append_stream(
            session_name,
            {"jsonrpc": "2.0", "id": 20, "result": {"protocolVersion": 1}},
        )
        self._world.append_stream(
            session_name,
            {"jsonrpc": "2.0", "id": 21, "method": "session/load", "params": {}},
        )
        self._world.append_stream(
            session_name,
            {"jsonrpc": "2.0", "id": 21, "result": {"configOptions": []}},
        )

        observed = AcpExecution(env=self._world.env()).inspect(execution_id=ref.id)
        self.assertEqual(observed.state, LIFECYCLE_STATE_SETTLED)
        self.assertEqual(observed.outcome, "completed")

    def test_ambiguous_record_after_end_turn_stays_running(self) -> None:
        ref, session_name = self._start(
            work_id="ambiguous", idempotency_key="ambiguous-after-result", states=["running"]
        )
        self._world.append_stream(
            session_name,
            {"jsonrpc": "2.0", "id": 10, "result": {"stopReason": "end_turn"}},
        )
        self._world.append_stream(session_name, {"jsonrpc": "2.0", "future": {"kind": "new"}})

        observed = AcpExecution(env=self._world.env()).inspect(execution_id=ref.id)
        self.assertEqual(observed.state, LIFECYCLE_STATE_RUNNING)
        evidence = observed.extensions["acp-settlement/v1"]["suppression"]
        self.assertEqual(evidence["laterRecordClass"], "unknown")

    def test_result_present_maps_cancelled_stop_reason(self) -> None:
        ref, _session_name = self._start(
            work_id="w1", idempotency_key="cancelled-1", states=["settled"]
        )
        # Rewrite the scripted entry's outcome to "cancelled" before the
        # first show() materializes it.
        session_name = session_name_for_idempotency_key("cancelled-1")
        self._world.set_script_entry(session_name, 0, {"states": ["settled"], "outcome": "cancelled"})

        observed = self._submitter.inspect(execution_id=ref.id)
        self.assertEqual(observed.state, LIFECYCLE_STATE_SETTLED)
        self.assertEqual(observed.outcome, "cancelled")

    def test_result_present_maps_unknown_stop_reason_to_failed(self) -> None:
        # A refusal/permission-denied-shaped stopReason must NEVER read as
        # success -- the mapping-doc footgun ("permission-denied runs can
        # exit looking successful ... MUST map to canonical failure").
        ref, _session_name = self._start(
            work_id="w1", idempotency_key="refused-1", states=["settled"]
        )
        session_name = session_name_for_idempotency_key("refused-1")
        self._world.set_script_entry(
            session_name, 0, {"states": ["settled"], "outcome": "something-else-entirely"}
        )

        observed = self._submitter.inspect(execution_id=ref.id)
        self.assertEqual(observed.state, LIFECYCLE_STATE_SETTLED)
        self.assertEqual(observed.outcome, "failed")

    # -- branch 3: daemon alive, no recorded result yet -> running, never a
    # -- timeout. --

    def test_daemon_alive_with_no_recorded_result_stays_running(self) -> None:
        ref, _session_name = self._start(
            work_id="w1", idempotency_key="alive-1", states=["running"]
        )
        fresh = AcpExecution(env=self._world.env())
        observed = fresh.inspect(execution_id=ref.id)
        self.assertEqual(observed.state, LIFECYCLE_STATE_RUNNING)
        self.assertIsNone(observed.outcome)

        # Calling inspect() again (simulating a later poll) with the
        # daemon still alive and still no result must not flip to any
        # settled outcome -- there is no timeout path.
        observed_again = fresh.inspect(execution_id=ref.id)
        self.assertEqual(observed_again.state, LIFECYCLE_STATE_RUNNING)


class AcpExecutionCancelPostVerificationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._world = AcpxStubWorld(Path(self._tmp.name))
        self._adapter = AcpExecution(env=self._world.env())

    def test_cancel_on_in_flight_turn_settles_cancelled(self) -> None:
        session_name = session_name_for_idempotency_key("cancel-inflight")
        self._world.seed_script(session_name, [{"states": ["running"], "outcome": "completed"}])
        ref = self._adapter.start(
            work_id="w1", execution_request={"prompt": "hi"}, idempotency_key="cancel-inflight"
        )
        self._adapter.cancel(execution_id=ref.id)  # cancel() post-verifies internally
        observed = self._adapter.inspect(execution_id=ref.id)
        self.assertEqual(observed.state, LIFECYCLE_STATE_SETTLED)
        self.assertEqual(observed.outcome, "cancelled")

    def test_cancel_with_nothing_in_flight_does_not_fabricate_a_cancellation(self) -> None:
        # Footgun: a cancel that exits 0 may mean "nothing to cancel" -- an
        # already-settled turn's real outcome must survive an idle cancel.
        session_name = session_name_for_idempotency_key("cancel-idle")
        self._world.seed_script(session_name, [{"states": ["settled"], "outcome": "completed"}])
        ref = self._adapter.start(
            work_id="w1", execution_request={"prompt": "hi"}, idempotency_key="cancel-idle"
        )
        self._adapter.inspect(execution_id=ref.id)  # materialize + observe "completed"

        self._adapter.cancel(execution_id=ref.id)  # nothing in flight -> no-op cancel

        observed = self._adapter.inspect(execution_id=ref.id)
        self.assertEqual(observed.state, LIFECYCLE_STATE_SETTLED)
        self.assertEqual(observed.outcome, "completed")  # unchanged, NOT "cancelled"


if __name__ == "__main__":
    unittest.main()
