"""issue #94: "every canonical error carries next-step guidance" -- the
affordance rule (`PLAYBOOK-CLI-USAGE`'s `next:` blocks, issue #43)
extended to the ERROR surface. Subprocess pattern matching
`test_cli_ux_round2.py`/`test_cli_report.py`.

Covers:

- the named regression case: bare `orc report` (no positional arg, no
  `--index`/`--all`) now names where to find a run id, not just what is
  missing;
- a sweep across every other error site this round touched (`main.py`,
  `config.py`, `journal_reading.py`, `report.py`): each canonical error's
  stderr JSON carries a non-empty `next` list of 1-3 strings;
- `ERR-CONFLICT` replay-failure diagnosis (`orc status`'s own failure
  points at `orc history`; every OTHER read command's failure points at
  `orc status`), reusing `test_cli_report.py`'s "poisoned journal"
  fixture technique (a duplicated `FACT-CANDIDATE-OBSERVED` record breaks
  reducer replay).
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from orc_werk.adapters.jsonl import layout

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


def _stderr_error(result: subprocess.CompletedProcess) -> dict:
    return json.loads(result.stderr)


class _NextFieldAssertions:
    def assertUsefulNext(self, error: dict, *, contains: str | None = None) -> None:
        """Every canonical error this round touched carries a `next` list
        of 1-3 non-empty, navigational/runnable strings (issue #94's own
        shape: "1-3 runnable/navigational strings")."""
        self.assertIn("next", error, msg=f"no next field: {error}")
        next_steps = error["next"]
        self.assertIsInstance(next_steps, list)
        self.assertTrue(1 <= len(next_steps) <= 3, msg=next_steps)
        for step in next_steps:
            self.assertIsInstance(step, str)
            self.assertTrue(step.strip())
        if contains is not None:
            self.assertTrue(
                any(contains in step for step in next_steps),
                msg=f"{contains!r} not found in {next_steps}",
            )


class BareReportRegressionTest(unittest.TestCase, _NextFieldAssertions):
    """The exact operator finding that opened issue #94: `orc report` named
    what was missing (a run id) but not where to get it."""

    def test_bare_report_names_run_index_and_report_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(tmp_dir, "report")
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = _stderr_error(result)
            self.assertEqual(error["error"], "ERR-VALIDATION")
            self.assertEqual(
                error["next"],
                [
                    "orc (bare) to list run ids",
                    "orc report --index for the portfolio",
                    "orc report <run-id> for one run",
                ],
            )


class ErrorAffordanceSweepTest(unittest.TestCase, _NextFieldAssertions):
    """Every other canonical-error emission site this round touched: each
    stderr JSON error carries a non-empty, well-shaped `next` list."""

    def test_unknown_run_id_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(tmp_dir, "status", "totally-unknown-run")
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            self.assertUsefulNext(_stderr_error(result), contains="orc dispatch")

    def test_directory_with_multiple_journals_is_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            journal_dir = tmp_dir / ".orc"
            journal_dir.mkdir()
            (journal_dir / "run-a.jsonl").write_text("", encoding="utf-8")
            (journal_dir / "run-b.jsonl").write_text("", encoding="utf-8")
            result = _run_cli(tmp_dir, "status", str(journal_dir))
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = _stderr_error(result)
            self.assertEqual(error["error"], "ERR-VALIDATION")
            self.assertUsefulNext(error, contains="run-a")

    def test_journal_path_that_does_not_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(tmp_dir, "status", "no/such/path.jsonl")
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            self.assertUsefulNext(_stderr_error(result))

    def test_dispatch_intent_required_for_new_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(tmp_dir, "dispatch")
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            self.assertUsefulNext(_stderr_error(result), contains="orc dispatch")

    def test_dispatch_missing_run_id_is_intent_required_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(tmp_dir, "dispatch", "--run-id", "no-such-run")
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            # no run named "no-such-run" exists yet, so this is the
            # "intent is required" branch, not the "no journaled intent"
            # one -- still a validation error with useful next guidance.
            self.assertUsefulNext(_stderr_error(result), contains="orc dispatch")

    def test_dispatch_existing_run_with_no_journaled_intent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            journal_dir = tmp_dir / ".orc" / "no-intent"
            journal_dir.mkdir(parents=True)
            # a structurally valid envelope that is NOT FACT-INTENT-SUBMITTED
            # -- enough for `layout.discover_run_ids`/`history()` (raw
            # envelope reads only, no reducer replay) to count "no-intent"
            # as an existing run with zero journaled intent text.
            (journal_dir / "journal.jsonl").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "seq": 1,
                        "delivery_run_id": "no-intent",
                        "kind": "fact",
                        "id": "FACT-WORK-CREATED",
                        "data": {"work_id": "work-1"},
                        "extensions": {},
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            result = _run_cli(tmp_dir, "dispatch", "--run-id", "no-intent")
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = _stderr_error(result)
            self.assertIn("no journaled intent", error["message"])
            self.assertUsefulNext(error, contains="--run-id no-intent")

    def test_intent_collides_with_existing_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {"attempts": {"work-1": [{"outcome": "completed", "candidate": {"x": 1}, "assurance": {"verdict": "accepted"}}]}}
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            first = _run_cli(tmp_dir, "dispatch", "known-run", "--config", str(config_path), "--run-id", "known-run")
            self.assertEqual(first.returncode, 0, msg=first.stdout + first.stderr)
            second = _run_cli(tmp_dir, "dispatch", "known-run", "--config", str(config_path))
            self.assertEqual(second.returncode, 2, msg=second.stdout + second.stderr)
            self.assertUsefulNext(_stderr_error(second), contains="--run-id known-run")

    def test_config_unknown_top_level_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps({"bogus": 1}), encoding="utf-8")
            result = _run_cli(tmp_dir, "dispatch", "hi", "--config", str(config_path))
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            self.assertUsefulNext(_stderr_error(result), contains="orc config-schema")

    def test_config_not_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config_path = tmp_dir / "cfg.json"
            config_path.write_text("{not json", encoding="utf-8")
            result = _run_cli(tmp_dir, "dispatch", "hi", "--config", str(config_path))
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            self.assertUsefulNext(_stderr_error(result), contains="orc config-schema")

    def test_report_all_with_positional_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(tmp_dir, "report", "--all", "some-run")
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            self.assertUsefulNext(_stderr_error(result))

    def test_report_match_without_all(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(tmp_dir, "report", "--match", "*", "some-run")
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            self.assertUsefulNext(_stderr_error(result), contains="--all")

    def test_report_index_with_positional_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(tmp_dir, "report", "--index", "some-run")
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            self.assertUsefulNext(_stderr_error(result))

    def test_report_missing_journal_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(tmp_dir, "report", "--index", "--journal", str(tmp_dir / "nope"))
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            self.assertUsefulNext(_stderr_error(result), contains="orc dispatch")


class ReplayConflictDiagnosisTest(unittest.TestCase, _NextFieldAssertions):
    """`ERR-CONFLICT` on journal replay (`core/reducer.py`'s per-Fact
    legal-transition check -- a hand-corrupted journal here) is otherwise
    silent about where to look. `orc status`'s own failure points at `orc
    history` (avoids suggesting the exact command that just failed); every
    other read command's failure points at `orc status`."""

    def _build_poisoned_run(self, tmp_dir: Path, run_id: str) -> None:
        config = {
            "attempts": {
                "work-1": [{"outcome": "completed", "candidate": {"x": 1}, "assurance": {"verdict": "accepted"}}]
            }
        }
        config_path = tmp_dir / "cfg.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        result = _run_cli(tmp_dir, "dispatch", f"intent for {run_id}", "--config", str(config_path), "--run-id", run_id)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        journal_path = layout.journal_path(tmp_dir / ".orc", run_id)
        records = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
        duplicate = next(record for record in records if record["id"] == "FACT-CANDIDATE-OBSERVED")
        duplicate["seq"] = records[-1]["seq"] + 1
        with journal_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(duplicate, sort_keys=True) + "\n")

    def test_status_on_poisoned_run_points_at_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            self._build_poisoned_run(tmp_dir, "poisoned")
            result = _run_cli(tmp_dir, "status", "poisoned")
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = _stderr_error(result)
            self.assertEqual(error["error"], "ERR-CONFLICT")
            self.assertUsefulNext(error, contains="orc history poisoned")

    def test_report_on_poisoned_run_points_at_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            self._build_poisoned_run(tmp_dir, "poisoned")
            result = _run_cli(tmp_dir, "report", "poisoned")
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = _stderr_error(result)
            self.assertEqual(error["error"], "ERR-CONFLICT")
            self.assertUsefulNext(error, contains="orc status poisoned")


if __name__ == "__main__":
    unittest.main()
