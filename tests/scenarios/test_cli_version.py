"""Scenario coverage for the read-only ``orc version`` identity surface."""

from __future__ import annotations

import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from orc_werk.cli import main as cli_main

_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def _declared_version() -> str:
    """The version pyproject.toml declares — the independent source the CLI
    must agree with, so a release bump cannot silently diverge from the
    reported identity (and the test needs no edit per bump)."""
    for line in _PYPROJECT.read_text(encoding="utf-8").splitlines():
        if line.startswith("version = "):
            return line.split('"')[1]
    raise AssertionError(f"no version line found in {_PYPROJECT}")


class CliVersionTest(unittest.TestCase):
    def _run_in(self, cwd: Path) -> tuple[int, str]:
        previous = Path.cwd()
        stream = io.StringIO()
        try:
            os.chdir(cwd)
            with redirect_stdout(stream):
                exit_code = cli_main(["version"])
        finally:
            os.chdir(previous)
        return exit_code, stream.getvalue()

    def test_checkout_identity_and_no_journal(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            exit_code, output = self._run_in(tmp_path)

            self.assertEqual(exit_code, 0)
            self.assertIn(f"orc {_declared_version()}", output)
            self.assertRegex(output, r"git [0-9a-f]{7,}(?:\+dirty)?")
            self.assertFalse((tmp_path / ".orc").exists())

    def test_git_unavailable_degrades_honestly(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            with patch.object(subprocess, "run", side_effect=FileNotFoundError("git")):
                exit_code, output = self._run_in(tmp_path)

            self.assertEqual(exit_code, 0)
            self.assertIn(f"orc {_declared_version()}", output)
            self.assertIn("git unavailable", output)
            self.assertFalse((tmp_path / ".orc").exists())


if __name__ == "__main__":
    unittest.main()
