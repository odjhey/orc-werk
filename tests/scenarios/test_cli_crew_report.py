"""CLI-level regression tests for `orc crew-report append|list`
(`TASK-M1-007`), specifically the attempt-2 review finding: no filesystem
side effects before validation, mirroring the #17/#18 invariants PR #32
established for the main commands --

- `crew-report list` against a run with no report log is a pure query: it
  exits cleanly and creates no journal directory;
- `crew-report append` with an invalid payload exits `2` with a canonical
  error AND leaves no stray directory behind;
- a valid `crew-report append` still works (creates the directory on the
  first actual write) and `list` reads it back in append order.

Subprocess-driven against a temp cwd where `./.orc` does not exist,
following `tests/scenarios/test_cli_dogfood_fixes.py`'s `_run_cli`
pattern.
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


class CrewReportCliNoSideEffectsTest(unittest.TestCase):
    def test_list_on_fresh_dir_creates_no_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(tmp_dir, "crew-report", "list", "some-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertFalse((tmp_dir / ".orc").exists())

    def test_invalid_append_exits_2_and_creates_no_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(
                tmp_dir,
                "crew-report",
                "append",
                "some-run",
                "--execution-id",
                "e1",
                "--payload",
                '{"turn": 1, "claimed_verdict": "bogus"}',
            )
            self.assertEqual(result.returncode, 2, result.stdout)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-VALIDATION")
            self.assertFalse((tmp_dir / ".orc").exists())

    def test_malformed_json_payload_exits_2_and_creates_no_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(
                tmp_dir,
                "crew-report",
                "append",
                "some-run",
                "--execution-id",
                "e1",
                "--payload",
                "not json at all",
            )
            self.assertEqual(result.returncode, 2, result.stdout)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-VALIDATION")
            self.assertFalse((tmp_dir / ".orc").exists())

    def test_valid_append_still_works_then_list_reads_back_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            for turn, verdict in ((1, "waiting"), (2, "done")):
                result = _run_cli(
                    tmp_dir,
                    "crew-report",
                    "append",
                    "some-run",
                    "--execution-id",
                    "e1",
                    "--payload",
                    json.dumps({"turn": turn, "claimed_verdict": verdict}),
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(layout.reports_path(tmp_dir / ".orc", "some-run").exists())
            # The journal file itself is never created by this command.
            self.assertFalse(layout.journal_path(tmp_dir / ".orc", "some-run").exists())

            listed = _run_cli(tmp_dir, "crew-report", "list", "some-run")
            self.assertEqual(listed.returncode, 0, listed.stderr)
            lines = listed.stdout.splitlines()
            self.assertEqual(len(lines), 2)
            self.assertIn('"turn":1', lines[0])
            self.assertIn('"turn":2', lines[1])


if __name__ == "__main__":
    unittest.main()
