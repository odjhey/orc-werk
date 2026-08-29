"""`TASK-M2-001` CLI wiring: `orc dispatch`'s `assurance` config selecting
`NoMistakesAssurance` (a real port) in place of the operator-recorded
`ScriptedAssurance` (`src/orc_werk/cli/config.py`'s "Real-port selection"
section), mirroring `test_cli_acp_wiring.py`'s pattern for the acp
execution wiring.

Two groups of coverage:

- `NoMistakesConfigValidationTest` -- `load_config`'s strict validation of
  the new `assurance` block and its adapter-aware `attempts` narrowing
  (unit-level, in-process).
- `NoMistakesWiringSmokeTest` -- a full `dispatch -> pending
  (execution-outcome) -> pending (assurance-verdict, automatic) ->
  accepted` cycle driven through the REAL `orc` CLI entrypoint
  (subprocess), against a fake `no-mistakes` on `PATH` (`tests/
  conformance/support_no_mistakes_stub.py`) and a real temporary git
  repository (`GitDiffCandidate`). No live `no-mistakes`/daemon/agent
  dependency anywhere in this suite. Execution stays `scripted` here
  (this task's scope is the assurance seat, not a second real-execution
  proof -- `TASK-M1-005` already covers that combination); candidate is
  real (`git`) since `assurance.adapter == "no-mistakes"` requires it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from orc_werk.cli.config import load_config
from orc_werk.core.errors import CoreError
from tests.conformance.support_no_mistakes_stub import NoMistakesStubWorld

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


def _git(args: list[str], *, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(["init", "-q"], cwd=path)
    _git(["config", "user.email", "no-mistakes-wiring@example.invalid"], cwd=path)
    _git(["config", "user.name", "No-Mistakes Wiring Fixture"], cwd=path)
    (path / "a.txt").write_text("x")
    _git(["add", "."], cwd=path)
    _git(["commit", "-q", "-m", "init"], cwd=path)


class NoMistakesConfigValidationTest(unittest.TestCase):
    def _write(self, tmp: Path, data: dict, *, name: str = "cfg.json") -> str:
        path = tmp / name
        path.write_text(json.dumps(data))
        return str(path)

    def test_no_mistakes_requires_repo_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(Path(tmp), {"assurance": {"adapter": "no-mistakes"}})
            with self.assertRaises(CoreError) as ctx:
                load_config(path)
            self.assertEqual(ctx.exception.error["error"], "ERR-VALIDATION")

    def test_no_mistakes_requires_git_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                Path(tmp), {"assurance": {"adapter": "no-mistakes", "repo_path": "/tmp"}}
            )
            with self.assertRaises(CoreError) as ctx:
                load_config(path)
            self.assertEqual(ctx.exception.error["error"], "ERR-VALIDATION")

    def test_no_mistakes_plus_git_candidate_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                Path(tmp),
                {
                    "assurance": {"adapter": "no-mistakes", "repo_path": "/tmp"},
                    "candidate": {"adapter": "git", "repo_path": "/tmp"},
                },
            )
            data = load_config(path)
            self.assertEqual(data["assurance"]["adapter"], "no-mistakes")

    def test_unknown_assurance_key_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                Path(tmp),
                {"assurance": {"adapter": "no-mistakes", "repo_path": "/tmp", "bogus": 1}},
            )
            with self.assertRaises(CoreError):
                load_config(path)

    def test_no_mistakes_attempts_reject_assurance_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                Path(tmp),
                {
                    "assurance": {"adapter": "no-mistakes", "repo_path": "/tmp"},
                    "candidate": {"adapter": "git", "repo_path": "/tmp"},
                    "attempts": {"work-1": [{"outcome": "completed", "assurance": {"verdict": "accepted"}}]},
                },
            )
            with self.assertRaises(CoreError):
                load_config(path)

    def test_no_mistakes_attempts_allow_outcome_since_execution_stays_scripted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                Path(tmp),
                {
                    "assurance": {"adapter": "no-mistakes", "repo_path": "/tmp"},
                    "candidate": {"adapter": "git", "repo_path": "/tmp"},
                    "attempts": {"work-1": [{"outcome": "completed"}]},
                },
            )
            data = load_config(path)  # does not raise
            self.assertEqual(data["attempts"]["work-1"][0], {"outcome": "completed"})


class NoMistakesWiringSmokeTest(unittest.TestCase):
    """Full dispatch -> pending -> pending (auto) -> accepted cycle through
    the REAL `cmd_dispatch` path (subprocess `orc` invocation), against the
    stub-`no-mistakes` harness and a real git repo. No operator verdict
    step -- that is exactly the automation this card delivers."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.repo = self.root / "repo"
        _init_repo(self.repo)

        self.world = NoMistakesStubWorld(self.root / "nm_world")
        self.journal_dir = self.root / ".orc"
        self.run_id = "no-mistakes-wiring-smoke"
        self.config_path = self.root / "cfg.json"

    def _env(self) -> dict:
        env = dict(self.world.env())
        env["PYTHONPATH"] = str(SRC)
        env["PATH"] = f"{self.world.bin_dir}{os.pathsep}/usr/bin:/bin"
        return env

    def _run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "orc_werk.cli", *args],
            cwd=self.root,
            env=self._env(),
            capture_output=True,
            text=True,
            timeout=30,
        )

    def _write_config(self) -> None:
        # NoMistakesAssurance invokes the fake binary with cwd=repo_path,
        # not this test process's cwd -- the stub's own repo_path
        # (world.repo_path) is irrelevant here, this adapter always uses
        # ITS OWN configured repo_path as the subprocess cwd.
        data = {
            "candidate": {"adapter": "git", "repo_path": str(self.repo)},
            "assurance": {"adapter": "no-mistakes", "repo_path": str(self.repo)},
            "attempts": {"work-1": [{"outcome": "completed"}]},
        }
        self.config_path.write_text(json.dumps(data))

    def test_full_dispatch_pending_auto_settled_accepted_cycle(self) -> None:
        self._write_config()

        # 1) First dispatch: scripted execution settles immediately
        # (outcome: completed, per the config), a REAL git candidate is
        # identified, and assurance is auto-requested (no operator
        # action) -- the stub `axi run` spawn registers a new running
        # pipeline run with no gate/outcome yet, so the run rests pending
        # at exit 3, awaiting the assurance verdict.
        result1 = self._run_cli(
            "dispatch", "add a small fix",
            "--config", str(self.config_path), "--journal", str(self.journal_dir),
            "--run-id", self.run_id,
        )
        self.assertEqual(result1.returncode, 3, result1.stdout + result1.stderr)
        self.assertIn("awaiting=assurance-verdict", result1.stdout)
        self.assertIn("candidate_fingerprint=fp-", result1.stdout)

        active_run_id = self.world.active_run_id()
        self.assertIsNotNone(active_run_id, "the stub should have registered a new pipeline run")

        # 2) Re-dispatch while the pipeline is still running: no new `axi
        # run` spawn (cross-process idempotency, best-effort -- mapping
        # doc "Limitations"), still pending.
        result2 = self._run_cli(
            "dispatch", "add a small fix",
            "--config", str(self.config_path), "--journal", str(self.journal_dir),
            "--run-id", self.run_id,
        )
        self.assertEqual(result2.returncode, 3, result2.stdout + result2.stderr)
        self.assertEqual(self.world.run_count(), 1, "must not spawn a second pipeline run while one is active")

        # 3) The (real) no-mistakes pipeline settles passed -- entirely
        # outside this adapter/CLI's control, exactly as a real daemon
        # would settle it in the background.
        self.world.set_outcome(active_run_id, "passed")

        result3 = self._run_cli(
            "dispatch", "add a small fix",
            "--config", str(self.config_path), "--journal", str(self.journal_dir),
            "--run-id", self.run_id,
        )
        self.assertEqual(result3.returncode, 0, result3.stdout + result3.stderr)
        self.assertIn("state=ACCEPTED", result3.stdout)

    def test_bound_then_divergent_run_never_settles_and_status_surfaces_it(self) -> None:
        """`TASK-M3B-002` (issue #92 scope extension), the xatu incident
        shape reproduced end-to-end: a run this candidate's assurance is
        genuinely bound to reaches a terminal, otherwise-settleable
        outcome -- but its observed head has since diverged from the
        candidate. inspect()'s identity guard must refuse to settle it
        (the Work stays pending, exit 3, forever -- never a silently wrong
        ACCEPTED), and `orc status` (pure journal read, no live port call)
        must still name the bound assurance + candidate head + the
        abandon-flags recovery path."""
        self._write_config()

        result1 = self._run_cli(
            "dispatch", "add a small fix",
            "--config", str(self.config_path), "--journal", str(self.journal_dir),
            "--run-id", self.run_id,
        )
        self.assertEqual(result1.returncode, 3, result1.stdout + result1.stderr)
        active_run_id = self.world.active_run_id()
        self.assertIsNotNone(active_run_id)

        # The bound run's observed head diverges from the real candidate
        # (a foreign/adopted pipeline reaching its own terminal outcome),
        # then reaches an otherwise-settleable terminal outcome.
        self.world.set_head_shape(
            active_run_id, head="f" * 40, emit_run_head=True, emit_branch_sync=True
        )
        self.world.set_outcome(active_run_id, "passed")

        result2 = self._run_cli(
            "dispatch", "add a small fix",
            "--config", str(self.config_path), "--journal", str(self.journal_dir),
            "--run-id", self.run_id,
        )
        # Never silently ACCEPTED on a foreign outcome (P-004/INV-007..
        # INV-010) -- stays pending, awaiting the operator's out-of-band
        # judgment (TASK-M3B-001's abandon record is the only recovery).
        self.assertEqual(result2.returncode, 3, result2.stdout + result2.stderr)
        self.assertIn("awaiting=assurance-verdict", result2.stdout)
        self.assertNotIn("state=ACCEPTED", result2.stdout)

        status = self._run_cli("status", self.run_id, "--journal", str(self.journal_dir))
        self.assertEqual(status.returncode, 3, status.stdout + status.stderr)
        self.assertIn("bound assurance is no-mistakes:", status.stdout)
        self.assertIn("--abandon-work work-1", status.stdout)
        self.assertIn("--abandon-reason", status.stdout)


if __name__ == "__main__":
    unittest.main()
