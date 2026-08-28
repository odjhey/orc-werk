"""CLI config vocabulary discovery regression tests (GitHub issue #89)."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from orc_werk.cli import config
from orc_werk.cli.config import (
    _ASSURANCE_ADAPTERS,
    _CANDIDATE_ADAPTERS,
    _EXECUTION_ADAPTERS,
    _MIRROR_ADAPTERS,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "orc_werk.cli", *args],
        cwd=REPO_ROOT,
        env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=30,
    )


def _values(values: frozenset[str], *, default: str | None = None) -> str:
    ordered = ([default] if default else []) + sorted(values - ({default} if default else set()))
    return "|".join(ordered)


class ConfigDiscoveryTest(unittest.TestCase):
    def test_config_schema_prints_module_docstring_verbatim(self) -> None:
        result = _run_cli("config-schema")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(result.stdout, config.__doc__)
        for block in ("execution", "candidate", "assurance", "mirror", "briefs"):
            self.assertIn(block, result.stdout)

    def test_dispatch_help_lists_every_config_block_and_validator_adapters(self) -> None:
        result = _run_cli("dispatch", "--help")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("config blocks:", result.stdout)
        self.assertIn("orc config-schema for the full reference", result.stdout)
        for block in ("execution", "candidate", "assurance", "mirror", "briefs", "plan", "attempts"):
            self.assertRegex(result.stdout, rf"(?m)^  {block}\s")

        expected = {
            "execution": _values(_EXECUTION_ADAPTERS, default="scripted"),
            "candidate": _values(_CANDIDATE_ADAPTERS, default="scripted"),
            "assurance": _values(_ASSURANCE_ADAPTERS, default="scripted"),
            "mirror": _values(_MIRROR_ADAPTERS),
        }
        for block, adapters in expected.items():
            self.assertRegex(result.stdout, rf"(?m)^  {block}\s+.*\({adapters}\)$")


if __name__ == "__main__":
    unittest.main()
