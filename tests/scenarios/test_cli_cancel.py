"""SCN-011 cancellation coverage through the application-facing CLI."""

from __future__ import annotations

import json
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


def _ready_run(root: Path, run_id: str):
    orchestrator, _journal, _graph = build_run(
        delivery_run_id=run_id,
        attempts_by_work={"work-1": []},
        journal=JSONLJournal(root / ".orc"),
    )
    return orchestrator


class CancelCliTest(unittest.TestCase):
    def test_cancel_happy_path_and_canonical_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ready_run(root, "cancel-cli")

            missing_reason = _run_cli(root, "cancel", "cancel-cli", "--work", "work-1")
            self.assertEqual(missing_reason.returncode, 2)
            self.assertEqual(json.loads(missing_reason.stderr)["error"], "ERR-VALIDATION")

            unknown = _run_cli(
                root, "cancel", "cancel-cli", "--work", "missing", "--reason", "operator closure"
            )
            self.assertEqual(unknown.returncode, 2)
            self.assertEqual(json.loads(unknown.stderr)["error"], "ERR-NOT-FOUND")

            cancelled = _run_cli(
                root, "cancel", "cancel-cli", "--work", "work-1", "--reason", "operator closure"
            )
            self.assertEqual(cancelled.returncode, 0, msg=cancelled.stdout + cancelled.stderr)
            self.assertIn("state=CANCELLED", cancelled.stdout)

            repeated = _run_cli(
                root, "cancel", "cancel-cli", "--work", "work-1", "--reason", "again"
            )
            self.assertEqual(repeated.returncode, 2)
            self.assertEqual(json.loads(repeated.stderr)["error"], "ERR-CONFLICT")

    def test_cancel_briefed_acp_run_does_not_construct_provider_ports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "cfg.json"
            config_path.write_text(
                json.dumps(
                    {
                        "run_id": "cancel-acp",
                        "attempts": {"work-1": []},
                    }
                ),
                encoding="utf-8",
            )
            initial = _run_cli(root, "dispatch", "cancel me", "--config", str(config_path))
            self.assertEqual(initial.returncode, 3, msg=initial.stdout + initial.stderr)
            (root / ".orc" / "profile.json").write_text(
                json.dumps(
                    {
                        "execution": {"adapter": "acp", "cwd": str(root)},
                        "candidate": {"adapter": "git", "repo_path": str(root)},
                        "briefs": {"work-1": "provider-only brief"},
                    }
                ),
                encoding="utf-8",
            )

            result = _run_cli(
                root, "cancel", "cancel-acp", "--work", "work-1", "--reason", "operator closure"
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("state=CANCELLED", result.stdout)
            self.assertNotIn("note: work", result.stderr)


class CancelledReportingTest(unittest.TestCase):
    def test_cancelled_is_settled_and_excluded_from_active_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cancelled = _ready_run(root, "cancelled-run")
            _ready_run(root, "ready-control")
            cancelled.cancel_work(work_id="work-1", reason="done elsewhere", by="test-operator")

            active = _run_cli(root, "--state", "active", "--limit", "0")
            self.assertEqual(active.returncode, 0, msg=active.stdout + active.stderr)
            self.assertIn("ready-control:", active.stdout)
            self.assertNotIn("cancelled-run:", active.stdout)

            projection = JSONLJournal(root / ".orc").load_projection(delivery_run_id="cancelled-run")
            rollup, is_active = _index_state_rollup(projection)
            self.assertEqual(rollup, "CANCELLED:1")
            self.assertFalse(is_active)


if __name__ == "__main__":
    unittest.main()
