"""Read-only pre-dispatch config validation and ingestion preview (#148)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


class CliValidateTest(unittest.TestCase):
    def _validate(self, root: Path, config: dict) -> subprocess.CompletedProcess[str]:
        path = root / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        return subprocess.run(
            [sys.executable, "-m", "orc_werk.cli", "validate", str(path)],
            cwd=root,
            env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_valid_config_previews_ingestion_without_creating_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self._validate(
                root,
                {
                    "plan": {"works": [{"work_id": "w", "deps": []}]},
                    "execution": {"adapter": "scripted"},
                    "candidate": {"adapter": "scripted"},
                    "assurance": {"adapter": "scripted"},
                    "attempts": {
                        "w": [{
                            "outcome": "completed",
                            "candidate": {"label": "A"},
                            "assurance": {
                                "verdict": "accepted",
                                "extensions": {"review-findings/v1": {"findings": []}},
                            },
                        }]
                    },
                },
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("PASS:", result.stdout)
            self.assertIn("plan works: w", result.stdout)
            self.assertIn("adapters: execution=scripted candidate=scripted assurance=scripted", result.stdout)
            self.assertIn("attempts.w[0]: keys=[assurance, candidate, outcome]", result.stdout)
            self.assertIn(
                "attempts.w[0].assurance: verdict=accepted, extensions=[review-findings/v1]",
                result.stdout,
            )
            self.assertFalse((root / ".orc").exists())

    def test_unknown_assurance_key_is_canonical_validation_error_and_pure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self._validate(root, {"attempts": {"w": [{"assurance": {"reveiw-findings": []}}]}})
            self.assertEqual(result.returncode, 2)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-VALIDATION")
            self.assertIn("reveiw-findings", error["message"])
            self.assertIn("<config>.attempts.w[0].assurance", error["message"])
            self.assertFalse((root / ".orc").exists())

    def test_unknown_top_level_key_is_canonical_validation_error_and_pure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self._validate(root, {"attemtps": {}})
            self.assertEqual(result.returncode, 2)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-VALIDATION")
            self.assertIn("attemtps", error["message"])
            self.assertFalse((root / ".orc").exists())


if __name__ == "__main__":
    unittest.main()
