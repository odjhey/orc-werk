"""Unit tests for `NoMistakesAssurance`'s verdict-mapping table and for
`orc_werk.adapters.no_mistakes.toon.parse_toon`'s tolerance (`TASK-M2-001`
acceptance item: "unit tests for the verdict mapping table and TOON parse
tolerance"), against the fake `no-mistakes` executable (`tests/
conformance/support_no_mistakes_stub.py`).

The verdict-mapping table this exercises (full rationale:
`docs/adapters/no-mistakes/mapping.md` "Verdict mapping"):

| Observed `no-mistakes` state                              | Verdict       |
|---|---|
| `run.status == "completed"`, `outcome: passed`             | `accepted`    |
| `run.status == "completed"`, `outcome: failed`             | `rejected`    |
| `run.status == "completed"`, `outcome` missing/unrecognized| `inconclusive`|
| parked gate, 1+ findings                                   | `rejected`    |
| parked gate, 0 findings                                    | `inconclusive`|
| `run.status in {cancelled, aborted, failed}` (no gate)      | `inconclusive`|
| `run.status == "running"`, no gate                          | `running` (not settled) |
| no run observed for this exact `assurance_id` yet           | `requested` (not settled) |
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from orc_werk.adapters.no_mistakes.assurance import NoMistakesAssurance
from orc_werk.adapters.no_mistakes.toon import parse_toon
from orc_werk.core.errors import CoreError
from orc_werk.core.models import Candidate
from orc_werk.ports.base import LIFECYCLE_STATE_REQUESTED, LIFECYCLE_STATE_RUNNING, LIFECYCLE_STATE_SETTLED
from tests.conformance.support_no_mistakes_stub import NoMistakesStubWorld


class NoMistakesAssuranceVerdictMappingTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._world = NoMistakesStubWorld(Path(self._tmp.name))

    def _adapter(self) -> NoMistakesAssurance:
        return NoMistakesAssurance(
            repo_path=self._world.repo_path,
            env=self._world.env(),
            spawn_poll_timeout_s=2.0,
            spawn_poll_interval_s=0.02,
        )

    def _candidate(self, fingerprint: str, *, head_sha: str | None = None) -> Candidate:
        subject = {"head_sha": head_sha} if head_sha else {"note": fingerprint}
        return Candidate(
            id=f"cand-{fingerprint}",
            work_id="w1",
            execution_id=f"e-{fingerprint}",
            subject_identity=subject,
            fingerprint=fingerprint,
        )

    def _request(self, adapter: NoMistakesAssurance, *, fingerprint: str, key: str, head_sha=None):
        candidate = self._candidate(fingerprint, head_sha=head_sha)
        return adapter.request(candidate=candidate, requirements={"intent": "verify"}, idempotency_key=key)

    # -- completed / outcome mapping --------------------------------------

    def test_outcome_passed_maps_to_accepted(self) -> None:
        adapter = self._adapter()
        run = self._request(adapter, fingerprint="fp-a", key="k-a")
        self._world.set_outcome(self._world.active_run_id(), "passed")
        observed = adapter.inspect(assurance_id=run.id)
        self.assertEqual(observed.state, LIFECYCLE_STATE_SETTLED)
        self.assertEqual(observed.verdict, "accepted")

    def test_outcome_failed_maps_to_rejected(self) -> None:
        adapter = self._adapter()
        run = self._request(adapter, fingerprint="fp-b", key="k-b")
        self._world.set_outcome(self._world.active_run_id(), "failed")
        observed = adapter.inspect(assurance_id=run.id)
        self.assertEqual(observed.state, LIFECYCLE_STATE_SETTLED)
        self.assertEqual(observed.verdict, "rejected")

    def test_completed_with_unrecognized_outcome_maps_to_inconclusive(self) -> None:
        adapter = self._adapter()
        run = self._request(adapter, fingerprint="fp-c", key="k-c")
        # "flaky" is not a value this adapter's verdict table recognizes --
        # never guessed toward accepted.
        self._world.set_outcome(self._world.active_run_id(), "flaky")
        observed = adapter.inspect(assurance_id=run.id)
        self.assertEqual(observed.verdict, "inconclusive")

    # -- gate / findings mapping -------------------------------------------

    def test_parked_gate_with_findings_maps_to_rejected_with_review_findings_v1(self) -> None:
        adapter = self._adapter()
        run = self._request(adapter, fingerprint="fp-d", key="k-d")
        self._world.set_gate(
            self._world.active_run_id(),
            step="review",
            findings=[
                {
                    "id": "hardcoded-secret",
                    "severity": "error",
                    "file": "a.py",
                    "action": "auto-fix",
                    "description": "a hardcoded secret",
                }
            ],
        )
        observed = adapter.inspect(assurance_id=run.id)
        self.assertEqual(observed.verdict, "rejected")
        findings = observed.extensions["review-findings/v1"]["findings"]
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding["severity"], "high")
        self.assertEqual(finding["disposition"], "blocking")
        self.assertEqual(finding["category"], "security")
        self.assertEqual(finding["status"], "open")
        self.assertTrue(finding["evidence"])

    def test_parked_gate_with_no_findings_maps_to_inconclusive(self) -> None:
        adapter = self._adapter()
        run = self._request(adapter, fingerprint="fp-e", key="k-e")
        self._world.set_gate(self._world.active_run_id(), step="review", findings=[])
        observed = adapter.inspect(assurance_id=run.id)
        self.assertEqual(observed.verdict, "inconclusive")
        self.assertNotIn("review-findings/v1", observed.extensions)

    def test_warning_severity_finding_maps_to_non_blocking_medium(self) -> None:
        adapter = self._adapter()
        run = self._request(adapter, fingerprint="fp-f", key="k-f")
        self._world.set_gate(
            self._world.active_run_id(),
            step="review",
            findings=[
                {
                    "id": "dead-code",
                    "severity": "warning",
                    "file": "b.py",
                    "action": "auto-fix",
                    "description": "unused function",
                }
            ],
        )
        observed = adapter.inspect(assurance_id=run.id)
        # A parked gate is still rejected regardless of individual finding
        # severity (mapping doc rationale: no-mistakes' own review policy
        # already declined to let the candidate proceed automatically).
        self.assertEqual(observed.verdict, "rejected")
        finding = observed.extensions["review-findings/v1"]["findings"][0]
        self.assertEqual(finding["severity"], "medium")
        self.assertEqual(finding["disposition"], "non-blocking")

    # -- terminal-without-outcome mapping ------------------------------------

    def test_cancelled_run_maps_to_inconclusive(self) -> None:
        adapter = self._adapter()
        run = self._request(adapter, fingerprint="fp-g", key="k-g")
        self._world.set_status(self._world.active_run_id(), "cancelled")
        observed = adapter.inspect(assurance_id=run.id)
        self.assertEqual(observed.verdict, "inconclusive")

    # -- non-terminal mapping -----------------------------------------------

    def test_running_with_no_gate_is_not_settled(self) -> None:
        adapter = self._adapter()
        run = self._request(adapter, fingerprint="fp-h", key="k-h")
        observed = adapter.inspect(assurance_id=run.id)
        self.assertEqual(observed.state, LIFECYCLE_STATE_RUNNING)
        self.assertIsNone(observed.verdict)

    def test_unrecognized_assurance_id_is_requested_not_an_error(self) -> None:
        adapter = self._adapter()
        # Well-formed shape, but no such run id was ever created by this world.
        fake_id = f"no-mistakes:fp-zzzzzzzzzzzzzzzzzzzzzzzz:STUB9999999999999999999999:{self._world.repo_path}"
        observed = adapter.inspect(assurance_id=fake_id)
        self.assertEqual(observed.state, LIFECYCLE_STATE_REQUESTED)

    def test_malformed_assurance_id_raises_not_found(self) -> None:
        adapter = self._adapter()
        with self.assertRaises(CoreError) as ctx:
            adapter.inspect(assurance_id="not-a-real-id")
        self.assertEqual(ctx.exception.to_canonical()["error"], "ERR-NOT-FOUND")

    # -- mechanical never-push (PR #80 fix round, finding B) ----------------

    def test_every_spawn_passes_skip_push_mechanical_never_push(self) -> None:
        """Never-push must be MECHANICAL, not incidental: omitting `--yes`
        only prevents gate auto-resolution -- a clean candidate with no
        gates runs the full pipeline INCLUDING the push step (confirmed
        empirically against the real CLI; the mapping doc's "Judge-only
        ruling" records the probe: `--skip push` completes a clean run
        with `push,skipped`, `pushed_head` empty, local branch head
        untouched). Every `axi run` spawn must therefore carry `--skip
        push` -- asserted against the stub's own record of the exact
        `--skip` value the invocation carried."""
        adapter = self._adapter()
        self._request(adapter, fingerprint="fp-skip", key="k-skip")
        run_id = self._world.active_run_id()
        assert run_id is not None
        self.assertIn("push", self._world.run_skip_args(run_id))

    # -- cross-process-style idempotency (fresh instance) -------------------

    def test_fresh_adapter_instance_reaches_same_settlement(self) -> None:
        """INV-020: a fresh process/instance re-inspecting the same
        `assurance_id` must reach the identical verdict observation --
        mirrors `AcpExecutionCrossProcessIdempotencyTest`'s crash-recovery
        style assertions for `AcpExecution`."""
        first = self._adapter()
        run = self._request(first, fingerprint="fp-i", key="k-i")
        self._world.set_outcome(self._world.active_run_id(), "passed")

        second = self._adapter()  # fresh instance, empty in-process caches
        observed = second.inspect(assurance_id=run.id)
        self.assertEqual(observed.state, LIFECYCLE_STATE_SETTLED)
        self.assertEqual(observed.verdict, "accepted")

    def test_active_run_without_any_readable_head_is_refused(self) -> None:
        first = self._adapter()
        self._request(first, fingerprint="fp-unknown-owner", key="k-unknown-owner", head_sha="a" * 40)
        run_id = self._world.active_run_id()
        assert run_id is not None
        self._world.set_head_shape(
            run_id, head=None, emit_run_head=False, emit_branch_sync=False
        )

        with self.assertRaises(CoreError) as raised:
            self._request(
                self._adapter(), fingerprint="fp-unknown-candidate", key="k-unknown-candidate", head_sha="a" * 40
            )
        self.assertEqual(raised.exception.error["error"], "ERR-UNSAFE-STATE")
        self.assertIn("abort or await it", raised.exception.error["message"])
        self.assertEqual(self._world.run_count(), 1)

    def test_active_run_with_divergent_run_block_head_is_refused(self) -> None:
        first = self._adapter()
        self._request(first, fingerprint="fp-divergent-owner", key="k-divergent-owner", head_sha="b" * 40)
        run_id = self._world.active_run_id()
        assert run_id is not None
        self._world.set_head_shape(
            run_id, head="b" * 40, emit_run_head=True, emit_branch_sync=False
        )

        with self.assertRaises(CoreError) as raised:
            self._request(
                self._adapter(), fingerprint="fp-divergent-candidate", key="k-divergent-candidate", head_sha="c" * 40
            )
        self.assertEqual(raised.exception.error["error"], "ERR-UNSAFE-STATE")
        self.assertEqual(raised.exception.error["details"]["observed_head"], "b" * 40)
        self.assertEqual(self._world.run_count(), 1)

    def test_active_run_with_matching_run_block_head_is_adopted(self) -> None:
        first = self._adapter()
        candidate = self._candidate("fp-run-head-match", head_sha="d" * 40)
        run1 = first.request(candidate=candidate, requirements={"intent": "x"}, idempotency_key="k-match")
        run_id = self._world.active_run_id()
        assert run_id is not None
        self._world.set_head_shape(
            run_id, head="d" * 40, emit_run_head=True, emit_branch_sync=False
        )

        run2 = self._adapter().request(
            candidate=candidate, requirements={"intent": "x"}, idempotency_key="k-match"
        )
        self.assertEqual(run1.id, run2.id)
        self.assertEqual(self._world.run_count(), 1)

    def test_active_run_is_adopted_not_respawned_across_instances(self) -> None:
        """A fresh instance calling request() with the SAME idempotency_key
        for a candidate whose run is already active must adopt it, never
        spawn a second `axi run` (mirrors the acp adapter's issue #57
        cross-process idempotency discipline, best-effort here since
        no-mistakes assigns opaque run ids -- see mapping doc
        'Limitations')."""
        first = self._adapter()
        candidate = self._candidate("fp-j", head_sha="f" * 40)
        self._world.set_next_head("f" * 40)
        run1 = first.request(candidate=candidate, requirements={"intent": "x"}, idempotency_key="k-j")
        self.assertEqual(self._world.run_count(), 1)

        second = self._adapter()  # fresh instance, empty in-process cache
        run2 = second.request(candidate=candidate, requirements={"intent": "x"}, idempotency_key="k-j")
        self.assertEqual(run1.id, run2.id)
        self.assertEqual(self._world.run_count(), 1)


class ParseToonTest(unittest.TestCase):
    def test_empty_input_returns_empty_dict(self) -> None:
        self.assertEqual(parse_toon(""), {})
        self.assertEqual(parse_toon("   \n  \n"), {})

    def test_nested_scalars_and_blocks(self) -> None:
        text = "run:\n  id: \"abc123\"\n  status: running\n  count: 3\n  ok: true\n  bad: false\n"
        parsed = parse_toon(text)
        self.assertEqual(
            parsed, {"run": {"id": "abc123", "status": "running", "count": 3, "ok": True, "bad": False}}
        )

    def test_table_with_quoted_comma_and_escaped_quote_field(self) -> None:
        text = (
            "gate:\n"
            "  findings[1]{id,severity,description}:\n"
            '    hardcoded-secret,error,"a value, with a comma and \\"quotes\\" inside"\n'
        )
        parsed = parse_toon(text)
        findings = parsed["gate"]["findings"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["id"], "hardcoded-secret")
        self.assertEqual(findings[0]["severity"], "error")
        self.assertEqual(findings[0]["description"], 'a value, with a comma and "quotes" inside')

    def test_bracket_suffix_stripped_from_stored_key(self) -> None:
        text = "steps[9]{step,status}:\n  intent,completed\n"
        parsed = parse_toon(text)
        self.assertIn("steps", parsed)
        self.assertNotIn("steps[9]", parsed)
        self.assertEqual(parsed["steps"], [{"step": "intent", "status": "completed"}])

    def test_unrecognized_lines_are_tolerated_not_fatal(self) -> None:
        text = "no active run\n---\nrun:\n  status: running\n"
        parsed = parse_toon(text)
        # "no active run" and "---" have no `key: value` shape and are
        # silently skipped rather than raising.
        self.assertEqual(parsed, {"run": {"status": "running"}})

    def test_sibling_keys_after_a_table_pop_correctly(self) -> None:
        text = "run:\n  steps[1]{a}:\n    x\nbranch_sync:\n  state: behind\n"
        parsed = parse_toon(text)
        self.assertEqual(parsed["run"]["steps"], [{"a": "x"}])
        self.assertEqual(parsed["branch_sync"], {"state": "behind"})


if __name__ == "__main__":
    unittest.main()
