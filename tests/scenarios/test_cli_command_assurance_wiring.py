"""Real CLI wiring for the generic command assurance verify seat."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from orc_werk.cli.config import load_config
from orc_werk.core.errors import CoreError

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


class CommandAssuranceConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.script = self.root / "assure.sh"
        self.script.write_text("#!/bin/sh\ncat >/dev/null\nexit 0\n")
        self.script.chmod(0o755)

    def write(self, assurance: dict, candidate: dict | None = None, attempts: dict | None = None) -> str:
        data = {"assurance": assurance}
        if candidate is not None:
            data["candidate"] = candidate
        if attempts is not None:
            data["attempts"] = attempts
        path = self.root / "config.json"
        path.write_text(json.dumps(data))
        return str(path)

    def test_required_keys_timeout_and_git_combo(self) -> None:
        base = {"adapter": "command", "script": self.script.name, "cwd": str(self.root)}
        for broken in (
            {"adapter": "command", "cwd": str(self.root)},
            {"adapter": "command", "script": self.script.name},
            {**base, "timeout_s": 0},
            {**base, "args": []},
        ):
            with self.subTest(broken=broken), self.assertRaises(CoreError):
                load_config(self.write(broken, {"adapter": "git", "repo_path": str(self.root)}))
        with self.assertRaises(CoreError):
            load_config(self.write(base))
        loaded = load_config(self.write(base, {"adapter": "git", "repo_path": str(self.root)}))
        self.assertEqual(loaded["assurance"]["adapter"], "command")

    def test_containment_and_provider_availability(self) -> None:
        outside = self.root.parent / f"outside-command-{os.getpid()}.sh"
        outside.write_text("#!/bin/sh\nexit 0\n")
        outside.chmod(0o755)
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        with self.assertRaises(CoreError) as escaped:
            load_config(self.write(
                {"adapter": "command", "script": str(outside), "cwd": str(self.root)},
                {"adapter": "git", "repo_path": str(self.root)},
            ))
        self.assertEqual(escaped.exception.error["error"], "ERR-VALIDATION")
        with self.assertRaises(CoreError) as missing:
            load_config(self.write(
                {"adapter": "command", "script": "missing.sh", "cwd": str(self.root)},
                {"adapter": "git", "repo_path": str(self.root)},
            ))
        self.assertEqual(missing.exception.error["error"], "ERR-PROVIDER-UNAVAILABLE")

    def test_real_assurance_drops_config_scripted_verdict(self) -> None:
        with self.assertRaises(CoreError):
            load_config(self.write(
                {"adapter": "command", "script": self.script.name, "cwd": str(self.root)},
                {"adapter": "git", "repo_path": str(self.root)},
                {"work-1": [{"outcome": "completed", "assurance": {"verdict": "accepted"}}]},
            ))


class CommandAssuranceCliSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        _git(["init", "-q"], self.repo)
        _git(["config", "user.email", "command@example.invalid"], self.repo)
        _git(["config", "user.name", "Command Fixture"], self.repo)
        (self.repo / "tracked.txt").write_text("base\n")
        _git(["add", "."], self.repo)
        _git(["commit", "-q", "-m", "init"], self.repo)
        self.journal = self.root / ".orc"

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(SRC)
        return subprocess.run(
            [sys.executable, "-m", "orc_werk.cli", *args],
            cwd=self.root,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )

    def config(self, exit_code: int) -> Path:
        script = self.repo / "scripts" / "assure.sh"
        script.parent.mkdir(exist_ok=True)
        capture = self.root / "received.json"
        script.write_text(f"#!/bin/sh\ncat > {capture}\nprintf '{{\"evidence_refs\":[{{\"fixture\":\"command\"}}]}}'\nexit {exit_code}\n")
        script.chmod(0o755)
        path = self.root / "config.json"
        path.write_text(json.dumps({
            "candidate": {"adapter": "git", "repo_path": str(self.repo)},
            "assurance": {"adapter": "command", "script": "scripts/assure.sh", "cwd": str(self.repo), "timeout_s": 5},
            "attempts": {"work-1": [{"outcome": "completed"}]},
        }))
        return path

    def test_accepted_cycle_and_journaled_evidence(self) -> None:
        config = self.config(0)
        result = self.run_cli("dispatch", "verify candidate", "--config", str(config), "--journal", str(self.journal), "--run-id", "command-smoke")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("state=ACCEPTED", result.stdout)
        document = json.loads((self.root / "received.json").read_text())
        self.assertEqual(document["schema"], "command-assurance-input/v1")
        history = self.run_cli("history", "command-smoke", "--journal", str(self.journal), "--limit", "0")
        self.assertEqual(history.returncode, 0, history.stdout + history.stderr)
        self.assertIn("script_sha256", history.stdout)
        self.assertIn('"fixture":"command"', history.stdout)

    def test_exit_one_blocks_as_rejected(self) -> None:
        config = self.config(1)
        result = self.run_cli("dispatch", "reject candidate", "--config", str(config), "--journal", str(self.journal), "--run-id", "command-reject")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("verdict=rejected", result.stdout)
        self.assertIn("attempt 2 opened", result.stdout)


if __name__ == "__main__":
    unittest.main()
