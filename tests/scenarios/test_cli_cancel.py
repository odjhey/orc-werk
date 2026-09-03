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

    def test_cancel_real_candidate_run_does_not_construct_provider_ports(self) -> None:
        # `orc cancel` is a journal-only operation and must never construct
        # a real port -- even when the repo-default profile names a real
        # candidate.adapter (the surviving A5 git-candidate half of the
        # removed acp+git real-port combo, ADR-0005) -- so this never
        # attempts to construct a real GitDiffCandidate against `root`
        # (not an actual git repository).
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "cfg.json"
            config_path.write_text(
                json.dumps(
                    {
                        "run_id": "cancel-git",
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
                        "candidate": {"adapter": "git", "repo_path": str(root)},
                    }
                ),
                encoding="utf-8",
            )

            result = _run_cli(
                root, "cancel", "cancel-git", "--work", "work-1", "--reason", "operator closure"
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("state=CANCELLED", result.stdout)

    def test_cancel_tolerates_persisted_config_naming_removed_adapter(self) -> None:
        """Issue #236 repro (field evidence: 23 stranded adopter runs after
        an ADR-0005 adapter removal). Cancel is journal-only (`SCN-011`,
        `STATE-DELIVERY` item 10) -- a persisted config that still names a
        since-removed adapter (`acp`, ADR-0005) must not block it, even
        though `orc dispatch`'s own refusal of that exact config is
        unchanged (asserted below, requirement (d))."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "cfg.json"
            config_path.write_text(
                json.dumps({"run_id": "legacy-cancel", "attempts": {"work-1": []}}),
                encoding="utf-8",
            )
            initial = _run_cli(root, "dispatch", "legacy work", "--config", str(config_path))
            self.assertEqual(initial.returncode, 3, msg=initial.stdout + initial.stderr)

            # Simulate the field scenario: an install upgrade removes the
            # `acp` adapter (ADR-0005) out from under an already-persisted
            # config that still names it.
            persisted_path = root / ".orc" / "legacy-cancel" / "config.json"
            persisted = json.loads(persisted_path.read_text())
            persisted["execution"] = {"adapter": "acp", "agent": "claude", "cwd": "/tmp"}
            persisted_path.write_text(json.dumps(persisted), encoding="utf-8")

            # (d) dispatch's own refusal of the same invalid config is
            # UNCHANGED -- only the journal-only escape hatches open.
            refused = _run_cli(root, "dispatch", "--run-id", "legacy-cancel")
            self.assertEqual(refused.returncode, 2)
            refused_error = json.loads(refused.stderr)
            self.assertEqual(refused_error["error"], "ERR-VALIDATION")
            self.assertIn("execution", refused_error["message"])

            # (a) cancel tolerates it: journal-only, acts on the journal
            # alone, and names the tolerated error on stderr rather than
            # failing silently.
            cancelled = _run_cli(
                root, "cancel", "legacy-cancel", "--work", "work-1",
                "--reason", "adopter upgrade recovery (#236)",
            )
            self.assertEqual(cancelled.returncode, 0, msg=cancelled.stdout + cancelled.stderr)
            self.assertIn("state=CANCELLED", cancelled.stdout)
            self.assertIn("persisted config invalid", cancelled.stderr)
            self.assertIn("ERR-VALIDATION", cancelled.stderr)
            self.assertIn("journal-only", cancelled.stderr)

            # Journal-clean read-back: replay reconstructs the same
            # confirmed terminal projection (SCN-011 item 7).
            projection = JSONLJournal(root / ".orc").load_projection(delivery_run_id="legacy-cancel")
            self.assertEqual(projection.works["work-1"].state, "CANCELLED")

    def test_cancel_missing_run_is_still_not_found(self) -> None:
        """(c): the escape hatch is scoped to an invalid *persisted config*
        for an EXISTING run -- a genuinely missing run is still refused."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = _run_cli(root, "cancel", "no-such-run", "--work", "work-1", "--reason", "x")
            self.assertEqual(missing.returncode, 2)
            self.assertEqual(json.loads(missing.stderr)["error"], "ERR-NOT-FOUND")


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
