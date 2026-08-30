"""Read-only verdict projection and issue #149 refs discoverability."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


def run_cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    return subprocess.run(
        [sys.executable, "-m", "orc_werk.cli", *args],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


class VerdictProjectionTest(unittest.TestCase):
    def test_latest_verdicts_findings_empty_state_and_no_journal_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {
                "max_attempts": 2,
                "plan": {"works": [
                    {"work_id": "accepted-work", "deps": []},
                    {"work_id": "rejected-work", "deps": []},
                    {"work_id": "pending-work", "deps": []},
                ]},
                "attempts": {
                    "accepted-work": [{
                        "outcome": "completed",
                        "candidate": {"head_sha": "aaa", "branch": "feature/accepted"},
                        "assurance": {
                            "verdict": "accepted",
                            "evidence_refs": ["accepted-evidence"],
                            "extensions": {"review-findings/v1": {"findings": [
                                {"id": "A-1", "severity": "note", "summary": "accept summary"}
                            ]}},
                        },
                    }],
                    "rejected-work": [{
                        "outcome": "completed",
                        "candidate": {"head_sha": "bbb"},
                        "assurance": {
                            "verdict": "rejected",
                            "evidence_refs": ["rejected-evidence"],
                            "extensions": {"review-findings/v1": {"findings": [
                                {"id": "R-1", "severity": "high", "summary": "reject summary"}
                            ]}},
                        },
                    }],
                    "pending-work": [{"outcome": "completed", "candidate": {"head_sha": "ccc"}}],
                },
            }
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch = run_cli(root, "dispatch", "verdict fixture", "--config", str(config_path), "--run-id", "verdict-run")
            self.assertEqual(dispatch.returncode, 3, msg=dispatch.stdout + dispatch.stderr)

            journal = root / ".orc" / "verdict-run" / "journal.jsonl"
            before = journal.read_bytes()
            result = run_cli(root, "verdict", "verdict-run")
            after = journal.read_bytes()

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertEqual(before, after, "orc verdict must not append or rewrite the journal")
            self.assertRegex(result.stdout, r"accepted-work: verdict=accepted candidate_fingerprint=(?!-)\S+")
            self.assertIn("review-findings/v1", result.stdout)
            self.assertIn("A-1: accept summary", result.stdout)
            self.assertRegex(result.stdout, r"rejected-work: verdict=rejected candidate_fingerprint=(?!-)\S+")
            self.assertIn("R-1: reject summary", result.stdout)
            self.assertIn("work pending-work: (no verdict yet)", result.stdout)

            refs = run_cli(root, "refs", "verdict-run")
            self.assertEqual(refs.returncode, 0, msg=refs.stdout + refs.stderr)
            self.assertRegex(refs.stdout, r"accepted-evidence verdict=accepted")
            self.assertRegex(refs.stdout, r"rejected-evidence verdict=rejected")
            self.assertIn('"branch":"feature/accepted"', refs.stdout)

    def test_verdict_is_registered_in_top_level_help(self) -> None:
        result = run_cli(Path.cwd(), "--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("verdict", result.stdout)


if __name__ == "__main__":
    unittest.main()
