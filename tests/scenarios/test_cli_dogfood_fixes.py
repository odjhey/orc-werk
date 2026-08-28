"""Regression tests for a dogfooding session's four `orc` CLI defects
(subprocess, JSONL journal, temp directory -- same harness as
`test_cli_end_to_end.py`):

- BUG-1: a hand-authored config with a non-finite float (`NaN`) must fail
  with the canonical `ERR-VALIDATION` error value, not a raw Python
  traceback (`main.py`'s documented "never a Python traceback" contract).
- BUG-2: `max_attempts: 0` (config or `--max-attempts` flag) must be
  rejected as invalid, not silently replaced by the default (`0` is falsy
  in Python, so a naive `or`-chain swallowed it).
- FRICTION-1: `orc history` must surface a journal record's `extensions`
  field (e.g. assurance findings) when present, not just its `data`.
- FRICTION-5: `orc status`/`orc history` given a nonexistent journal path
  must report canonical `ERR-NOT-FOUND` naming the missing path, not leak
  the JSONL adapter's internal filename-safety error.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


def _run_cli(tmp_dir: Path, *args: str) -> subprocess.CompletedProcess:
    env = {"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"}
    return subprocess.run(
        [sys.executable, "-m", "orc_werk.cli", *args],
        cwd=tmp_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


class Bug1NonFiniteFloatTest(unittest.TestCase):
    def test_nan_candidate_is_canonical_validation_error_not_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config_path = tmp_dir / "config.json"
            config_payload = json.dumps(
                {
                    "run_id": "bug1-nan",
                    "attempts": {
                        "work-1": [
                            {
                                "outcome": "completed",
                                "candidate": {"score": float("nan")},
                                "assurance": {"verdict": "accepted"},
                            }
                        ]
                    },
                }
            )
            # json.dumps's default allow_nan=True emits the bare `NaN`
            # token (BUG-1 repro precondition: Python's json.loads accepts
            # it back even though it has no JSON literal).
            self.assertIn("NaN", config_payload)
            config_path.write_text(config_payload, encoding="utf-8")

            result = _run_cli(tmp_dir, "dispatch", "bug1", "--config", str(config_path))

            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-VALIDATION")
            self.assertIn("score", error["message"])
            self.assertIn("score", error["details"]["path"])


class Bug2MaxAttemptsZeroTest(unittest.TestCase):
    def _config(self, tmp_dir: Path, *, max_attempts: object | None) -> Path:
        config: dict = {"run_id": "bug2-run", "attempts": {"work-1": [{"outcome": "failed"}]}}
        if max_attempts is not None:
            config["max_attempts"] = max_attempts
        config_path = tmp_dir / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        return config_path

    def test_config_max_attempts_zero_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config_path = self._config(tmp_dir, max_attempts=0)
            result = _run_cli(tmp_dir, "dispatch", "bug2", "--config", str(config_path))
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-VALIDATION")
            self.assertIn("max_attempts", error["message"])

    def test_flag_max_attempts_zero_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config_path = self._config(tmp_dir, max_attempts=None)
            result = _run_cli(
                tmp_dir, "dispatch", "bug2", "--config", str(config_path), "--max-attempts", "0"
            )
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-VALIDATION")
            self.assertIn("max_attempts", error["message"])

    def test_flag_max_attempts_one_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config_path = self._config(tmp_dir, max_attempts=None)
            result = _run_cli(
                tmp_dir, "dispatch", "bug2", "--config", str(config_path), "--max-attempts", "1"
            )
            self.assertEqual(result.returncode, 1, msg=result.stdout + result.stderr)
            self.assertIn("attempts=1", result.stdout)
            self.assertIn("state=BLOCKED", result.stdout)

    def test_explicit_config_max_attempts_not_overridden_by_absent_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            # TASK-M1-002/SCN-007: pending/incremental mode is now the CLI
            # default, so a *missing* second scripted attempt would rest
            # pending (exit 3) rather than fail -- that is the intended
            # behavior change this task ships, not a regression. This test's
            # actual concern (BUG-2: explicit config max_attempts must not
            # be silently overridden by an absent --max-attempts flag) is
            # orthogonal to that; script both attempts explicitly so the
            # budget-exhaustion path under test stays deterministic.
            config_path = tmp_dir / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "run_id": "bug2-run",
                        "max_attempts": 2,
                        "attempts": {"work-1": [{"outcome": "failed"}, {"outcome": "failed"}]},
                    }
                ),
                encoding="utf-8",
            )
            result = _run_cli(tmp_dir, "dispatch", "bug2", "--config", str(config_path))
            self.assertEqual(result.returncode, 1, msg=result.stdout + result.stderr)
            # config's max_attempts=2 must be honored exactly (not silently
            # replaced by the RunConfig default of 3).
            self.assertIn("attempts=2", result.stdout)


class Friction1HistoryExtensionsTest(unittest.TestCase):
    def test_history_renders_record_extensions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config_path = tmp_dir / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "run_id": "friction1-run",
                        "attempts": {
                            "work-1": [
                                {
                                    "outcome": "completed",
                                    "candidate": {"label": "A"},
                                    "assurance": {
                                        "verdict": "accepted",
                                        "extensions": {
                                            "assurance_findings": {"severity": "low", "note": "ok"}
                                        },
                                    },
                                }
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )
            dispatch = _run_cli(tmp_dir, "dispatch", "friction1", "--config", str(config_path))
            self.assertEqual(dispatch.returncode, 0, msg=dispatch.stderr)

            history = _run_cli(tmp_dir, "history", "friction1-run")
            self.assertEqual(history.returncode, 0, msg=history.stderr)

            # Match the FACT-ASSURE-SETTLED *record line* precisely (kind
            # "fact", id "FACT-ASSURE-SETTLED") -- a plain substring search
            # also matches the later DEC-ACCEPT decision line, whose JSON
            # `basis` payload cites "FACT-ASSURE-SETTLED" as a fact id.
            settled_lines = [
                line
                for line in history.stdout.splitlines()
                if line.split(None, 3)[1:3] == ["fact", "FACT-ASSURE-SETTLED"]
            ]
            self.assertEqual(len(settled_lines), 1, msg=history.stdout)
            self.assertIn("extensions=", settled_lines[0])
            self.assertIn("assurance_findings", settled_lines[0])
            self.assertIn("severity", settled_lines[0])

    def test_history_omits_extensions_marker_when_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config_path = tmp_dir / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "run_id": "friction1-empty",
                        "attempts": {
                            "work-1": [
                                {
                                    "outcome": "completed",
                                    "candidate": {"label": "A"},
                                    "assurance": {"verdict": "accepted"},
                                }
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )
            dispatch = _run_cli(tmp_dir, "dispatch", "friction1-empty", "--config", str(config_path))
            self.assertEqual(dispatch.returncode, 0, msg=dispatch.stderr)

            history = _run_cli(tmp_dir, "history", "friction1-empty")
            self.assertEqual(history.returncode, 0, msg=history.stderr)
            self.assertNotIn("extensions=", history.stdout)


class Friction5MissingJournalPathTest(unittest.TestCase):
    def test_missing_jsonl_path_is_canonical_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(tmp_dir, "status", "some/dir/missing.jsonl")
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-NOT-FOUND")
            self.assertIn("some/dir/missing.jsonl", error["message"])
            self.assertEqual(error["details"]["path"], "some/dir/missing.jsonl")

    def test_missing_jsonl_path_history_also_canonical_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(tmp_dir, "history", "nested/missing.jsonl")
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-NOT-FOUND")

    def test_bare_run_id_unaffected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(tmp_dir, "status", "no-such-run-id")
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("(no work recorded yet)", result.stdout)

    def test_directory_target_unaffected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            empty_dir = tmp_dir / "journal-dir"
            empty_dir.mkdir()
            result = _run_cli(tmp_dir, "status", str(empty_dir))
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-NOT-FOUND")
            self.assertIn("no *.jsonl journal files found", error["message"])


if __name__ == "__main__":
    unittest.main()
