"""Issue #254 -- `orc --state active` must not surface a terminal BLOCKED
run forever. BLOCKED is a terminal state (`STATE-DELIVERY`'s canonical
terminal set is ACCEPTED/BLOCKED/CANCELLED), exactly like the already-
excluded CANCELLED (`tests/scenarios/test_cli_cancel.py`'s
`CancelledReportingTest`). A run whose only Work has exhausted its retry
budget and settled into BLOCKED needs no further operator action, so it
must drop out of the active view precisely as a CANCELLED run already
does.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from orc_werk.adapters.jsonl.journal import JSONLJournal
from orc_werk.cli.report import _index_state_rollup
from tests.scenarios.support import build_run

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


def _run_cli(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "orc_werk.cli", *args],
        cwd=root,
        env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin", "USER": "test-operator"},
        capture_output=True,
        text=True,
        timeout=30,
    )


def _blocked_run(root: Path, run_id: str, *, max_attempts: int = 3):
    orchestrator, _journal, _graph = build_run(
        delivery_run_id=run_id,
        attempts_by_work={"work-1": [{"outcome": "failed"} for _ in range(max_attempts)]},
        max_attempts=max_attempts,
        journal=JSONLJournal(root / ".orc"),
    )
    orchestrator.run()
    return orchestrator


def _ready_run(root: Path, run_id: str):
    orchestrator, _journal, _graph = build_run(
        delivery_run_id=run_id,
        attempts_by_work={"work-1": []},
        journal=JSONLJournal(root / ".orc"),
    )
    return orchestrator


class BlockedRunExcludedFromActiveIndexTest(unittest.TestCase):
    def test_retry_budget_exhausted_blocked_run_excluded_from_active_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _blocked_run(root, "blocked-run")
            _ready_run(root, "ready-control")

            active = _run_cli(root, "--state", "active", "--limit", "0")
            self.assertEqual(active.returncode, 0, msg=active.stdout + active.stderr)
            self.assertIn("ready-control:", active.stdout)
            self.assertNotIn("blocked-run:", active.stdout)

            unfiltered = _run_cli(root, "--limit", "0")
            self.assertIn("blocked-run:", unfiltered.stdout)

            projection = JSONLJournal(root / ".orc").load_projection(delivery_run_id="blocked-run")
            rollup, is_active = _index_state_rollup(projection)
            self.assertEqual(rollup, "BLOCKED:1 flags=blocked")
            self.assertFalse(is_active)


if __name__ == "__main__":
    unittest.main()
