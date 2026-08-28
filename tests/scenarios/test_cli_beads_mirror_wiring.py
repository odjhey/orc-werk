"""`TASK-M2-006` CLI wiring: `orc dispatch`'s optional `mirror` config
block, mirroring `test_cli_no_mistakes_wiring.py`'s pattern.

Two groups of coverage:

- `MirrorConfigValidationTest` -- `load_config`'s strict validation of the
  new `mirror`/`briefs` top-level keys (unit-level, in-process).
- `MirrorWiringSmokeTest` -- the REAL `orc` CLI entrypoint (subprocess),
  proving: (a) an ABSENT `mirror` key is zero behavior change (no stderr
  output at all, same exit code any existing scripted-only config already
  produces); (b) a configured mirror against a stub `bd` (`tests/
  conformance/support_beads_stub.py`, referenced by absolute path via
  `mirror.bd_bin` -- no `PATH` manipulation needed, unlike the no-mistakes
  precedent, since `BeadsMirror` always invokes its configured `bd_bin`
  directly) issues real `bd` calls; (c) a FORCED stub failure degrades the
  mirror (a `mirror: degraded` stderr note) WITHOUT changing `stdout`/exit
  code at all versus the no-mirror baseline -- the task card's "mirror
  failures MUST NEVER break the delivery loop" guarantee, proven at the
  CLI boundary.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from orc_werk.core.errors import CoreError
from tests.conformance.support_beads_stub import install_stub, read_calls

from orc_werk.cli.config import load_config

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


class MirrorConfigValidationTest(unittest.TestCase):
    def _write(self, tmp: Path, data: dict, *, name: str = "cfg.json") -> str:
        path = tmp / name
        path.write_text(json.dumps(data))
        return str(path)

    def test_absent_mirror_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(Path(tmp), {"attempts": {"work-1": [{"outcome": "completed"}]}})
            data = load_config(path)
            self.assertNotIn("mirror", data)

    def test_mirror_requires_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(Path(tmp), {"mirror": {"adapter": "beads"}})
            with self.assertRaises(CoreError) as ctx:
                load_config(path)
            self.assertEqual(ctx.exception.error["error"], "ERR-VALIDATION")

    def test_mirror_rejects_unknown_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                Path(tmp), {"mirror": {"adapter": "jira", "workspace": "/tmp"}}
            )
            with self.assertRaises(CoreError) as ctx:
                load_config(path)
            self.assertEqual(ctx.exception.error["error"], "ERR-VALIDATION")

    def test_mirror_rejects_unknown_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                Path(tmp), {"mirror": {"adapter": "beads", "workspace": "/tmp", "extra": 1}}
            )
            with self.assertRaises(CoreError) as ctx:
                load_config(path)
            self.assertEqual(ctx.exception.error["error"], "ERR-VALIDATION")

    def test_mirror_with_workspace_and_bd_bin_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                Path(tmp),
                {"mirror": {"adapter": "beads", "workspace": "/tmp", "bd_bin": "/usr/local/bin/bd"}},
            )
            data = load_config(path)
            self.assertEqual(data["mirror"]["workspace"], "/tmp")

    def test_briefs_must_be_string_valued(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(Path(tmp), {"briefs": {"work-1": 123}})
            with self.assertRaises(CoreError) as ctx:
                load_config(path)
            self.assertEqual(ctx.exception.error["error"], "ERR-VALIDATION")

    def test_briefs_valid_without_any_mirror_configured(self) -> None:
        """`briefs` is independently valid even with no `mirror` block --
        simply unused in that case (module docstring)."""
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(Path(tmp), {"briefs": {"work-1": "text"}})
            data = load_config(path)
            self.assertEqual(data["briefs"]["work-1"], "text")


class MirrorWiringSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.journal_dir = self.root / ".orc"
        self.stub_bin = install_stub(self.root)
        self.stub_log = self.root / "bd-stub.log"

    def _env(self, *, fail_verbs: str = "") -> dict:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(SRC)
        env["PATH"] = "/usr/bin:/bin"
        env["ORC_BEADS_STUB_LOG"] = str(self.stub_log)
        if fail_verbs:
            env["ORC_BEADS_STUB_FAIL_VERBS"] = fail_verbs
        else:
            env.pop("ORC_BEADS_STUB_FAIL_VERBS", None)
        return env

    def _run_cli(self, *args: str, fail_verbs: str = "") -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "orc_werk.cli", *args],
            cwd=self.root,
            env=self._env(fail_verbs=fail_verbs),
            capture_output=True,
            text=True,
            timeout=30,
        )

    def _write_config(self, tmp: Path, *, with_mirror: bool) -> Path:
        data: dict = {"attempts": {"work-1": [{"outcome": "completed"}]}}
        if with_mirror:
            data["mirror"] = {"adapter": "beads", "workspace": str(self.root / "bd-workspace"), "bd_bin": str(self.stub_bin)}
        path = tmp / ("cfg-mirror.json" if with_mirror else "cfg-baseline.json")
        path.write_text(json.dumps(data))
        return path

    def test_absent_mirror_key_produces_no_stderr_and_no_mirror_calls(self) -> None:
        config_path = self._write_config(self.root, with_mirror=False)
        result = self._run_cli(
            "dispatch", "ship it",
            "--config", str(config_path), "--journal", str(self.journal_dir),
            "--run-id", "baseline-run",
        )
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertNotIn("mirror", result.stdout)
        self.assertEqual(read_calls(self.stub_log), [])

    def test_configured_mirror_issues_bd_calls_without_changing_exit_code(self) -> None:
        config_path = self._write_config(self.root, with_mirror=True)
        result = self._run_cli(
            "dispatch", "ship it",
            "--config", str(config_path), "--journal", str(self.journal_dir),
            "--run-id", "mirrored-run",
        )
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        calls = read_calls(self.stub_log)
        self.assertGreater(len(calls), 0)
        verbs = {c[3] for c in calls if len(c) > 3}
        self.assertIn("create", verbs)

    def test_degraded_mirror_never_changes_exit_code_or_stdout(self) -> None:
        baseline_config = self._write_config(self.root, with_mirror=False)
        baseline = self._run_cli(
            "dispatch", "ship it",
            "--config", str(baseline_config), "--journal", str(self.journal_dir),
            "--run-id", "degraded-run-baseline",
        )

        mirror_config = self._write_config(self.root, with_mirror=True)
        degraded = self._run_cli(
            "dispatch", "ship it",
            "--config", str(mirror_config), "--journal", str(self.journal_dir),
            "--run-id", "degraded-run-mirrored",
            fail_verbs="create",
        )

        self.assertEqual(baseline.returncode, degraded.returncode, degraded.stdout + degraded.stderr)
        # `--run-id` differs between the two invocations (distinct journal
        # runs), so stdout is compared modulo that one substitutable token
        # rather than byte-for-byte.
        self.assertEqual(
            baseline.stdout.replace("degraded-run-baseline", "RUN"),
            degraded.stdout.replace("degraded-run-mirrored", "RUN"),
        )
        self.assertIn("mirror: degraded", degraded.stderr)
        self.assertEqual(baseline.stderr, "")


if __name__ == "__main__":
    unittest.main()
