"""Issue #240 -- journaled budget is the single authority for every verb
(`docs/scenarios/SCN-008-replay-budget.md`'s issue #240 amendment): a
`--max-attempts` flag on first dispatch journals into `FX-CREATE-WORK` but
was not persisted into the run's `config.json`; a bare `--run-id` resume
then evaluated retry policy under the config-derived default instead of the
journaled budget, journaling a `DEC-RETRY` -> `FACT-EXEC-STARTED` the run's
own journal already forbade, then wedging `status`/`history`/`record` with
`ERR-CONFLICT` on that same fact while `dispatch` kept advancing -- one
journal, two reconstructed states.

- (a) `Scn240RepeatIssueReproTest`: the issue's exact 5-command repro,
  post-fix.
- (b) `Scn240MatchOrRefuseTest`: R2 -- an explicit `--max-attempts` that
  disagrees with an existing run's journaled budget is refused with
  `ERR-VALIDATION`; an equal value is a no-op.
- (c) `Scn240PersistedConfigCarriesBudgetTest`: R3 -- a flag-created run's
  persisted `config.json` carries the budget.
- (d) `Scn240ReplayAssertionFiresTest`: R4 -- a divergent record injected
  outside the ordinary decision path makes `Orchestrator.
  _assert_replay_consistent` fail loudly (never silently wedge).
- (e) `Scn240ReplayDeterminismTest`: for the fixed flow, the read-side
  (`JSONLJournal.load_projection`) and write-side (`Orchestrator.
  projection`) folds of one journal agree exactly.

Verifies: `PORT-JOURNAL-005`, `CONF-JOURNAL-003`, `INV-018`, `INV-019`,
`CONTRACT-DURABILITY`, `ERR-VALIDATION`, `ERR-CONFLICT`.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from orc_werk.adapters.jsonl.journal import JSONLJournal
from orc_werk.app.orchestrator import Orchestrator, RunConfig
from orc_werk.core.effects import FX_START_EXECUTION
from orc_werk.core.errors import CoreError
from orc_werk.core.facts import FACT_EXEC_STARTED, make_fact
from orc_werk.core.state import STATE_BLOCKED

from tests.scenarios.support import build_run

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


def cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "orc_werk.cli", *args],
        cwd=root,
        env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=30,
    )


class Scn240RepeatIssueReproTest(unittest.TestCase):
    """(a) The issue's exact 5-command repro, post-fix."""

    def test_bare_resume_does_not_retry_past_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "cfg.json").write_text(json.dumps({}), encoding="utf-8")

            first = cli(
                root, "dispatch", "budget probe", "--config", "cfg.json",
                "--run-id", "probe", "--max-attempts", "1", "--journal", "./.orc",
            )
            self.assertEqual(first.returncode, 3, first.stdout + first.stderr)  # EXIT_PENDING

            recorded = cli(root, "record", "probe", "--work", "work-1", "--outcome", "failed", "--journal", "./.orc")
            self.assertEqual(recorded.returncode, 0, recorded.stdout + recorded.stderr)

            # The bug: this used to journal DEC-RETRY -> FACT-EXEC-STARTED
            # for attempt 2 (a decision the journaled max_attempts=1
            # already forbade) and exit EXIT_PENDING (3). Post-fix it must
            # recognize the budget is already exhausted and BLOCK instead.
            resumed = cli(root, "dispatch", "--run-id", "probe", "--journal", "./.orc")
            self.assertEqual(resumed.returncode, 1, resumed.stdout + resumed.stderr)
            self.assertIn("state=BLOCKED", resumed.stdout)
            self.assertIn("retry-budget-exhausted", resumed.stdout)

            # status/history/record must all read the journal cleanly --
            # never the wedge-specific ERR-CONFLICT ("FACT-EXEC-STARTED
            # illegal from state 'BLOCKED'") the pre-fix journal produced.
            status = cli(root, "status", "probe", "--journal", "./.orc")
            self.assertEqual(status.returncode, 1, status.stdout + status.stderr)
            self.assertIn("state=BLOCKED", status.stdout)

            history = cli(root, "history", "probe", "--journal", "./.orc")
            self.assertEqual(history.returncode, 0, history.stdout + history.stderr)
            self.assertNotIn("ERR-CONFLICT", history.stdout)
            # Exactly one FACT-EXEC-STARTED -- no illegal second attempt.
            self.assertEqual(history.stdout.count("FACT-EXEC-STARTED"), 1)

            # `record` now sees an ordinary, expected conflict (the run is
            # legitimately BLOCKED, not awaiting an outcome) -- not the
            # wedge's inexplicable illegal-transition conflict.
            record_again = cli(root, "record", "probe", "--work", "work-1", "--outcome", "failed", "--journal", "./.orc")
            self.assertEqual(record_again.returncode, 2, record_again.stdout + record_again.stderr)
            error = json.loads(record_again.stdout or record_again.stderr)
            self.assertEqual(error["error"], "ERR-CONFLICT")
            self.assertIn("not awaiting an execution outcome", error["message"])


class Scn240MatchOrRefuseTest(unittest.TestCase):
    """(b) R2: an explicit --max-attempts differing from an existing run's
    journaled budget is refused; an equal value is a no-op."""

    def _bootstrap(self, root: Path, run_id: str, max_attempts: int) -> None:
        (root / "cfg.json").write_text(json.dumps({}), encoding="utf-8")
        first = cli(
            root, "dispatch", "budget probe", "--config", "cfg.json",
            "--run-id", run_id, "--max-attempts", str(max_attempts), "--journal", "./.orc",
        )
        self.assertEqual(first.returncode, 3, first.stdout + first.stderr)
        recorded = cli(root, "record", run_id, "--work", "work-1", "--outcome", "failed", "--journal", "./.orc")
        self.assertEqual(recorded.returncode, 0, recorded.stdout + recorded.stderr)

    def test_differing_flag_on_resume_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._bootstrap(root, "probe-differ", max_attempts=1)

            resumed = cli(root, "dispatch", "--run-id", "probe-differ", "--max-attempts", "3", "--journal", "./.orc")
            self.assertEqual(resumed.returncode, 2, resumed.stdout + resumed.stderr)
            error = json.loads(resumed.stdout or resumed.stderr)
            self.assertEqual(error["error"], "ERR-VALIDATION")
            self.assertEqual(error["details"]["journaled_max_attempts"], 1)
            self.assertEqual(error["details"]["requested_max_attempts"], 3)
            self.assertIn("fixed at creation", error["message"])

    def test_equal_flag_on_resume_is_a_no_op(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._bootstrap(root, "probe-equal", max_attempts=2)

            # max_attempts=2, one failed attempt recorded: an equal
            # --max-attempts on resume is not refused -- ordinary retry
            # proceeds (attempt 2 dispatched, still pending).
            resumed = cli(root, "dispatch", "--run-id", "probe-equal", "--max-attempts", "2", "--journal", "./.orc")
            self.assertEqual(resumed.returncode, 3, resumed.stdout + resumed.stderr)
            self.assertNotIn("ERR-VALIDATION", resumed.stdout + resumed.stderr)

    def test_bare_resume_with_no_explicit_opinion_is_never_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._bootstrap(root, "probe-bare", max_attempts=1)

            resumed = cli(root, "dispatch", "--run-id", "probe-bare", "--journal", "./.orc")
            self.assertEqual(resumed.returncode, 1, resumed.stdout + resumed.stderr)
            self.assertIn("state=BLOCKED", resumed.stdout)


class Scn240PersistedConfigCarriesBudgetTest(unittest.TestCase):
    """(c) R3: a flag-created run's persisted config.json carries the
    budget -- the #240 trigger, closed as belt."""

    def test_flag_supplied_max_attempts_is_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "cfg.json").write_text(json.dumps({}), encoding="utf-8")
            result = cli(
                root, "dispatch", "budget probe", "--config", "cfg.json",
                "--run-id", "probe-persist", "--max-attempts", "1", "--journal", "./.orc",
            )
            self.assertEqual(result.returncode, 3, result.stdout + result.stderr)

            persisted = json.loads((root / ".orc" / "probe-persist" / "config.json").read_text())
            self.assertEqual(persisted["max_attempts"], 1)


class Scn240ReplayAssertionFiresTest(unittest.TestCase):
    """(d) R4: a divergent record injected outside the ordinary decision
    path makes the post-decision replay assertion fail loudly rather than
    silently wedge."""

    DRID = "scn240-assert"
    WORK_ID = "work-1"

    def test_injected_divergent_record_raises_instead_of_wedging(self) -> None:
        orchestrator, journal, _work_graph = build_run(
            delivery_run_id=self.DRID,
            attempts_by_work={self.WORK_ID: [{"outcome": "failed"}]},
            max_attempts=1,
        )
        projection = orchestrator.run()
        wp = projection.works[self.WORK_ID]
        self.assertEqual(wp.state, STATE_BLOCKED)
        self.assertTrue(wp.blocked_confirmed)

        # Simulate a divergent record path: some other bug appends a
        # second FACT-EXEC-STARTED directly to the journal, bypassing the
        # ordinary decide()/apply_fact() legality gate entirely -- exactly
        # the shape of record R4 exists to catch.
        journal.append_fact(
            make_fact(
                FACT_EXEC_STARTED,
                delivery_run_id=self.DRID,
                work_id=self.WORK_ID,
                execution_id="exec-injected-illegal",
            )
        )

        with self.assertRaises(CoreError) as ctx:
            orchestrator._assert_replay_consistent()
        canonical = ctx.exception.to_canonical()
        self.assertEqual(canonical["error"], "ERR-CONFLICT")
        self.assertIn("post-decision replay assertion failed", canonical["message"])
        self.assertIn("offending_record", canonical["details"])


class Scn240ReplayDeterminismTest(unittest.TestCase):
    """(e) For the fixed flow, the read-side (`load_projection`) and
    write-side (`Orchestrator.projection`) folds of one journal agree
    exactly -- CONF-JOURNAL-003 across verbs, not just within one."""

    DRID = "scn240-determinism"
    WORK_ID = "work-1"

    def test_read_and_write_side_projections_agree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp) / ".orc"
            journal = JSONLJournal(journal_dir)
            orchestrator, journal, _work_graph = build_run(
                delivery_run_id=self.DRID,
                attempts_by_work={self.WORK_ID: [{"outcome": "failed"}]},
                max_attempts=1,
                journal=journal,
            )
            write_side = orchestrator.run()
            wp = write_side.works[self.WORK_ID]
            self.assertEqual(wp.state, STATE_BLOCKED)

            # A fresh Orchestrator over the same journal (simulating a
            # brand-new process resuming with no memory of RunConfig)
            # reconstructs identical state via the write-side fold.
            fresh_orchestrator = Orchestrator(
                delivery_run_id=self.DRID,
                journal=journal,
                work_graph=_work_graph,
                execution=orchestrator.execution,
                candidate=orchestrator.candidate,
                assurance=orchestrator.assurance,
                # A deliberately WRONG config default -- the whole point of
                # R1 is that this must be ignored once history exists.
                config=RunConfig(max_attempts=3),
            )
            fresh_write_side = fresh_orchestrator.projection()

            # The independent read-side path agrees too.
            read_side = journal.load_projection(delivery_run_id=self.DRID)

            self.assertEqual(write_side.to_dict(), fresh_write_side.to_dict())
            self.assertEqual(write_side.to_dict(), read_side.to_dict())


if __name__ == "__main__":
    unittest.main()
