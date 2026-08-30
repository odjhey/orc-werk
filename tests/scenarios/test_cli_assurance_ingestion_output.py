"""CLI assurance-settlement ingestion and seat-ownership output (#147/#150)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


class AssuranceIngestionOutputTest(unittest.TestCase):
    def _dispatch(self, root: Path, config: dict, *, run_id: str) -> subprocess.CompletedProcess:
        config_path = root / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "orc_werk.cli",
                "dispatch",
                "assurance output test",
                "--config",
                str(config_path),
                "--run-id",
                run_id,
            ],
            cwd=root,
            env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_accepted_settlement_echoes_journaled_verdict_extensions_and_seq(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._dispatch(
                Path(tmp),
                {
                    "attempts": {
                        "work-1": [
                            {
                                "outcome": "completed",
                                "candidate": {"label": "A"},
                                "assurance": {
                                    "verdict": "accepted",
                                    "extensions": {"review-findings/v1": {"findings": []}},
                                },
                            }
                        ]
                    }
                },
                run_id="accepted-echo",
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertRegex(
                result.stdout,
                r"assurance recorded: work 'work-1' verdict=accepted "
                r"extensions=\[review-findings/v1\] \(seq \d+\)",
            )

    def test_misnested_extension_is_absent_from_assurance_echo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._dispatch(
                Path(tmp),
                {
                    "attempts": {
                        "work-1": [
                            {
                                "outcome": "completed",
                                "candidate": {"label": "A"},
                                # A plausible malformed nesting: this lands on
                                # FACT-EXEC-SETTLED, not FACT-ASSURE-SETTLED.
                                "extensions": {"review-findings/v1": {"findings": []}},
                                "assurance": {"verdict": "accepted"},
                            }
                        ]
                    }
                },
                run_id="misnested-extension",
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            echo = next(line for line in result.stdout.splitlines() if line.startswith("assurance recorded:"))
            self.assertIn("verdict=accepted extensions=[]", echo)
            self.assertNotIn("review-findings/v1", echo)

    def test_rejected_retry_echoes_ingestion_and_execution_seat_clarifier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._dispatch(
                Path(tmp),
                {
                    "max_attempts": 2,
                    "attempts": {
                        "work-1": [
                            {
                                "outcome": "completed",
                                "candidate": {"label": "A"},
                                "assurance": {"verdict": "rejected"},
                            }
                        ]
                    },
                },
                run_id="rejected-retry",
            )
            self.assertEqual(result.returncode, 3, msg=result.stdout + result.stderr)
            self.assertRegex(result.stdout, r"assurance recorded: .*verdict=rejected.*\(seq \d+\)")
            self.assertIn(
                "assurance verdict recorded (rejected); attempt 2 opened -- "
                "the next action belongs to the EXECUTION seat, not the verifier.",
                result.stdout,
            )
            self.assertIn("awaiting=execution-outcome", result.stdout)

    def test_execution_only_settlement_emits_no_assurance_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._dispatch(
                Path(tmp),
                {"attempts": {"work-1": [{"outcome": "completed", "candidate": {"label": "A"}}]}},
                run_id="execution-only",
            )
            self.assertEqual(result.returncode, 3, msg=result.stdout + result.stderr)
            self.assertNotIn("assurance recorded:", result.stdout)
            self.assertNotIn("assurance verdict recorded", result.stdout)


if __name__ == "__main__":
    unittest.main()
