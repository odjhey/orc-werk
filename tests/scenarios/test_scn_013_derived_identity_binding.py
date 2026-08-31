"""SCN-013: scripted assurance derived-identity binding (CONF-ASSURE-005)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
CANDIDATE = {"head_sha": "current", "pr": 180}


class DerivedIdentityBindingScenarioTest(unittest.TestCase):
    def _dispatch(self, root: Path, config: dict, run_id: str) -> subprocess.CompletedProcess[str]:
        config_path = root / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        return subprocess.run(
            [sys.executable, "-m", "orc_werk.cli", "dispatch", "SCN-013", "--config",
             str(config_path), "--run-id", run_id, "--journal", str(root / ".orc")],
            cwd=root, env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"},
            capture_output=True, text=True, timeout=30,
        )

    @staticmethod
    def _config(assurance: dict | None) -> dict:
        attempt = {"outcome": "completed", "candidate": CANDIDATE}
        if assurance is not None:
            attempt["assurance"] = assurance
        return {"attempts": {"work-1": [attempt]}}

    def test_mismatch_is_pure_pending_redispatchable_and_replays(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "scn013-mismatch"
            pending = self._dispatch(root, self._config(None), run_id)
            self.assertEqual(pending.returncode, 3, msg=pending.stdout + pending.stderr)
            journal = root / ".orc" / run_id / "journal.jsonl"
            before = journal.read_bytes()

            mismatch = self._dispatch(root, self._config({
                "verdict": "accepted", "derived_identity": {"head_sha": "stale"}
            }), run_id)
            self.assertEqual(mismatch.returncode, 2)
            self.assertEqual(json.loads(mismatch.stderr)["error"], "ERR-CONFLICT")
            self.assertEqual(journal.read_bytes(), before)

            replay = self._dispatch(root, self._config(None), run_id)
            self.assertEqual(replay.returncode, 3, msg=replay.stdout + replay.stderr)
            self.assertIn("awaiting=assurance-verdict", replay.stdout)
            self.assertEqual(journal.read_bytes(), before)

            matched = self._dispatch(root, self._config({
                "verdict": "accepted", "derived_identity": {"head_sha": "current"}
            }), run_id)
            self.assertEqual(matched.returncode, 0, msg=matched.stdout + matched.stderr)

    def test_match_binds_without_derived_identity_in_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self._dispatch(root, self._config({
                "verdict": "accepted", "derived_identity": {"head_sha": "current"}
            }), "scn013-match")
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            journal = root / ".orc" / "scn013-match" / "journal.jsonl"
            records = [json.loads(line) for line in journal.read_text().splitlines()]
            settled = [r for r in records if r["id"] == "FACT-ASSURE-SETTLED"]
            self.assertEqual(len(settled), 1)
            self.assertNotIn("derived_identity", settled[0]["data"])
            self.assertNotIn("derived_identity", settled[0].get("extensions", {}))

    def test_absent_field_preserves_existing_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._dispatch(Path(tmp), self._config({"verdict": "accepted"}), "scn013-absent")
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertNotIn("derived_identity corroborated", result.stdout)


if __name__ == "__main__":
    unittest.main()
