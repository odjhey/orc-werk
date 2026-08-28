"""Regression tests for issue #55 housekeeping:

- H1 per-run directory layout (`.orc/<run>/{journal,times,reports}.jsonl`,
  `report.html`) with legacy flat-file read-fallback -- writes always use
  the new layout, but a pre-existing flat `.orc` dir keeps working, and a
  legacy run never splits its records across both layouts mid-run.
- H2 journal-dir precedence: `--journal` flag > `ORC_JOURNAL_DIR` env >
  `./.orc` default.
- Dispatch config persistence into the run dir (`.orc/<run>/config.json`)
  on first dispatch, refreshed whenever `--config` is explicitly given, so
  a later dispatch may be invoked with just the run id.
- OSC-8 clickable paths: TTY-gated wrapping of every printed `report:`/
  `journal:`/index-line path, byte-identical (zero escape bytes) when
  stdout is not a TTY.

Subprocess-driven for real end-to-end coverage (stdout piped by
`subprocess.run` is never a TTY, which is itself the non-TTY negative-
assertion fixture for OSC-8); a small in-process section drives
`orc_werk.cli.main.main()` directly against a fake TTY stream to exercise
the positive (wrapped) OSC-8 branch, since no subprocess pipe can ever be
one.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from orc_werk.adapters.jsonl import layout
from orc_werk.cli import main as run_cli_main
from orc_werk.cli.hyperlink import hyperlink_path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


def _run_cli(tmp_dir: Path, *args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"}
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "orc_werk.cli", *args],
        cwd=tmp_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _accepted_config(run_id: str, **overrides) -> dict:
    config = {
        "run_id": run_id,
        "attempts": {
            "work-1": [{"outcome": "completed", "candidate": {"x": 1}, "assurance": {"verdict": "accepted"}}]
        },
    }
    config.update(overrides)
    return config


class LegacyLayoutReadFallbackTest(unittest.TestCase):
    """H1: writes always land on the new per-run-dir layout, but every
    read path (bare `orc` index, `status`/`history` by bare run id,
    `report`/`report --all`/`--match`, sidecar discovery) accepts a
    pre-existing legacy flat run exactly as before -- and re-dispatching a
    legacy run never migrates or splits it."""

    def _seed_legacy_run(self, tmp_dir: Path, journal_dir: Path, run_id: str) -> Path:
        """Dispatch a run normally (new layout), then transplant its
        journal bytes to the flat legacy path and delete the per-run
        directory -- simulating a run that already existed in the pre-#55
        flat layout, without hand-authoring envelope bytes by hand.
        Returns the dispatch config path (reusable for a legacy re-dispatch)."""
        config_path = tmp_dir / f"{run_id}.config.json"
        config_path.write_text(json.dumps(_accepted_config(run_id)), encoding="utf-8")
        result = _run_cli(
            tmp_dir, "dispatch", f"legacy fixture {run_id}", "--config", str(config_path),
            "--journal", str(journal_dir),
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

        new_journal = layout.run_dir(journal_dir, run_id) / layout.JOURNAL_FILENAME
        legacy_journal = journal_dir / f"{run_id}.jsonl"
        legacy_journal.write_bytes(new_journal.read_bytes())
        shutil.rmtree(layout.run_dir(journal_dir, run_id))
        return config_path

    def test_status_history_report_read_a_pre_existing_legacy_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            journal_dir = tmp_dir / ".orc"
            self._seed_legacy_run(tmp_dir, journal_dir, "legacy-run")

            status = _run_cli(tmp_dir, "status", "legacy-run")
            self.assertEqual(status.returncode, 0, msg=status.stdout + status.stderr)
            self.assertIn("run: legacy-run", status.stdout)
            self.assertIn("state=ACCEPTED", status.stdout)

            history = _run_cli(tmp_dir, "history", "legacy-run")
            self.assertEqual(history.returncode, 0, msg=history.stdout + history.stderr)
            self.assertIn("FACT-INTENT-SUBMITTED", history.stdout)

            report = _run_cli(tmp_dir, "report", "legacy-run")
            self.assertEqual(report.returncode, 0, msg=report.stdout + report.stderr)
            out_path = layout.report_html_path(journal_dir, "legacy-run")
            # Legacy default output lands BESIDE the flat journal, not
            # inside a new run directory.
            self.assertEqual(out_path, journal_dir / "legacy-run.report.html")
            self.assertTrue(out_path.exists())

            index = _run_cli(tmp_dir)  # bare `orc`
            self.assertEqual(index.returncode, 0, msg=index.stdout + index.stderr)
            self.assertIn("legacy-run", index.stdout)

    def test_redispatching_a_legacy_run_never_splits_or_migrates_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            journal_dir = tmp_dir / ".orc"
            config_path = self._seed_legacy_run(tmp_dir, journal_dir, "legacy-continue")

            redispatch = _run_cli(
                tmp_dir, "dispatch", "legacy fixture legacy-continue", "--config", str(config_path),
                "--journal", str(journal_dir), "--run-id", "legacy-continue",
            )
            self.assertEqual(redispatch.returncode, 0, msg=redispatch.stdout + redispatch.stderr)
            # Still exactly the flat file -- the JOURNAL specifically never
            # migrates/splits. (`--config` was given, so config persistence
            # -- which has no legacy fallback of its own, see
            # orc_werk.adapters.jsonl.layout.config_path -- legitimately
            # creates the run's directory for config.json alone; that is
            # not a journal-layout migration.)
            self.assertTrue((journal_dir / "legacy-continue.jsonl").exists())
            run_dir = layout.run_dir(journal_dir, "legacy-continue")
            self.assertFalse((run_dir / layout.JOURNAL_FILENAME).exists())
            self.assertTrue((run_dir / layout.CONFIG_FILENAME).exists())

    def test_report_all_and_match_see_a_mix_of_legacy_and_new_layout_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            journal_dir = tmp_dir / ".orc"
            self._seed_legacy_run(tmp_dir, journal_dir, "mix-legacy")
            config_path = tmp_dir / "mix-new.config.json"
            config_path.write_text(json.dumps(_accepted_config("mix-new")), encoding="utf-8")
            fresh = _run_cli(
                tmp_dir, "dispatch", "mix fixture new", "--config", str(config_path),
                "--journal", str(journal_dir),
            )
            self.assertEqual(fresh.returncode, 0, msg=fresh.stdout + fresh.stderr)

            result = _run_cli(tmp_dir, "report", "--all", "--journal", str(journal_dir))
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            index_html = (journal_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn("mix-legacy", index_html)
            self.assertIn("mix-new", index_html)

    def test_crew_report_log_independently_uses_new_layout_for_a_legacy_journal_run(self) -> None:
        """Per-artifact discrimination (`orc_werk.adapters.jsonl.layout`'s
        module docstring): a legacy-journal run with no pre-existing legacy
        `+reports.jsonl` gets the NEW layout for crew reports specifically
        -- the journal and the crew-report log are allowed to sit on
        different layouts for the same run, since the crew-report CLI
        surface never requires a journal to exist at all."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            journal_dir = tmp_dir / ".orc"
            self._seed_legacy_run(tmp_dir, journal_dir, "legacy-crew")

            append = _run_cli(
                tmp_dir, "crew-report", "append", "legacy-crew",
                "--execution-id", "exec-1", "--payload",
                json.dumps({"turn": 1, "claimed_verdict": "done"}),
                "--journal", str(journal_dir),
            )
            self.assertEqual(append.returncode, 0, msg=append.stdout + append.stderr)

            self.assertTrue((journal_dir / "legacy-crew.jsonl").exists())  # journal: still flat
            self.assertFalse((journal_dir / "legacy-crew+reports.jsonl").exists())
            self.assertTrue(
                (layout.run_dir(journal_dir, "legacy-crew") / layout.REPORTS_FILENAME).exists()
            )  # reports: new layout, independently

            listed = _run_cli(tmp_dir, "crew-report", "list", "legacy-crew", "--journal", str(journal_dir))
            self.assertEqual(listed.returncode, 0, msg=listed.stdout + listed.stderr)
            self.assertIn("claimed_verdict", listed.stdout)


class JournalDirPrecedenceTest(unittest.TestCase):
    """H2: `--journal` flag > `ORC_JOURNAL_DIR` env > `./.orc` default."""

    def test_default_when_neither_given(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps(_accepted_config("default-run")), encoding="utf-8")
            result = _run_cli(tmp_dir, "dispatch", "default dir fixture", "--config", str(config_path))
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertTrue((tmp_dir / ".orc" / "default-run" / "journal.jsonl").exists())

    def test_env_var_overrides_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            custom_dir = tmp_dir / "custom-journal-dir"
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps(_accepted_config("env-run")), encoding="utf-8")
            result = _run_cli(
                tmp_dir, "dispatch", "env dir fixture", "--config", str(config_path),
                env_extra={"ORC_JOURNAL_DIR": str(custom_dir)},
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertFalse((tmp_dir / ".orc").exists())
            self.assertTrue((custom_dir / "env-run" / "journal.jsonl").exists())

            # status (no --journal flag of its own) also honors the env
            # var for bare-run-id resolution.
            status = _run_cli(
                tmp_dir, "status", "env-run", env_extra={"ORC_JOURNAL_DIR": str(custom_dir)}
            )
            self.assertEqual(status.returncode, 0, msg=status.stdout + status.stderr)
            self.assertIn("run: env-run", status.stdout)

            # bare `orc` (no args) also honors it.
            index = _run_cli(tmp_dir, env_extra={"ORC_JOURNAL_DIR": str(custom_dir)})
            self.assertEqual(index.returncode, 0, msg=index.stdout + index.stderr)
            self.assertIn("env-run", index.stdout)

    def test_explicit_flag_beats_env_var(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            env_dir = tmp_dir / "env-journal-dir"
            flag_dir = tmp_dir / "flag-journal-dir"
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps(_accepted_config("flag-run")), encoding="utf-8")
            result = _run_cli(
                tmp_dir, "dispatch", "flag beats env fixture", "--config", str(config_path),
                "--journal", str(flag_dir),
                env_extra={"ORC_JOURNAL_DIR": str(env_dir)},
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertTrue((flag_dir / "flag-run" / "journal.jsonl").exists())
            self.assertFalse(env_dir.exists())

            status = _run_cli(
                tmp_dir, "status", "flag-run", "--journal", str(flag_dir),
                env_extra={"ORC_JOURNAL_DIR": str(env_dir)},
            )
            self.assertEqual(status.returncode, 0, msg=status.stdout + status.stderr)
            self.assertIn("run: flag-run", status.stdout)

    def test_history_resolves_bare_run_id_against_explicit_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            flag_dir = tmp_dir / "flag-journal-dir"
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps(_accepted_config("history-flag-run")), encoding="utf-8")
            dispatch = _run_cli(
                tmp_dir, "dispatch", "history flag fixture", "--config", str(config_path),
                "--journal", str(flag_dir),
            )
            self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)

            history = _run_cli(
                tmp_dir, "history", "history-flag-run", "--journal", str(flag_dir)
            )
            self.assertEqual(history.returncode, 0, msg=history.stdout + history.stderr)
            self.assertIn("FACT-INTENT-SUBMITTED", history.stdout)


class ConfigPersistenceTest(unittest.TestCase):
    """H2 config persistence: dispatch persists the effective config into
    the run dir on first dispatch; a later dispatch may be invoked with
    just the run id (config resolved from the run dir); explicit --config
    still wins and refreshes the persisted copy."""

    def test_first_dispatch_persists_effective_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            journal_dir = tmp_dir / ".orc"
            config = {"run_id": "persist-run", "attempts": {}}
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            result = _run_cli(
                tmp_dir, "dispatch", "persist fixture", "--config", str(config_path),
                "--journal", str(journal_dir),
            )
            self.assertEqual(result.returncode, 3, msg=result.stdout + result.stderr)  # pending

            persisted_path = layout.config_path(journal_dir, "persist-run")
            self.assertTrue(persisted_path.exists())
            self.assertEqual(json.loads(persisted_path.read_text(encoding="utf-8")), config)

    def test_run_id_only_redispatch_resolves_config_from_run_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            journal_dir = tmp_dir / ".orc"
            config = {"run_id": "resume-run", "attempts": {}}
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            first = _run_cli(
                tmp_dir, "dispatch", "resume fixture", "--config", str(config_path),
                "--journal", str(journal_dir), "--run-id", "resume-run",
            )
            self.assertEqual(first.returncode, 3, msg=first.stdout + first.stderr)

            # A ship agent records the settlement by editing the DURABLE
            # in-run-dir config -- never the caller's ephemeral cfg.json.
            persisted_path = layout.config_path(journal_dir, "resume-run")
            persisted = json.loads(persisted_path.read_text(encoding="utf-8"))
            persisted["attempts"] = {
                "work-1": [{"outcome": "completed", "candidate": {"x": 1}, "assurance": {"verdict": "accepted"}}]
            }
            persisted_path.write_text(json.dumps(persisted), encoding="utf-8")

            # Run-id-only re-dispatch: no --config at all.
            second = _run_cli(
                tmp_dir, "dispatch", "resume fixture", "--journal", str(journal_dir),
                "--run-id", "resume-run",
            )
            self.assertEqual(second.returncode, 0, msg=second.stdout + second.stderr)
            self.assertIn("state=ACCEPTED", second.stdout)

    def test_explicit_config_refreshes_persisted_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            journal_dir = tmp_dir / ".orc"
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(
                json.dumps({"run_id": "refresh-run", "max_attempts": 2, "attempts": {}}), encoding="utf-8"
            )
            first = _run_cli(
                tmp_dir, "dispatch", "refresh fixture", "--config", str(config_path),
                "--journal", str(journal_dir), "--run-id", "refresh-run",
            )
            self.assertEqual(first.returncode, 3, msg=first.stdout + first.stderr)

            config_path.write_text(
                json.dumps({"run_id": "refresh-run", "max_attempts": 5, "attempts": {}}), encoding="utf-8"
            )
            second = _run_cli(
                tmp_dir, "dispatch", "refresh fixture", "--config", str(config_path),
                "--journal", str(journal_dir), "--run-id", "refresh-run",
            )
            self.assertEqual(second.returncode, 3, msg=second.stdout + second.stderr)

            persisted = json.loads(layout.config_path(journal_dir, "refresh-run").read_text(encoding="utf-8"))
            self.assertEqual(persisted["max_attempts"], 5)

    def test_next_block_references_durable_config_path_not_ephemeral(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            journal_dir = tmp_dir / ".orc"
            ephemeral_dir = tmp_dir / "ephemeral-scratchpad"
            ephemeral_dir.mkdir()
            config_path = ephemeral_dir / "cfg.json"
            config_path.write_text(
                json.dumps({"run_id": "durable-affordance", "attempts": {}}), encoding="utf-8"
            )
            result = _run_cli(
                tmp_dir, "dispatch", "durable affordance fixture", "--config", str(config_path),
                "--journal", str(journal_dir),
            )
            self.assertEqual(result.returncode, 3, msg=result.stdout + result.stderr)
            self.assertNotIn(str(config_path), result.stdout)
            durable = layout.config_path(journal_dir, "durable-affordance").resolve()
            self.assertIn(str(durable), result.stdout)


class _FakeTTY(io.StringIO):
    def isatty(self) -> bool:  # noqa: D102
        return True


class OSC8HyperlinkUnitTest(unittest.TestCase):
    """Direct unit coverage of `orc_werk.cli.hyperlink.hyperlink_path`."""

    def test_non_tty_returns_byte_identical_plain_path(self) -> None:
        path = Path("/abs/journal.jsonl")
        with contextlib.redirect_stdout(io.StringIO()):
            result = hyperlink_path(path)
        self.assertEqual(result, str(path))
        self.assertNotIn("\x1b", result)  # the load-bearing negative assertion

    def test_tty_wraps_in_osc8_with_plain_path_as_display_text(self) -> None:
        path = Path("/abs/journal.jsonl")
        with contextlib.redirect_stdout(_FakeTTY()):
            result = hyperlink_path(path)
        self.assertNotEqual(result, str(path))
        self.assertTrue(result.startswith("\x1b]8;;file://"))
        self.assertTrue(result.endswith(str(path) + "\x1b]8;;\x1b\\"))
        self.assertIn(str(path), result)


class OSC8CliIntegrationTest(unittest.TestCase):
    """Drives `orc_werk.cli.main.main()` in-process (not subprocess) so
    stdout can be swapped for a TTY-like stream to exercise the positive
    (wrapped) branch -- a subprocess's piped stdout is never a TTY, so
    subprocess-driven tests elsewhere in this file are themselves the
    non-TTY byte-identical fixture for `journal:`/`report:`/index lines."""

    def test_dispatch_journal_line_non_tty_has_zero_escape_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            journal_dir = tmp_dir / ".orc"
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps(_accepted_config("osc8-plain")), encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                exit_code = run_cli_main(
                    ["dispatch", "osc8 fixture", "--config", str(config_path), "--journal", str(journal_dir)]
                )
            self.assertEqual(exit_code, 0)
            output = buf.getvalue()
            self.assertNotIn("\x1b", output)
            expected = str(layout.journal_path(journal_dir, "osc8-plain").resolve())
            self.assertIn(f"journal: {expected}\n", output)

    def test_dispatch_journal_line_tty_is_osc8_wrapped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            journal_dir = tmp_dir / ".orc"
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps(_accepted_config("osc8-tty")), encoding="utf-8")
            buf = _FakeTTY()
            with contextlib.redirect_stdout(buf):
                exit_code = run_cli_main(
                    ["dispatch", "osc8 fixture", "--config", str(config_path), "--journal", str(journal_dir)]
                )
            self.assertEqual(exit_code, 0)
            output = buf.getvalue()
            expected_path = str(layout.journal_path(journal_dir, "osc8-tty").resolve())
            self.assertIn("\x1b]8;;file://", output)
            self.assertIn(expected_path, output)
            self.assertNotIn(f"journal: {expected_path}\n", output)

    def test_report_and_index_lines_are_also_tty_gated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            journal_dir = tmp_dir / ".orc"
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps(_accepted_config("osc8-report")), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                dispatch_exit = run_cli_main(
                    ["dispatch", "osc8 report fixture", "--config", str(config_path),
                     "--journal", str(journal_dir)]
                )
            self.assertEqual(dispatch_exit, 0)

            plain_buf = io.StringIO()
            with contextlib.redirect_stdout(plain_buf):
                report_exit = run_cli_main(["report", "osc8-report", "--journal", str(journal_dir)])
            self.assertEqual(report_exit, 0)
            self.assertNotIn("\x1b", plain_buf.getvalue())

            tty_buf = _FakeTTY()
            with contextlib.redirect_stdout(tty_buf):
                index_exit = run_cli_main(["report", "--index", "--journal", str(journal_dir)])
            self.assertEqual(index_exit, 0)
            self.assertIn("\x1b]8;;file://", tty_buf.getvalue())


if __name__ == "__main__":
    unittest.main()
