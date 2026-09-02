"""TASK-M4A-001 repo-default dispatch profile scenarios."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from orc_werk.cli.config import deep_merge_config, load_repo_profile, validate_config

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(SRC))
    return subprocess.run(
        [sys.executable, "-m", "orc_werk.cli", *args], cwd=cwd, env=env,
        capture_output=True, text=True, timeout=30,
    )


class RepoProfileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_bare_dispatch_uses_profile_defaults(self):
        profile = self.root / ".orc" / "profile.json"
        profile.parent.mkdir()
        profile.write_text(json.dumps({"attempts": {"work-1": [{
            "outcome": "completed", "candidate": {"from": "profile"},
            "assurance": {"verdict": "accepted"}
        }]}}), encoding="utf-8")
        result = _run(self.root, "dispatch", "profile fixture", "--run-id", "profile-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        persisted = json.loads((self.root / ".orc" / "profile-run" / "config.json").read_text())
        self.assertEqual(persisted["attempts"]["work-1"][0]["candidate"], {"from": "profile"})

    def test_dispatch_loader_defers_profile_completeness_until_composition(self):
        script = self.root / "assure.sh"
        script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        script.chmod(0o755)
        profile_path = self.root / ".orc" / "profile.json"
        profile_path.parent.mkdir()
        profile_path.write_text(json.dumps({
            "candidate": {"adapter": "git"},
            "assurance": {"adapter": "command"},
            "mirror": {"adapter": "beads", "workspace": "/board"},
        }), encoding="utf-8")

        profile = load_repo_profile(self.root / ".orc")
        merged = validate_config(deep_merge_config(profile or {}, {
            "candidate": {"repo_path": "/repo"},
            "assurance": {"script": str(script), "cwd": str(self.root)},
        }))
        self.assertEqual(merged["candidate"]["repo_path"], "/repo")
        self.assertEqual(merged["assurance"]["adapter"], "command")
        self.assertEqual(merged["mirror"]["workspace"], "/board")

    def test_dispatch_adapter_switch_drops_inherited_command_keys(self):
        profile = self.root / ".orc" / "profile.json"
        profile.parent.mkdir()
        profile.write_text(json.dumps({
            "assurance": {
                "adapter": "command", "script": "scripts/assure.sh",
                "cwd": "/repo", "timeout_s": 120,
            }
        }), encoding="utf-8")
        config_path = self.root / "run.json"
        config_path.write_text(json.dumps({
            "plan": {"works": [{"work_id": "w", "deps": []}]},
            "assurance": {"adapter": "scripted"},
        }), encoding="utf-8")

        result = _run(
            self.root, "dispatch", "adapter switch", "--run-id", "switch-run",
            "--config", str(config_path),
        )

        self.assertEqual(result.returncode, 3, result.stderr)
        persisted = json.loads((self.root / ".orc" / "switch-run" / "config.json").read_text())
        self.assertEqual(persisted["assurance"], {"adapter": "scripted"})

    def test_absent_profile_preserves_empty_scripted_default(self):
        self.assertIsNone(load_repo_profile(self.root / ".orc"))
        result = _run(self.root, "dispatch", "no profile", "--run-id", "empty-default")
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(json.loads((self.root / ".orc" / "empty-default" / "config.json").read_text()), {})

    def test_bad_profile_json_is_canonical_validation_with_next(self):
        profile = self.root / ".orc" / "profile.json"
        profile.parent.mkdir()
        profile.write_text("{bad", encoding="utf-8")
        result = _run(self.root, "dispatch", "bad profile")
        self.assertEqual(result.returncode, 2)
        error = json.loads(result.stderr)
        self.assertEqual(error["error"], "ERR-VALIDATION")
        self.assertEqual(error["next"], ["orc config-schema"])


if __name__ == "__main__":
    unittest.main()
