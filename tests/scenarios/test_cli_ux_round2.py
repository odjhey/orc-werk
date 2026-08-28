"""Regression tests for the CLI-UX round (issue #43 + its two watchtower
comments: pagination/progressive-disclosure, and the HATEOAS-style
per-state affordance reframe), subprocess pattern matching
`test_cli_ux_batch.py`/`test_cli_dogfood_fixes.py`.

Covers:

- item 1, content-first: bare `orc` prints a live text index (content,
  empty-state, truncation hint) instead of an argparse usage error;
- item 3, pagination: `orc history`/`orc crew-report list` default to the
  last 30 records with a definitive `--limit 0` hint; exact counts.
- item 4, HATEOAS affordances: the `next:` block per state (pending
  execution/assurance, blocked, accepted with/without a `pr` candidate
  field), and the `ERR-NOT-FOUND(run)` affordance;
- item 2, help quality: the top-level epilog's exit-code table and
  promises, per-subcommand examples, and stripped task-card/extension IDs.
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


def _write_minimal_run(directory: Path, run_id: str, *, num_records: int, mtime: float) -> None:
    """Write a minimal-but-structurally-valid run journal directly (no
    Work, just `num_records` `FACT-INTENT-SUBMITTED`-shaped envelopes with
    ascending `seq`) -- fast fixture construction for pagination/index
    tests that don't need a real delivery run, only a journal file
    `history()`/the bare index can read. Mirrors the raw envelope shape
    `JSONLJournal` itself writes (`schema_version`/`seq`/`delivery_run_id`/
    `kind`/`id`/`data`/`extensions`)."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{run_id}.jsonl"
    lines = []
    for seq in range(1, num_records + 1):
        lines.append(
            json.dumps(
                {
                    "schema_version": 1,
                    "seq": seq,
                    "delivery_run_id": run_id,
                    "kind": "fact",
                    "id": "FACT-INTENT-SUBMITTED",
                    "data": {"intent_id": run_id, "text": f"record {seq}"},
                    "extensions": {},
                },
                sort_keys=True,
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    import os

    os.utime(path, (mtime, mtime))


# ----------------------------------------------------------------------
# item 1 -- bare `orc` content-first index
# ----------------------------------------------------------------------


class BareIndexTest(unittest.TestCase):
    def test_empty_journal_dir_shows_definitive_zero_and_dispatch_affordance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(tmp_dir)
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn(f"0 runs in {(tmp_dir / '.orc').resolve()}", result.stdout)
            self.assertIn("next:", result.stdout)
            self.assertIn("orc dispatch", result.stdout)
            # Strictly read-only: no journal directory created by the bare
            # index over an empty/missing default dir.
            self.assertFalse((tmp_dir / ".orc").exists())

    def test_index_shows_run_id_state_attempts_and_pending_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            accepted_config = {
                "run_id": "accepted-run",
                "attempts": {
                    "work-1": [{"outcome": "completed", "candidate": {"label": "A"}, "assurance": {"verdict": "accepted"}}]
                },
            }
            pending_config = {"run_id": "pending-run", "attempts": {}}
            for name, config in (("a.json", accepted_config), ("b.json", pending_config)):
                config_path = tmp_dir / name
                config_path.write_text(json.dumps(config), encoding="utf-8")
                intent = "ship it" if name == "a.json" else "wait for it"
                dispatch = _run_cli(tmp_dir, "dispatch", intent, "--config", str(config_path))
                self.assertIn(dispatch.returncode, (0, 3), msg=dispatch.stdout + dispatch.stderr)

            result = _run_cli(tmp_dir)
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("2 runs in", result.stdout)
            self.assertIn("accepted-run: work-1=ACCEPTED attempts=1", result.stdout)
            self.assertIn("pending-run: work-1=EXECUTING attempts=1 pending=execution-outcome", result.stdout)

    def test_index_truncates_with_definitive_exact_count_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            journal_dir = tmp_dir / ".orc"
            total = 35
            for i in range(total):
                _write_minimal_run(journal_dir, f"run-{i:03d}", num_records=1, mtime=1_700_000_000 + i)

            result = _run_cli(tmp_dir)
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn(f"{total} runs in", result.stdout)
            # Exact counts, never an ambiguous "...more" (axi #5): the hint
            # names both the shown count and the real total, plus the real
            # escape hatch (bare `orc` has no --limit of its own).
            self.assertIn("... showing last 30 of 35 runs; orc report --index for all", result.stdout)
            run_lines = [line for line in result.stdout.splitlines() if line.startswith("run-")]
            self.assertEqual(len(run_lines), 30)
            # Most-recently-modified first: run-034 (highest mtime) leads.
            self.assertTrue(run_lines[0].startswith("run-034:"))


# ----------------------------------------------------------------------
# item 3 -- pagination (`orc history`, `orc crew-report list`)
# ----------------------------------------------------------------------


class HistoryPaginationTest(unittest.TestCase):
    def test_default_limit_shows_last_30_with_definitive_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            _write_minimal_run(tmp_dir / ".orc", "big-run", num_records=45, mtime=1_700_000_000)
            result = _run_cli(tmp_dir, "history", "big-run")
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            lines = result.stdout.splitlines()
            record_lines = [line for line in lines if line.startswith("[")]
            self.assertEqual(len(record_lines), 30)
            # Last N means the most recent: seq 0016..0045 shown, oldest 15 dropped.
            self.assertIn("[0016]", record_lines[0])
            self.assertIn("[0045]", record_lines[-1])
            self.assertEqual(lines[-1], "... showing last 30 of 45 records; --limit 0 for all")

    def test_limit_zero_shows_all(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            _write_minimal_run(tmp_dir / ".orc", "big-run", num_records=45, mtime=1_700_000_000)
            result = _run_cli(tmp_dir, "history", "big-run", "--limit", "0")
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            record_lines = [line for line in result.stdout.splitlines() if line.startswith("[")]
            self.assertEqual(len(record_lines), 45)
            self.assertNotIn("showing last", result.stdout)

    def test_since_seq_filters_before_the_default_limit_applies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            _write_minimal_run(tmp_dir / ".orc", "big-run", num_records=45, mtime=1_700_000_000)
            result = _run_cli(tmp_dir, "history", "big-run", "--since-seq", "40")
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            record_lines = [line for line in result.stdout.splitlines() if line.startswith("[")]
            # Only seq 41..45 match the filter -- fewer than the default
            # limit, so no truncation hint at all.
            self.assertEqual(len(record_lines), 5)
            self.assertIn("[0041]", record_lines[0])
            self.assertNotIn("showing last", result.stdout)

    def test_small_run_untruncated_no_regression(self) -> None:
        # Guard: existing small-journal tests must see no hint line at all.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            _write_minimal_run(tmp_dir / ".orc", "small-run", num_records=3, mtime=1_700_000_000)
            result = _run_cli(tmp_dir, "history", "small-run")
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertNotIn("showing last", result.stdout)
            self.assertEqual(len([l for l in result.stdout.splitlines() if l.startswith("[")]), 3)


class CrewReportListPaginationTest(unittest.TestCase):
    def test_default_limit_shows_last_30_with_definitive_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            total = 35
            for turn in range(1, total + 1):
                result = _run_cli(
                    tmp_dir,
                    "crew-report",
                    "append",
                    "some-run",
                    "--execution-id",
                    "e1",
                    "--payload",
                    json.dumps({"turn": turn, "claimed_verdict": "waiting"}),
                )
                self.assertEqual(result.returncode, 0, msg=result.stderr)

            listed = _run_cli(tmp_dir, "crew-report", "list", "some-run")
            self.assertEqual(listed.returncode, 0, msg=listed.stdout + listed.stderr)
            lines = listed.stdout.splitlines()
            record_lines = [line for line in lines if line.startswith("[")]
            self.assertEqual(len(record_lines), 30)
            self.assertIn('"turn":6', record_lines[0])
            self.assertIn('"turn":35', record_lines[-1])
            self.assertEqual(lines[-1], "... showing last 30 of 35 reports; --limit 0 for all")

            full = _run_cli(tmp_dir, "crew-report", "list", "some-run", "--limit", "0")
            self.assertEqual(full.returncode, 0, msg=full.stdout + full.stderr)
            full_record_lines = [line for line in full.stdout.splitlines() if line.startswith("[")]
            self.assertEqual(len(full_record_lines), 35)
            self.assertNotIn("showing last", full.stdout)


# ----------------------------------------------------------------------
# item 4 -- HATEOAS-style per-state affordances
# ----------------------------------------------------------------------


class AffordanceTest(unittest.TestCase):
    def test_pending_execution_next_block_has_exact_redispatch_with_absolute_config_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {"run_id": "pending-exec", "attempts": {}}
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch = _run_cli(tmp_dir, "dispatch", "wait on me", "--config", str(config_path))
            self.assertEqual(dispatch.returncode, 3, msg=dispatch.stdout + dispatch.stderr)
            self.assertIn("next:", dispatch.stdout)
            self.assertIn("record the execution outcome for work(s): work-1", dispatch.stdout)
            # issue #55 H2: config persistence -- the affordance now names
            # the durable in-run-dir config (refreshed by this very
            # dispatch, since --config was given), not the caller's own
            # ephemeral --config path.
            abs_config = str(layout.config_path(tmp_dir / ".orc", "pending-exec").resolve())
            abs_journal = str((tmp_dir / ".orc").resolve())
            expected_command = (
                f"orc dispatch 'wait on me' --config {abs_config} "
                f"--journal {abs_journal} --run-id pending-exec"
            )
            self.assertIn(f"then re-run: {expected_command}", dispatch.stdout)

    def test_pending_assurance_next_block_notes_different_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {
                "run_id": "pending-assure",
                "attempts": {"work-1": [{"outcome": "completed", "candidate": {"label": "A"}}]},
            }
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch = _run_cli(tmp_dir, "dispatch", "assure me", "--config", str(config_path))
            self.assertEqual(dispatch.returncode, 3, msg=dispatch.stdout + dispatch.stderr)
            self.assertIn("record the assurance verdict for work(s): work-1", dispatch.stdout)
            self.assertIn("different agent than the one that recorded the settlement", dispatch.stdout)
            self.assertIn("playbook discipline", dispatch.stdout)

    def test_blocked_next_block_points_at_history_for_root_cause(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {
                "run_id": "blocked-run",
                "max_attempts": 1,
                "attempts": {"work-1": [{"outcome": "failed"}]},
            }
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch = _run_cli(tmp_dir, "dispatch", "will fail", "--config", str(config_path))
            self.assertEqual(dispatch.returncode, 1, msg=dispatch.stdout + dispatch.stderr)
            self.assertIn("next:", dispatch.stdout)
            self.assertIn("BLOCKED (blocked_reason=retry-budget-exhausted)", dispatch.stdout)
            self.assertIn("retry budget exhausted -- no attempts remain", dispatch.stdout)
            self.assertIn("see orc history blocked-run for the root cause", dispatch.stdout)

    def test_accepted_next_block_has_report_and_gh_pr_view_when_pr_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {
                "run_id": "accepted-with-pr",
                "attempts": {
                    "work-1": [
                        {
                            "outcome": "completed",
                            "candidate": {"pr": 77, "head_sha": "cafef00d"},
                            "assurance": {"verdict": "accepted"},
                        }
                    ]
                },
            }
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch = _run_cli(tmp_dir, "dispatch", "ship it", "--config", str(config_path))
            self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)
            self.assertIn("see the full run report: orc report accepted-with-pr", dispatch.stdout)
            self.assertIn("work-1's candidate carries pr 77: gh pr view 77", dispatch.stdout)

            status = _run_cli(tmp_dir, "status", "accepted-with-pr")
            self.assertEqual(status.returncode, 0, msg=status.stdout + status.stderr)
            self.assertIn("gh pr view 77", status.stdout)

    def test_accepted_next_block_omits_gh_pr_view_when_no_pr_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {
                "run_id": "accepted-no-pr",
                "attempts": {
                    "work-1": [
                        {"outcome": "completed", "candidate": {"label": "A"}, "assurance": {"verdict": "accepted"}}
                    ]
                },
            }
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch = _run_cli(tmp_dir, "dispatch", "ship it plainly", "--config", str(config_path))
            self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)
            self.assertIn("see the full run report: orc report accepted-no-pr", dispatch.stdout)
            self.assertNotIn("gh pr view", dispatch.stdout)

    def test_multi_work_same_state_grouped_into_one_bullet_not_repeated(self) -> None:
        # Multi-work runs: works sharing the same next-step guidance are
        # named together in one bullet, with exactly one shared re-dispatch
        # command -- never one bullet (or one redispatch line) repeated per
        # work (item 4's "grouped/deduplicated sensibly").
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {
                "run_id": "fanout",
                "plan": {"works": [{"work_id": "a", "deps": []}, {"work_id": "b", "deps": []}]},
                "attempts": {},
            }
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch = _run_cli(tmp_dir, "dispatch", "fan out", "--config", str(config_path))
            self.assertEqual(dispatch.returncode, 3, msg=dispatch.stdout + dispatch.stderr)
            self.assertIn("record the execution outcome for work(s): a, b", dispatch.stdout)
            self.assertEqual(dispatch.stdout.count("record the execution outcome for work(s):"), 1)
            self.assertEqual(dispatch.stdout.count("then re-run:"), 1)

    def test_not_found_run_shows_available_runs_and_dispatch_affordance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {
                "run_id": "known-run",
                "attempts": {
                    "work-1": [{"outcome": "completed", "candidate": {"label": "A"}, "assurance": {"verdict": "accepted"}}]
                },
            }
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch = _run_cli(tmp_dir, "dispatch", "known thing", "--config", str(config_path))
            self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)

            result = _run_cli(tmp_dir, "status", "totally-unknown-run")
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-NOT-FOUND")
            self.assertIn("available runs in", result.stdout)
            self.assertIn("known-run", result.stdout)
            self.assertIn("next:", result.stdout)
            self.assertIn("orc dispatch", result.stdout)


# ----------------------------------------------------------------------
# item 2 -- help quality
# ----------------------------------------------------------------------


class HelpQualityTest(unittest.TestCase):
    def test_top_level_help_has_exit_code_table_and_promises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(tmp_dir, "--help")
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("exit codes:", result.stdout)
            for code_line in ("0   all Work ACCEPTED", "1   some Work BLOCKED", "2   usage/config error", "3   run non-terminal"):
                self.assertIn(code_line, result.stdout)
            self.assertIn("canonical JSON", result.stdout)
            self.assertIn("idempotent", result.stdout)
            self.assertIn("never prompts interactively", result.stdout)
            # Rot removed: no "(M0)" branding, no bare task-card/extension IDs.
            self.assertNotIn("(M0)", result.stdout)
            self.assertNotIn("TASK-M1-007", result.stdout)
            self.assertNotIn("TASK-M1-008", result.stdout)
            self.assertNotIn("EXT-CREW-REPORT-V1", result.stdout)

    def test_dispatch_help_has_examples_and_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(tmp_dir, "dispatch", "--help")
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("examples:", result.stdout)
            self.assertIn('orc dispatch "ship the widget"', result.stdout)
            self.assertIn("defaults:", result.stdout)

    def test_history_help_documents_pagination_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(tmp_dir, "history", "--help")
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("--limit", result.stdout)
            self.assertIn("--since-seq", result.stdout)
            self.assertIn("examples:", result.stdout)

    def test_crew_report_list_help_documents_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(tmp_dir, "crew-report", "list", "--help")
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("--limit", result.stdout)


if __name__ == "__main__":
    unittest.main()
