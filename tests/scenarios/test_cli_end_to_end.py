"""SCN-001 driven end-to-end through the `orc` CLI (subprocess, JSONL
journal, temp directory) -- the M-000 goal loop: intent -> attempt 1 ->
candidate A -> rejected -> retry -> candidate B -> accepted -> complete.
"""

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

CONFIG = {
    "run_id": "cli-e2e-run",
    "max_attempts": 3,
    "attempts": {
        "work-1": [
            {"outcome": "completed", "candidate": {"label": "A"}, "assurance": {"verdict": "rejected"}},
            {"outcome": "completed", "candidate": {"label": "B"}, "assurance": {"verdict": "accepted"}},
        ]
    },
}


class CliEndToEndTest(unittest.TestCase):
    def _run_cli(self, tmp_dir: Path, *args: str) -> subprocess.CompletedProcess:
        env = {"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"}
        return subprocess.run(
            [sys.executable, "-m", "orc_werk.cli", *args],
            cwd=tmp_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_dispatch_status_history_via_subprocess(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config_path = tmp_dir / "config.json"
            config_path.write_text(json.dumps(CONFIG), encoding="utf-8")

            dispatch = self._run_cli(
                tmp_dir, "dispatch", "ship the widget", "--config", str(config_path)
            )
            self.assertEqual(dispatch.returncode, 0, msg=dispatch.stderr)
            self.assertIn("run: cli-e2e-run", dispatch.stdout)
            self.assertIn("work work-1: state=ACCEPTED attempts=2", dispatch.stdout)

            journal_file = layout.journal_path(tmp_dir / ".orc", "cli-e2e-run")
            self.assertTrue(journal_file.exists())

            status = self._run_cli(tmp_dir, "status", "cli-e2e-run")
            self.assertEqual(status.returncode, 0, msg=status.stderr)
            self.assertIn("state=ACCEPTED", status.stdout)

            history = self._run_cli(tmp_dir, "history", "cli-e2e-run")
            self.assertEqual(history.returncode, 0, msg=history.stderr)
            self.assertIn("FACT-INTENT-SUBMITTED", history.stdout)
            self.assertIn("DEC-RETRY", history.stdout)
            self.assertIn("FACT-WORK-COMPLETED", history.stdout)
            # exactly one dispatch decision and one retry decision (M-000 loop).
            self.assertEqual(history.stdout.count("DEC-DISPATCH"), 1)
            self.assertEqual(history.stdout.count("DEC-RETRY"), 1)

    def test_blocked_run_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config_path = tmp_dir / "config.json"
            config_path.write_text(
                json.dumps({"run_id": "cli-blocked", "max_attempts": 1, "attempts": {"work-1": [{"outcome": "failed"}]}}),
                encoding="utf-8",
            )
            dispatch = self._run_cli(tmp_dir, "dispatch", "will fail", "--config", str(config_path))
            self.assertEqual(dispatch.returncode, 1, msg=dispatch.stderr)
            self.assertIn("state=BLOCKED", dispatch.stdout)


if __name__ == "__main__":
    unittest.main()
