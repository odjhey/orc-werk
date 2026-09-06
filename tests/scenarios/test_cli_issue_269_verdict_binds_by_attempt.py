"""Issue #269: a config-recorded verdict must bind to the candidate of the
SAME attempt number, not to the Nth candidate observed.

Pre-fix, `orc_werk.cli.config.build_real_assurance_script` indexed a
positional list of `FACT-CANDIDATE-OBSERVED` fingerprints by attempt index.
When attempt 1 settled `failed` before any candidate existed (the seat died),
the run's first observed candidate belonged to attempt 2, sat at position 0,
and the verdict recorded on `attempts.work-1[1]` (index 1) was skipped on
every dispatch -- the run rested ASSURING forever although its config
carried the verdict, and `orc record` refused both `--outcome` and
`--verdict` with ERR-CONFLICT.

The journal below is driven by the CLI itself (dispatch / record / dispatch
/ record --verdict / dispatch) against a real git candidate, exactly the
reporter's sequence."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from orc_werk.adapters.jsonl import layout

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


def cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "orc_werk.cli", *args], cwd=root,
        env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True, timeout=30,
    )


def _init_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for args in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "a@b.com"],
        ["git", "config", "user.name", "a"],
    ):
        subprocess.run(args, cwd=path, check=True)
    (path / "f.txt").write_text("hi")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)


class Issue269FailedFirstAttemptTest(unittest.TestCase):
    def test_verdict_on_attempt_two_settles_after_a_candidateless_failed_attempt_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            _init_git_repo(repo)
            run_id = "issue269"
            journal_dir = root / ".orc"
            journal_dir.mkdir()
            config_path = layout.config_path(journal_dir, run_id)
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps({
                "candidate": {"adapter": "git", "repo_path": str(repo)},
            }))
            journal = ("--journal", str(journal_dir))
            cfg = ("--config", str(config_path))

            first = cli(root, "dispatch", "issue 269", *cfg, *journal, "--run-id", run_id)
            self.assertIn("state=EXECUTING", first.stdout, first.stdout + first.stderr)

            # attempt 1 dies before producing anything (no candidate)
            failed = cli(root, "record", run_id, "--work", "work-1", "--outcome", "failed", *journal)
            self.assertEqual(failed.returncode, 0, failed.stdout + failed.stderr)
            second = cli(root, "dispatch", "issue 269", *cfg, *journal, "--run-id", run_id)
            self.assertIn("attempt=2", second.stdout, second.stdout + second.stderr)

            # attempt 2 ships; the FIRST observed candidate of the run belongs to attempt 2
            done = cli(root, "record", run_id, "--work", "work-1", "--outcome", "completed", *journal)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            assuring = cli(root, "dispatch", "issue 269", *cfg, *journal, "--run-id", run_id)
            self.assertIn("state=ASSURING", assuring.stdout, assuring.stdout + assuring.stderr)
            self.assertIn("attempt=2", assuring.stdout)

            verdict = cli(
                root, "record", run_id, "--work", "work-1", "--verdict", "accepted",
                "--evidence-ref", "https://example/pr/1", *journal,
            )
            self.assertEqual(verdict.returncode, 0, verdict.stdout + verdict.stderr)
            attempts = json.loads(config_path.read_text())["attempts"]["work-1"]
            self.assertEqual([a.get("outcome") for a in attempts], ["failed", "completed"])
            self.assertEqual(attempts[1]["assurance"]["verdict"], "accepted")

            settled = cli(root, "dispatch", "issue 269", *cfg, *journal, "--run-id", run_id)
            combined = settled.stdout + settled.stderr
            self.assertIn("state=ACCEPTED", settled.stdout, combined)
            self.assertNotIn("awaiting=assurance-verdict", settled.stdout, combined)


if __name__ == "__main__":
    unittest.main()
