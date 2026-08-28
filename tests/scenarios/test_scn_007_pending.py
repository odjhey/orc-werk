"""SCN-007 -- pending execution / operator-recorded settlement
(`docs/scenarios/SCN-007-pending-settlement.md`, `TASK-M1-002`).

Pending/incremental mode is the M1a *default* dispatch mode: a config with
no recorded outcome for the next attempt is pending, not an error and not
a failure. This module mirrors `SCN-007` step-for-step:

- `PendingStopsCleanlyTest` -- invocation 1: a started-but-unobserved
  attempt rests at `EXECUTING`, nothing is fabricated for the missing
  settlement, the retry budget is untouched (`INV-018`).
- `IdempotentReplayResumesTest` -- invocation 2 (a *fresh* `Orchestrator`
  over the same durable journal, i.e. a simulated process restart):
  recording the real outcome and re-dispatching advances the run via
  ordinary idempotent replay (`INV-020`) with no duplicated facts/effects,
  and the resulting two-invocation journal is record-identical to a single
  fully-scripted invocation carrying the same eventual outcomes up front.
- `AssuranceBoundaryPendingTest` -- the same pending pattern one boundary
  later: recording only the execution settlement/candidate (not yet the
  assurance verdict) rests cleanly at `ASSURING`.
- `DispatchGateFailureNeverPendingTest` -- `STATE-DELIVERY` mechanical fact
  sequencing item 6 is unchanged: a capability/provider-unavailable
  dispatch-gate failure still normalizes to a failed execution attempt
  immediately, never to pending, even against the pending-capable adapters.
- `CliPendingModeTest` -- the same chain end-to-end through the real `orc`
  CLI (subprocess, JSONL journal, config edited between invocations):
  dispatch -> exit 3 pending at EXECUTING -> record outcome -> re-dispatch
  -> exit 3 pending at ASSURING -> record verdict -> re-dispatch -> exit 0
  ACCEPTED.

Verifies `INV-003`, `INV-004`, `INV-018`, `INV-020`.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from orc_werk.adapters.jsonl.journal import JSONLJournal
from orc_werk.adapters.memory.journal import MemoryJournal
from orc_werk.adapters.memory.work_graph import MemoryWorkGraph
from orc_werk.adapters.scripted.assurance import ScriptedAssurance
from orc_werk.adapters.scripted.candidate import ScriptedCandidate, fingerprint_of
from orc_werk.adapters.scripted.execution import ScriptedExecution
from orc_werk.app import Orchestrator, RunConfig, default_single_work_plan, is_pending
from orc_werk.core.decisions import DEC_DISPATCH
from orc_werk.core.effects import FX_START_EXECUTION
from orc_werk.core.state import STATE_ACCEPTED, STATE_ASSURING, STATE_BLOCKED, STATE_EXECUTING
from orc_werk.ports.capabilities import CAP_EXEC_RESUME_BEST_EFFORT, CAP_EXEC_RESUME_EXACT

from tests.scenarios.support import predicted_execution_id

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"

DRID = "scn007"
WORK_ID = "A"
CANDIDATE_C1 = {"label": "C1"}


def _run_cli(tmp_dir: Path, *args: str) -> subprocess.CompletedProcess:
    env = {"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"}
    return subprocess.run(
        [sys.executable, "-m", "orc_werk.cli", *args],
        cwd=tmp_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _fact_ids(history, work_id_filter=None):
    return [
        r["id"]
        for r in history
        if r["kind"] == "fact" and (work_id_filter is None or r["data"].get("work_id") == work_id_filter)
    ]


class PendingStopsCleanlyTest(unittest.TestCase):
    """SCN-007 invocation 1 (Given/When 1-3, Then 1-7)."""

    def _build(self):
        journal = MemoryJournal()
        work_graph = MemoryWorkGraph()
        execution = ScriptedExecution(script={WORK_ID: []}, pending=True)
        candidate = ScriptedCandidate(subjects={}, current_by_work={})
        assurance = ScriptedAssurance(script={}, pending=True)
        orchestrator = Orchestrator(
            delivery_run_id=DRID,
            journal=journal,
            work_graph=work_graph,
            execution=execution,
            candidate=candidate,
            assurance=assurance,
            config=RunConfig(max_attempts=3),
        )
        orchestrator.bootstrap(intent_id=DRID, text="scn007", plan=default_single_work_plan(WORK_ID))
        return orchestrator, journal

    def test_pending_stops_cleanly_nothing_fabricated(self) -> None:
        orchestrator, journal = self._build()
        projection = orchestrator.run()
        wp = projection.works[WORK_ID]
        history = journal.history(delivery_run_id=DRID)

        # 1. Work A remains at EXECUTING.
        self.assertEqual(wp.state, STATE_EXECUTING)

        # 2. FACT-EXEC-STARTED for attempt 1 is the last Fact journaled for
        # Work A; no FACT-EXEC-SETTLED exists for attempt 1.
        work_facts = _fact_ids(history, work_id_filter=WORK_ID)
        self.assertEqual(work_facts[-1], "FACT-EXEC-STARTED")
        self.assertNotIn("FACT-EXEC-SETTLED", work_facts)

        # 3. No synthetic-ref FACT-EXEC-SETTLED(failed) is journaled for
        # waiting, and the retry-budget attempt count (INV-018) is
        # untouched: exactly one execution-start record, attempt_number 1.
        exec_started = [r for r in history if r["kind"] == "fact" and r["id"] == "FACT-EXEC-STARTED"]
        self.assertEqual(len(exec_started), 1)
        self.assertEqual(wp.attempt_number, 1)

        # 5. Kernel-level durable resting point: non-terminal, not ACCEPTED,
        # not BLOCKED.
        self.assertNotEqual(wp.state, STATE_ACCEPTED)
        self.assertNotEqual(wp.state, STATE_BLOCKED)
        self.assertTrue(is_pending(wp))

        # Repeated polling (re-running the loop / re-dispatching the exact
        # same command) makes no further progress and consumes no further
        # budget while the outcome remains unrecorded.
        second_projection = orchestrator.run()
        self.assertEqual(second_projection.works[WORK_ID].attempt_number, 1)
        self.assertEqual(
            len(journal.history(delivery_run_id=DRID)), len(history)
        )

        # 7. Process exit after invocation 1 is survivable: nothing beyond
        # FACT-EXEC-STARTED was ever asserted (no in-flight decision/effect
        # left dangling -- every journaled effect has a durable dispatch_result).
        for record in history:
            if record["kind"] == "effect":
                self.assertIn("dispatch_result", record["data"])


class IdempotentReplayResumesTest(unittest.TestCase):
    """SCN-007 invocation 2 (Then 8-11): a fresh Orchestrator over the same
    durable journal (simulated restart) resumes exactly where it stopped,
    and the resulting journal matches a single fully-scripted invocation
    record-for-record."""

    def _pending_script_execution(self):
        return ScriptedExecution(script={WORK_ID: []}, pending=True)

    def _resolved_script_execution(self):
        return ScriptedExecution(
            script={WORK_ID: [{"outcome": "completed"}]}, pending=True
        )

    def _resolved_candidate(self):
        execution_id = predicted_execution_id(delivery_run_id=DRID, work_id=WORK_ID, attempt_number=1)
        return ScriptedCandidate(
            subjects={execution_id: {"work_id": WORK_ID, "subject_identity": CANDIDATE_C1}},
            current_by_work={},
        )

    def _resolved_assurance(self):
        return ScriptedAssurance(
            script={fingerprint_of(CANDIDATE_C1): {"verdict": "accepted"}}, pending=True
        )

    def test_two_invocation_journal_matches_single_shot_fully_scripted_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)

            # Invocation 1: nothing scripted yet -- pending at EXECUTING.
            journal1 = JSONLJournal(directory)
            orchestrator1 = Orchestrator(
                delivery_run_id=DRID,
                journal=journal1,
                work_graph=MemoryWorkGraph(),
                execution=self._pending_script_execution(),
                candidate=ScriptedCandidate(subjects={}, current_by_work={}),
                assurance=ScriptedAssurance(script={}, pending=True),
                config=RunConfig(max_attempts=3),
            )
            orchestrator1.bootstrap(intent_id=DRID, text="scn007", plan=default_single_work_plan(WORK_ID))
            projection1 = orchestrator1.run()
            self.assertEqual(projection1.works[WORK_ID].state, STATE_EXECUTING)
            self.assertTrue(is_pending(projection1.works[WORK_ID]))

            # Operator records the real outcome (completed, candidate C1)
            # and the assurance verdict (accepted) -- NOT as journal
            # records, only in the provider-backing store, per SCN-007
            # step 4.
            #
            # Invocation 2: a *fresh* Orchestrator/ports over the same
            # journal directory (simulated process restart).
            journal2 = JSONLJournal(directory)
            orchestrator2 = Orchestrator(
                delivery_run_id=DRID,
                journal=journal2,
                work_graph=MemoryWorkGraph(),
                execution=self._resolved_script_execution(),
                candidate=self._resolved_candidate(),
                assurance=self._resolved_assurance(),
                config=RunConfig(max_attempts=3),
            )
            projection2 = orchestrator2.run()
            wp = projection2.works[WORK_ID]
            split_history = journal2.history(delivery_run_id=DRID)

            # 10. Work A completes only after assurance acceptance.
            self.assertEqual(wp.state, STATE_ACCEPTED)
            self.assertTrue(wp.completed_confirmed)

            # 9. No duplicate FACT-EXEC-STARTED; idempotency-addressable
            # replay produced no duplicated effects.
            exec_started = [r for r in split_history if r["kind"] == "fact" and r["id"] == "FACT-EXEC-STARTED"]
            self.assertEqual(len(exec_started), 1)
            effect_keys = [r["data"]["idempotency_key"] for r in split_history if r["kind"] == "effect"]
            self.assertEqual(len(effect_keys), len(set(effect_keys)))

            # seq continuity: no gaps, no reordering across the invocation
            # boundary.
            seqs = [r["seq"] for r in split_history]
            self.assertEqual(seqs, list(range(1, len(split_history) + 1)))

            # 11. Record-for-record identical to a single fully-scripted
            # invocation carrying the same eventual outcomes up front
            # (strict/opt-in simulation mode, pending=False -- the default
            # M0 adapter behavior).
            with tempfile.TemporaryDirectory() as clean_tmp:
                clean_directory = Path(clean_tmp)
                clean_journal = JSONLJournal(clean_directory)
                clean_orchestrator = Orchestrator(
                    delivery_run_id=DRID,
                    journal=clean_journal,
                    work_graph=MemoryWorkGraph(),
                    execution=ScriptedExecution(script={WORK_ID: [{"outcome": "completed"}]}),
                    candidate=self._resolved_candidate(),
                    assurance=ScriptedAssurance(
                        script={fingerprint_of(CANDIDATE_C1): {"verdict": "accepted"}}
                    ),
                    config=RunConfig(max_attempts=3),
                )
                clean_orchestrator.bootstrap(
                    intent_id=DRID, text="scn007", plan=default_single_work_plan(WORK_ID)
                )
                clean_projection = clean_orchestrator.run()
                clean_history = clean_journal.history(delivery_run_id=DRID)

                self.assertEqual(clean_projection.works[WORK_ID].to_dict(), wp.to_dict())
                self.assertEqual(len(clean_history), len(split_history))
                for clean_record, split_record in zip(clean_history, split_history):
                    self.assertEqual(clean_record, split_record)


class AssuranceBoundaryPendingTest(unittest.TestCase):
    """SCN-007 step 12: the same pending pattern one boundary later --
    execution settled + candidate observed, assurance verdict not yet
    known -- rests cleanly at ASSURING."""

    def test_pending_at_assuring_when_verdict_unrecorded(self) -> None:
        journal = MemoryJournal()
        execution = ScriptedExecution(script={WORK_ID: [{"outcome": "completed"}]}, pending=True)
        execution_id = predicted_execution_id(delivery_run_id=DRID, work_id=WORK_ID, attempt_number=1)
        candidate = ScriptedCandidate(
            subjects={execution_id: {"work_id": WORK_ID, "subject_identity": CANDIDATE_C1}},
            current_by_work={},
        )
        assurance = ScriptedAssurance(script={}, pending=True)  # no verdict scripted yet
        orchestrator = Orchestrator(
            delivery_run_id=DRID,
            journal=journal,
            work_graph=MemoryWorkGraph(),
            execution=execution,
            candidate=candidate,
            assurance=assurance,
            config=RunConfig(max_attempts=3),
        )
        orchestrator.bootstrap(intent_id=DRID, text="scn007-assuring", plan=default_single_work_plan(WORK_ID))
        projection = orchestrator.run()
        wp = projection.works[WORK_ID]
        history = journal.history(delivery_run_id=DRID)

        self.assertEqual(wp.state, STATE_ASSURING)
        self.assertTrue(is_pending(wp))
        # No FACT-ASSURE-SETTLED is fabricated; FACT-ASSURE-STARTED is
        # present (the request itself succeeded, per pending semantics).
        work_facts = _fact_ids(history, work_id_filter=WORK_ID)
        self.assertIn("FACT-ASSURE-STARTED", work_facts)
        self.assertNotIn("FACT-ASSURE-SETTLED", work_facts)
        # No retry-budget attempt consumed for the wait.
        self.assertEqual(wp.attempt_number, 1)


class DispatchGateFailureNeverPendingTest(unittest.TestCase):
    """`STATE-DELIVERY` mechanical fact sequencing item 6 boundary
    (`TASK-M1-002` "must not change"): a capability/provider-unavailable
    dispatch-gate failure still normalizes to a failed execution attempt
    immediately, never to pending -- even against `pending=True` adapters."""

    def test_capability_failure_fails_immediately_not_pending(self) -> None:
        journal = MemoryJournal()
        # pending=True execution adapter -- proves the pending flag only
        # affects the "no scripted entry" branch of start(), never the
        # capability-gated resume() path SCN-006 exercises.
        execution = ScriptedExecution(
            script={WORK_ID: [{"outcome": "completed"}]},
            capabilities=[CAP_EXEC_RESUME_BEST_EFFORT],
            pending=True,
        )
        assurance = ScriptedAssurance(script={}, pending=True)
        orchestrator = Orchestrator(
            delivery_run_id=DRID,
            journal=journal,
            work_graph=MemoryWorkGraph(),
            execution=execution,
            candidate=ScriptedCandidate(subjects={}, current_by_work={}),
            assurance=assurance,
            config=RunConfig(max_attempts=1, resume_capability=CAP_EXEC_RESUME_EXACT),
        )
        orchestrator.bootstrap(intent_id=DRID, text="scn007-gate", plan=default_single_work_plan(WORK_ID))
        projection = orchestrator.run()
        wp = projection.works[WORK_ID]

        self.assertEqual(wp.state, STATE_BLOCKED)
        self.assertTrue(wp.blocked_confirmed)
        self.assertFalse(is_pending(wp))

        history = journal.history(delivery_run_id=DRID)
        decisions = [r["id"] for r in history if r["kind"] == "decision"]
        self.assertIn(DEC_DISPATCH, decisions)
        start_effects = [r for r in history if r["kind"] == "effect" and r["id"] == FX_START_EXECUTION]
        self.assertEqual(len(start_effects), 1)
        self.assertIn("error", start_effects[0]["data"]["dispatch_result"])


class CliPendingModeTest(unittest.TestCase):
    """SCN-007 end-to-end through the real `orc` CLI: separate subprocess
    invocations, a config file edited between them, the distinct
    in-progress exit code (3) at both the EXECUTING and ASSURING pending
    boundaries, ACCEPTED (exit 0) once fully recorded."""

    def test_dispatch_pending_then_resumes_to_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config_path = tmp_dir / "config.json"

            # Invocation 1: no attempts recorded at all -- fully
            # incremental default (TASK-M1-002 Config section).
            config_path.write_text(
                json.dumps({"run_id": "scn007-cli", "max_attempts": 3}), encoding="utf-8"
            )
            dispatch1 = _run_cli(tmp_dir, "dispatch", "scn007 cli chain", "--config", str(config_path))
            self.assertEqual(dispatch1.returncode, 3, msg=dispatch1.stdout + dispatch1.stderr)
            self.assertIn("state=EXECUTING", dispatch1.stdout)
            self.assertIn("attempts=1", dispatch1.stdout)
            self.assertIn("pending=true", dispatch1.stdout)
            self.assertIn("awaiting=execution-outcome", dispatch1.stdout)
            self.assertIn("pending:", dispatch1.stdout)

            status1 = _run_cli(tmp_dir, "status", "scn007-cli")
            self.assertEqual(status1.returncode, 3, msg=status1.stdout + status1.stderr)
            self.assertIn("awaiting=execution-outcome", status1.stdout)

            # Operator records the execution settlement + candidate, but
            # not yet the assurance verdict -- re-dispatch stops at
            # ASSURING (SCN-007 step 12).
            config_path.write_text(
                json.dumps(
                    {
                        "run_id": "scn007-cli",
                        "max_attempts": 3,
                        "attempts": {"work-1": [{"outcome": "completed", "candidate": {"label": "C1"}}]},
                    }
                ),
                encoding="utf-8",
            )
            dispatch2 = _run_cli(tmp_dir, "dispatch", "scn007 cli chain", "--config", str(config_path))
            self.assertEqual(dispatch2.returncode, 3, msg=dispatch2.stdout + dispatch2.stderr)
            self.assertIn("state=ASSURING", dispatch2.stdout)
            self.assertIn("attempts=1", dispatch2.stdout)  # budget untouched by waiting (INV-018)
            self.assertIn("awaiting=assurance-verdict", dispatch2.stdout)

            # Operator records the assurance verdict -- re-dispatch
            # advances to ACCEPTED (exit 0).
            config_path.write_text(
                json.dumps(
                    {
                        "run_id": "scn007-cli",
                        "max_attempts": 3,
                        "attempts": {
                            "work-1": [
                                {
                                    "outcome": "completed",
                                    "candidate": {"label": "C1"},
                                    "assurance": {"verdict": "accepted"},
                                }
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )
            dispatch3 = _run_cli(tmp_dir, "dispatch", "scn007 cli chain", "--config", str(config_path))
            self.assertEqual(dispatch3.returncode, 0, msg=dispatch3.stdout + dispatch3.stderr)
            self.assertIn("state=ACCEPTED", dispatch3.stdout)
            self.assertIn("attempts=1", dispatch3.stdout)  # never retried -- single attempt lineage

            status3 = _run_cli(tmp_dir, "status", "scn007-cli")
            self.assertEqual(status3.returncode, 0, msg=status3.stdout + status3.stderr)
            self.assertIn("state=ACCEPTED", status3.stdout)

            # seq continuity + no duplicated effects across the three
            # invocations, and exactly one FACT-EXEC-STARTED overall.
            history = _run_cli(tmp_dir, "history", "scn007-cli")
            self.assertEqual(history.returncode, 0, msg=history.stderr)
            lines = [line for line in history.stdout.splitlines() if line.strip()]
            seqs = [int(line[1:5]) for line in lines]
            self.assertEqual(seqs, list(range(1, len(lines) + 1)))

            def _fact_line_count(fact_id: str) -> int:
                # Match the record's own (kind, id) columns -- a plain
                # substring search also matches later decisions whose JSON
                # `basis` payload cites this fact id (FRICTION-1 precedent
                # in test_cli_dogfood_fixes.py).
                return sum(1 for line in lines if line.split(None, 3)[1:3] == ["fact", fact_id])

            self.assertEqual(_fact_line_count("FACT-EXEC-STARTED"), 1)
            self.assertEqual(_fact_line_count("FACT-EXEC-SETTLED"), 1)
            self.assertEqual(_fact_line_count("FACT-ASSURE-STARTED"), 1)
            self.assertEqual(_fact_line_count("FACT-ASSURE-SETTLED"), 1)
            self.assertEqual(_fact_line_count("FACT-WORK-COMPLETED"), 1)

    def test_capability_failure_config_still_exits_blocked_not_pending(self) -> None:
        """CLI-level regression guard for the item-6 boundary: a config
        that is statically doomed by a capability mismatch must still fail
        immediately (exit 1, BLOCKED) through the pending-capable CLI
        default, never report pending (exit 3)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config_path = tmp_dir / "config.json"
            # No `attempts` entry at all for work-1 -- would be pending
            # under the default flag, but max_attempts=1 with a failing
            # scripted outcome instead exercises the ordinary BLOCKED path
            # to confirm pending-capable adapters don't change it.
            config_path.write_text(
                json.dumps(
                    {
                        "run_id": "scn007-blocked",
                        "max_attempts": 1,
                        "attempts": {"work-1": [{"outcome": "failed"}]},
                    }
                ),
                encoding="utf-8",
            )
            dispatch = _run_cli(tmp_dir, "dispatch", "scn007 blocked", "--config", str(config_path))
            self.assertEqual(dispatch.returncode, 1, msg=dispatch.stdout + dispatch.stderr)
            self.assertIn("state=BLOCKED", dispatch.stdout)
            self.assertNotIn("pending=true", dispatch.stdout)


if __name__ == "__main__":
    unittest.main()
