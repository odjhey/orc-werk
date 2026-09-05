"""Regression tests for `TASK-M1-003` (CLI UX batch: issues #16, #17, #18,
#23), subprocess pattern matching `test_cli_dogfood_fixes.py`:

- **#16** root-cause surfacing: `status`/`dispatch` append
  `(root_cause=<ERR-*>)` to a `blocked_reason=retry-budget-exhausted` line,
  read from the journaled `FX-START-EXECUTION` effect records'
  `dispatch_result.error`; mixed causes across attempts show the most
  recent (unit-level guard on `_root_cause_for_work`, since a real
  multi-cause dispatch-gate-failure run is not constructible through the
  CLI's config surface -- every attempt in one run shares the same static
  capability configuration).
- **#17** (re-scoped) strict config validation at load time: unknown
  top-level keys and structurally malformed `attempts` entries are
  rejected as canonical `ERR-VALIDATION` before any filesystem side
  effect (no journal directory created); an absent `attempts` key remains
  the valid fully-incremental case (`SCN-007` pending default), not an
  error.
- **#18** journal fail-closed: a file with zero valid records (garbage
  content) is canonical `ERR-VALIDATION`, not silent empty-history
  success; a torn tail with a valid preceding prefix still heals; a bare
  run id with no journal on disk is canonical `ERR-NOT-FOUND` naming the
  run id, with no `.orc/` directory created as a side effect of the
  read-only `status`/`history` commands.
- **#23** `status` shows the submitted intent text
  (`FACT-INTENT-SUBMITTED.data.text`) under `intent:`, not the run id
  (`run:` continues to show the run id separately).
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from orc_werk.adapters.jsonl import layout
from orc_werk.cli.main import _root_cause_for_work

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


# ----------------------------------------------------------------------
# #16 -- root-cause surfacing
# ----------------------------------------------------------------------

CAPABILITY_MISMATCH_CONFIG = {
    "run_id": "s5-capmismatch",
    "max_attempts": 3,
    "resume_capability": "CAP-EXEC-RESUME-EXACT",
    "execution_capabilities": ["CAP-EXEC-RESUME-BEST-EFFORT"],
    "attempts": {
        "work-1": [{"outcome": "completed", "candidate": {"label": "Z"}, "assurance": {"verdict": "accepted"}}]
    },
}


class RootCauseSurfacingTest(unittest.TestCase):
    def test_capability_blocked_run_shows_root_cause_in_dispatch_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config_path = tmp_dir / "config.json"
            config_path.write_text(json.dumps(CAPABILITY_MISMATCH_CONFIG), encoding="utf-8")

            dispatch = _run_cli(
                tmp_dir,
                "dispatch",
                "resume exact but only best-effort supported",
                "--config",
                str(config_path),
            )
            self.assertEqual(dispatch.returncode, 1, msg=dispatch.stdout + dispatch.stderr)
            expected = "blocked_reason=retry-budget-exhausted (root_cause=ERR-UNSUPPORTED-CAPABILITY)"
            self.assertIn(expected, dispatch.stdout)

            status = _run_cli(tmp_dir, "status", "s5-capmismatch")
            self.assertEqual(status.returncode, 1, msg=status.stdout + status.stderr)
            self.assertIn(expected, status.stdout)

    def test_root_cause_absent_when_block_reason_is_not_retry_budget_exhausted(self) -> None:
        # Guard: the root_cause suffix is scoped to
        # blocked_reason=retry-budget-exhausted only (per the ledger's #16
        # scope) -- an assurance-inconclusive block must never grow one.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            # Restated for ADR-0006 (issue #264): reaching an
            # `assurance-inconclusive` BLOCK now takes the assurance budget
            # (INV-021), which defaults to 2 -- so this exhausts it with two
            # inconclusive settlements of the same candidate within the one
            # attempt (`assurances`, consumed in order by assurance_number).
            # The assertion itself is unchanged: no root_cause suffix for a
            # block whose reason is not retry-budget-exhausted.
            config = {
                "run_id": "inconclusive-run",
                "attempts": {
                    "work-1": [
                        {
                            "outcome": "completed",
                            "candidate": {"label": "A"},
                            "assurances": [
                                {"verdict": "inconclusive"},
                                {"verdict": "inconclusive"},
                            ],
                        }
                    ]
                },
            }
            config_path = tmp_dir / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch = _run_cli(tmp_dir, "dispatch", "inconclusive", "--config", str(config_path))
            self.assertEqual(dispatch.returncode, 1, msg=dispatch.stdout + dispatch.stderr)
            self.assertIn("blocked_reason=assurance-inconclusive", dispatch.stdout)
            self.assertNotIn("root_cause=", dispatch.stdout)


class RootCauseMostRecentUnitTest(unittest.TestCase):
    """Unit-level guard on `_root_cause_for_work`'s "most recent wins"
    rule -- a real CLI dispatch cannot easily construct mixed dispatch-gate
    causes within one run (capability config is static for the whole run),
    so this exercises the presentation function directly against
    hand-built, seq-ordered effect-record history."""

    def test_most_recent_error_wins_over_earlier_attempts(self) -> None:
        history = [
            {
                "seq": 1,
                "kind": "effect",
                "id": "FX-START-EXECUTION",
                "data": {"work_id": "work-1", "dispatch_result": {"error": "ERR-UNSUPPORTED-CAPABILITY"}},
            },
            {
                "seq": 2,
                "kind": "effect",
                "id": "FX-START-EXECUTION",
                "data": {"work_id": "work-1", "dispatch_result": {"error": "ERR-PROVIDER-UNAVAILABLE"}},
            },
        ]
        self.assertEqual(_root_cause_for_work(history, "work-1"), "ERR-PROVIDER-UNAVAILABLE")

    def test_no_error_returns_none(self) -> None:
        history = [
            {
                "seq": 1,
                "kind": "effect",
                "id": "FX-START-EXECUTION",
                "data": {"work_id": "work-1", "dispatch_result": {"execution_id": "exec-abc"}},
            }
        ]
        self.assertIsNone(_root_cause_for_work(history, "work-1"))

    def test_other_work_ids_ignored(self) -> None:
        history = [
            {
                "seq": 1,
                "kind": "effect",
                "id": "FX-START-EXECUTION",
                "data": {"work_id": "work-2", "dispatch_result": {"error": "ERR-UNSUPPORTED-CAPABILITY"}},
            }
        ]
        self.assertIsNone(_root_cause_for_work(history, "work-1"))


# ----------------------------------------------------------------------
# #17 (re-scoped) -- strict config validation at load time
# ----------------------------------------------------------------------


class StrictConfigValidationTest(unittest.TestCase):
    def _dispatch(self, tmp_dir: Path, config: dict) -> subprocess.CompletedProcess:
        config_path = tmp_dir / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        return _run_cli(tmp_dir, "dispatch", "config abuse", "--config", str(config_path))

    def test_unknown_top_level_key_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {
                "run_id": "s8d-unknown",
                "attempts": {"work-1": [{"outcome": "completed", "candidate": {"x": 1}, "assurance": {"verdict": "accepted"}}]},
                "totally_bogus_key": True,
            }
            result = self._dispatch(tmp_dir, config)
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-VALIDATION")
            self.assertIn("totally_bogus_key", error["message"])
            # #17 comment fix: a rejected config must never leave a stray
            # journal directory behind.
            self.assertFalse((tmp_dir / ".orc").exists())

    def test_attempts_non_mapping_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {"run_id": "bad-attempts-shape", "attempts": ["not", "a", "mapping"]}
            result = self._dispatch(tmp_dir, config)
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-VALIDATION")
            self.assertFalse((tmp_dir / ".orc").exists())

    def test_attempts_value_non_list_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {"run_id": "bad-attempts-list", "attempts": {"work-1": "not-a-list"}}
            result = self._dispatch(tmp_dir, config)
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-VALIDATION")

    def test_attempts_entry_non_mapping_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {"run_id": "bad-entry-shape", "attempts": {"work-1": ["not-a-mapping"]}}
            result = self._dispatch(tmp_dir, config)
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-VALIDATION")

    def test_attempts_entry_unknown_key_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {
                "run_id": "bad-entry-key",
                "attempts": {"work-1": [{"outcome": "completed", "totally_unknown": 1}]},
            }
            result = self._dispatch(tmp_dir, config)
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-VALIDATION")
            self.assertIn("totally_unknown", error["message"])

    def test_invalid_outcome_value_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {"run_id": "bad-outcome", "attempts": {"work-1": [{"outcome": "not-a-real-outcome"}]}}
            result = self._dispatch(tmp_dir, config)
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-VALIDATION")
            self.assertIn("outcome", error["message"])

    def test_invalid_assurance_verdict_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {
                "run_id": "bad-verdict",
                "attempts": {
                    "work-1": [{"outcome": "completed", "candidate": {"x": 1}, "assurance": {"verdict": "maybe"}}]
                },
            }
            result = self._dispatch(tmp_dir, config)
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-VALIDATION")
            self.assertIn("verdict", error["message"])

    def test_absent_attempts_key_not_rejected_still_pending(self) -> None:
        # Re-scope guard: an absent `attempts` key entirely is the valid
        # fully-incremental case (SCN-007 default), never a load-time
        # rejection.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {"run_id": "fully-incremental"}
            result = self._dispatch(tmp_dir, config)
            self.assertEqual(result.returncode, 3, msg=result.stdout + result.stderr)
            self.assertIn("pending=true", result.stdout)

    def test_planned_work_with_no_entry_not_rejected_still_pending(self) -> None:
        # Re-scope guard: a planned Work with attempts scripted for a
        # sibling Work but no entry of its own is not an error either
        # (DFS-010 missingattempts.json shape).
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {
                "run_id": "s8h-missing",
                "plan": {"works": [{"work_id": "a", "deps": []}, {"work_id": "b", "deps": []}]},
                "attempts": {"a": [{"outcome": "completed", "candidate": {"x": 1}, "assurance": {"verdict": "accepted"}}]},
            }
            result = self._dispatch(tmp_dir, config)
            self.assertEqual(result.returncode, 3, msg=result.stdout + result.stderr)
            self.assertIn("work a: state=ACCEPTED", result.stdout)
            self.assertIn("work b: state=EXECUTING", result.stdout)
            self.assertIn("pending=true", result.stdout)


# ----------------------------------------------------------------------
# #18 -- torn-tail refinement + bare-run-id/garbage-file fail-closed
# ----------------------------------------------------------------------


class JournalFailClosedTest(unittest.TestCase):
    def test_garbage_file_status_is_err_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            ghost = tmp_dir / "ghost.jsonl"
            ghost.write_text("hello this is not json at all, just plain text\n", encoding="utf-8")

            result = _run_cli(tmp_dir, "status", str(ghost))
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-VALIDATION")

    def test_garbage_file_history_is_err_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            ghost = tmp_dir / "ghost.jsonl"
            ghost.write_text("not json either\n", encoding="utf-8")

            result = _run_cli(tmp_dir, "history", str(ghost))
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-VALIDATION")

    def test_torn_tail_with_valid_prefix_still_heals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {
                "run_id": "torn-ok",
                "attempts": {
                    "work-1": [{"outcome": "completed", "candidate": {"label": "A"}, "assurance": {"verdict": "accepted"}}]
                },
            }
            config_path = tmp_dir / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch = _run_cli(tmp_dir, "dispatch", "torn tail happy path", "--config", str(config_path))
            self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)

            journal_path = layout.journal_path(tmp_dir / ".orc", "torn-ok")
            self.assertTrue(journal_path.exists())
            # Simulate a crash mid-append: a valid prefix already on disk,
            # plus one truncated/unparseable final line with no newline.
            with journal_path.open("a", encoding="utf-8") as fh:
                fh.write('{"seq":99,"kind":"fact","id":"FACT-BOGUS","data":{"trunca')

            status = _run_cli(tmp_dir, "status", "torn-ok")
            self.assertEqual(status.returncode, 0, msg=status.stdout + status.stderr)
            self.assertIn("state=ACCEPTED", status.stdout)

    def test_bare_missing_run_id_status_is_err_not_found_no_side_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(tmp_dir, "status", "totally-nonexistent-run-id")
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-NOT-FOUND")
            self.assertIn("totally-nonexistent-run-id", error["message"])
            # The old bug: a read-only status call on an unknown bare run id
            # unconditionally mkdir'd .orc as a side effect.
            self.assertFalse((tmp_dir / ".orc").exists())

    def test_bare_missing_run_id_history_is_err_not_found_no_side_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(tmp_dir, "history", "totally-nonexistent-run-id")
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-NOT-FOUND")
            self.assertFalse((tmp_dir / ".orc").exists())


# ----------------------------------------------------------------------
# #23 -- status shows the submitted intent text
# ----------------------------------------------------------------------


class IntentTextDisplayTest(unittest.TestCase):
    def test_status_shows_submitted_intent_text_not_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {
                "run_id": "s23-intent",
                "attempts": {
                    "work-1": [{"outcome": "completed", "candidate": {"label": "A"}, "assurance": {"verdict": "accepted"}}]
                },
            }
            config_path = tmp_dir / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            intent_text = "write the changelog for the 0.3 release"
            dispatch = _run_cli(tmp_dir, "dispatch", intent_text, "--config", str(config_path))
            self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)

            status = _run_cli(tmp_dir, "status", "s23-intent")
            self.assertEqual(status.returncode, 0, msg=status.stdout + status.stderr)
            self.assertIn("run: s23-intent", status.stdout)
            self.assertIn(f"intent: {intent_text}", status.stdout)
            # The run id must not itself appear as the intent label's value.
            self.assertNotIn("intent: s23-intent", status.stdout)


if __name__ == "__main__":
    unittest.main()
