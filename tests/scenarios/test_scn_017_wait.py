"""SCN-017 -- blocking wait for the next resting point
(`docs/scenarios/SCN-017-wait-resting-point.md`, `TASK-M-210`, issue #210).

CLI-level scenario test, mirroring `test_scn_007_pending.py`'s
`CliPendingModeTest` structure and `_run_cli` subprocess harness (real
`orc` CLI, JSONL journal, config edited between/around invocations). The
wait mode adds no kernel semantics (SCN-017 Purpose): every assertion here
is CLI-observable exit code, stdout, and journal content only.

- `WaitWakesOnMovementTest` -- Then steps 1-4: an internal wait pass that
  observes no settlement is silent (nothing printed); a settlement
  recorded mid-wait (a background thread edits the run's config file,
  exploiting the per-pass config re-read, `SCN-017` Purpose paragraph 3)
  wakes the wait at a later internal pass, exits `3`, and reports the new
  resting state (`awaiting=assurance-verdict`).
- `WaitTerminalTest` -- Then step 6: a fully-scripted config resolves to
  `ACCEPTED` within the first internal pass; `--wait` exits `0` exactly
  like a non-`--wait` dispatch of the same config would.
- `WaitTimeoutTest` -- Then step 8: `--timeout` elapses with the pending
  fingerprint unchanged; exits the distinct wait-timeout code `4`, and the
  journal produced is record-for-record identical to a single non-`--wait`
  dispatch of the same starting state -- N idle internal passes journal
  nothing (`INV-018`, `INV-020`).
- `TimeoutRequiresWaitTest` -- Then step 9: `--timeout` without `--wait`
  is `ERR-VALIDATION`, exit `2`.
- `WaitJournalIdentityTest` -- Then step 13: the journal produced by a
  chain of `--wait` invocations spanning the `SCN-007` pending(EXECUTING)
  -> pending(ASSURING) -> `ACCEPTED` boundary chain is record-for-record
  identical to the same chain of invocations run without `--wait`.

Verifies `SCN-017` (steps 1, 4, 6, 8, 9, 13); inherits `SCN-007` pending
semantics per its own "Verifies" section (`INV-018`, `INV-020`).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from orc_werk.adapters.jsonl.journal import JSONLJournal

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


def _run_cli(tmp_dir: Path, *args: str, timeout: float = 15) -> subprocess.CompletedProcess:
    env = {"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"}
    return subprocess.run(
        [sys.executable, "-m", "orc_werk.cli", *args],
        cwd=tmp_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _journal_records(tmp_dir: Path, run_id: str):
    return JSONLJournal(tmp_dir / ".orc").history(delivery_run_id=run_id)


def _atomic_write_text(path: Path, content: str) -> None:
    """Write `content` to `path` via write-temp + `os.replace` (issue #216):
    the same atomicity `record_assurance_entry`
    (`orc_werk.cli.config`, `orc record`'s writer) already uses, so a
    concurrent reader (here, a `--wait` internal pass re-reading the same
    config file, `SCN-017` Purpose paragraph 3) never observes a
    partially-written file. This is the fix for the flake issue #216
    reported: the original delayed-writer thread in
    `WaitWakesOnMovementTest` used a direct, non-atomic `write_text`, which
    could race a `--wait` pass's read and hand it a torn/incomplete JSON
    document -- an `ERR-VALIDATION` indistinguishable, before this task,
    from a genuinely bad config."""
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


class WaitWakesOnMovementTest(unittest.TestCase):
    """SCN-017 Then steps 1-4: silence while nothing has settled, wake on
    the pass that observes a settlement recorded mid-wait."""

    def test_wait_exits_3_when_settlement_recorded_mid_wait(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config_path = tmp_dir / "config.json"
            config_path.write_text(
                json.dumps({"run_id": "scn017-wake", "max_attempts": 3}), encoding="utf-8"
            )

            # SCN-017's Given: "Work A is pending exactly as at the end of
            # SCN-007 invocation 1" -- the run already rests at EXECUTING,
            # awaiting execution-outcome, BEFORE the --wait invocation
            # begins. A brand-new run's baseline is empty (Purpose
            # paragraph 4), so if --wait itself created the run, its own
            # first pass would already move the fingerprint from empty
            # and return immediately -- an ordinary non-wait dispatch
            # establishes the Given pending state first, exactly like this
            # module's other tests build on SCN-007's own invocation 1.
            setup = _run_cli(tmp_dir, "dispatch", "scn017 wake", "--config", str(config_path))
            self.assertEqual(setup.returncode, 3, msg=setup.stdout + setup.stderr)
            self.assertIn("awaiting=execution-outcome", setup.stdout)

            def _record_settlement_after_delay() -> None:
                # Give the wait loop a couple of idle (empty) internal
                # passes before the settlement lands, so this test also
                # exercises step 1's silent-pass behavior, not just an
                # immediate first-pass wake. Issue #216: this write must be
                # atomic (write-temp + os.replace, `_atomic_write_text`)
                # -- a direct write_text here previously raced a --wait
                # pass's own config re-read and flaked the test with a
                # torn-JSON ERR-VALIDATION.
                time.sleep(0.2)
                _atomic_write_text(
                    config_path,
                    json.dumps(
                        {
                            "run_id": "scn017-wake",
                            "max_attempts": 3,
                            "attempts": {"work-1": [{"outcome": "completed", "candidate": {"label": "C1"}}]},
                        }
                    ),
                )

            recorder = threading.Thread(target=_record_settlement_after_delay)
            recorder.start()
            result = _run_cli(
                tmp_dir,
                "dispatch",
                "scn017 wake",
                "--config",
                str(config_path),
                "--wait",
                "--timeout",
                "5",
                "--poll-interval",
                "0.05",
            )
            recorder.join()

            # Then 4: exit 3 (the existing pending exit code), not 0/1/4.
            self.assertEqual(result.returncode, 3, msg=result.stdout + result.stderr)
            # Then 3-4: the pass that observed the settlement journaled it
            # through the normal observation path and moved the work to
            # ASSURING -- the wait returns reporting the NEW resting state.
            self.assertIn("state=ASSURING", result.stdout)
            self.assertIn("awaiting=assurance-verdict", result.stdout)
            self.assertNotIn("wait timeout", result.stdout)

            # Then 3: exactly one FACT-EXEC-STARTED/FACT-EXEC-SETTLED --
            # waiting fabricated nothing and did not re-dispatch the
            # already-recorded start (INV-020).
            history = _journal_records(tmp_dir, "scn017-wake")
            fact_ids = [r["id"] for r in history if r["kind"] == "fact"]
            self.assertEqual(fact_ids.count("FACT-EXEC-STARTED"), 1)
            self.assertEqual(fact_ids.count("FACT-EXEC-SETTLED"), 1)
            self.assertEqual(fact_ids.count("FACT-CANDIDATE-OBSERVED"), 1)
            self.assertNotIn("FACT-ASSURE-SETTLED", fact_ids)


class WaitTransientConfigTest(unittest.TestCase):
    """SCN-017 amendment (issue #216): a `--wait` pass whose config
    load/validate fails transiently (unparseable JSON) is tolerated up to
    `TRANSIENT_CONFIG_RETRY_LIMIT` (3) CONSECUTIVE failures within one
    invocation, but a failure on the invocation's very first pass fails
    fast, exactly as before this task."""

    def _setup_pending(self, tmp_dir: Path, config_path: Path, run_id: str) -> None:
        config_path.write_text(json.dumps({"run_id": run_id, "max_attempts": 3}), encoding="utf-8")
        # Same Given-establishing pattern as WaitWakesOnMovementTest: an
        # ordinary (non-wait) dispatch first reaches the pending/EXECUTING
        # resting state, so the --wait invocation's baseline is that
        # already-settled fingerprint rather than an empty one.
        setup = _run_cli(tmp_dir, "dispatch", "scn017 transient", "--config", str(config_path), "--run-id", run_id)
        self.assertEqual(setup.returncode, 3, msg=setup.stdout + setup.stderr)
        self.assertIn("awaiting=execution-outcome", setup.stdout)

    def test_wait_survives_one_or_two_garbage_config_passes_then_wakes(self) -> None:
        """A brief window of unparseable JSON, landing after the wait's
        first (successful) pass and cleared well within the
        3-consecutive-failure cap, does not fail the wait -- it retries
        and wakes normally once a valid settlement lands (the transient
        case of the amendment). The poll interval is deliberately larger
        than the garbage window here (and the garbage/fix writes are
        cheap, local filesystem ops) so that, even under CI scheduling
        jitter, at most one or two internal passes can plausibly land
        inside the window -- comfortably under the 3-consecutive cap that
        would fail the wait instead."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config_path = tmp_dir / "config.json"
            run_id = "scn017-transient-recovers"
            self._setup_pending(tmp_dir, config_path, run_id)

            def _garbage_then_recover() -> None:
                # Let at least one internal pass complete successfully
                # first (baseline set) before corrupting the config for a
                # window well short of one poll interval.
                time.sleep(0.4)
                config_path.write_text("{not valid json", encoding="utf-8")
                time.sleep(0.1)
                _atomic_write_text(
                    config_path,
                    json.dumps(
                        {
                            "run_id": run_id,
                            "max_attempts": 3,
                            "attempts": {"work-1": [{"outcome": "completed", "candidate": {"label": "C1"}}]},
                        }
                    ),
                )

            writer = threading.Thread(target=_garbage_then_recover)
            writer.start()
            result = _run_cli(
                tmp_dir,
                "dispatch",
                "scn017 transient",
                "--config",
                str(config_path),
                "--run-id",
                run_id,
                "--wait",
                "--timeout",
                "5",
                "--poll-interval",
                "0.25",
            )
            writer.join()

            # The wait survived the garbage passes and woke on the
            # eventual valid settlement -- exit 3 (movement), never exit 2
            # (the canonical config error the pre-#216 behavior would have
            # produced for the same garbage window).
            self.assertEqual(result.returncode, 3, msg=result.stdout + result.stderr)
            self.assertIn("state=ASSURING", result.stdout)
            self.assertIn("awaiting=assurance-verdict", result.stdout)
            self.assertNotIn("wait timeout", result.stdout)

            # A skipped transient-failure pass is silent per the amendment
            # (step 1's silence extended): nothing about the garbage
            # window is journaled, so the settled facts still appear
            # exactly once.
            history = _journal_records(tmp_dir, run_id)
            fact_ids = [r["id"] for r in history if r["kind"] == "fact"]
            self.assertEqual(fact_ids.count("FACT-EXEC-SETTLED"), 1)
            self.assertEqual(fact_ids.count("FACT-CANDIDATE-OBSERVED"), 1)

    def test_wait_fails_after_3_consecutive_bad_passes(self) -> None:
        """A config that goes bad mid-wait and never recovers exhausts the
        3-consecutive-failure cap and fails with the ordinary canonical
        error -- well before --timeout elapses, proving the cap (not the
        timeout) ended the wait."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config_path = tmp_dir / "config.json"
            run_id = "scn017-transient-caps"
            self._setup_pending(tmp_dir, config_path, run_id)

            def _corrupt_permanently() -> None:
                # One successful pass first (baseline set), then garbage
                # that is never fixed -- every subsequent pass fails,
                # tripping the 3-consecutive cap.
                time.sleep(0.1)
                config_path.write_text("{not valid json", encoding="utf-8")

            writer = threading.Thread(target=_corrupt_permanently)
            writer.start()
            started = time.monotonic()
            result = _run_cli(
                tmp_dir,
                "dispatch",
                "scn017 transient",
                "--config",
                str(config_path),
                "--run-id",
                run_id,
                "--wait",
                "--timeout",
                "10",
                "--poll-interval",
                "0.05",
            )
            elapsed = time.monotonic() - started
            writer.join()

            # The ordinary canonical error, exit 2 -- identical to what a
            # non-`--wait` dispatch of this same bad config would report.
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-VALIDATION")

            # Cross-check against the ordinary (non-wait) failure this bad
            # config produces on its own (issue #216 ruling: "fail with
            # the ordinary canonical error exactly as today"): the COMPLETE
            # stderr byte stream, the complete stdout byte stream, and the
            # exit code must all be identical, with NO normalization --
            # any drift in the error surface (a changed message, an added/
            # dropped detail or next-step, reordered keys, a stray extra
            # line) fails this comparison. No segment of either stream is
            # nondeterministic across the two invocations: the canonical
            # error is printed by `_print_error` as
            # `json.dumps(error, sort_keys=True)` (stable key order, no
            # timestamps/PIDs/tracebacks -- CONTRACT-ERRORS' portable
            # shape), and its only environment-derived content is the
            # absolute config path, which is the SAME file in both
            # invocations here. stdout is byte-identical too (empty:
            # config load fails before any dispatch output in the plain
            # case, and every earlier internal wait pass's captured
            # output is discarded per step 1's silence).
            plain = _run_cli(
                tmp_dir, "dispatch", "scn017 transient", "--config", str(config_path), "--run-id", run_id
            )
            self.assertEqual(plain.returncode, result.returncode)
            self.assertEqual(plain.stderr, result.stderr)
            self.assertEqual(plain.stdout, result.stdout)
            self.assertEqual(result.stdout, "")

            # The cap, not the 10s --timeout, ended the wait: 3 consecutive
            # 0.05s-apart passes is on the order of tenths of a second, not
            # anywhere near 10s.
            self.assertLess(elapsed, 5.0)

    def test_wait_first_pass_bad_config_fails_fast(self) -> None:
        """A config that is already bad when `--wait` is invoked -- before
        this invocation has completed any pass -- fails immediately, never
        retried: it is a real config error at wait start, not a race
        (issue #216 ruling)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config_path = tmp_dir / "config.json"
            run_id = "scn017-transient-first-pass"
            self._setup_pending(tmp_dir, config_path, run_id)

            # Corrupt the config BEFORE --wait is ever invoked -- its very
            # first internal pass sees the bad config.
            config_path.write_text("{not valid json", encoding="utf-8")

            # A poll interval long enough that any retry (even a single
            # one) would make the call take noticeably longer than an
            # immediate failure -- the timing margin that distinguishes
            # "failed fast" from "retried once, then failed".
            started = time.monotonic()
            result = _run_cli(
                tmp_dir,
                "dispatch",
                "scn017 transient",
                "--config",
                str(config_path),
                "--run-id",
                run_id,
                "--wait",
                "--timeout",
                "30",
                "--poll-interval",
                "3",
            )
            elapsed = time.monotonic() - started

            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-VALIDATION")
            # No retry/sleep happened -- well under one 3s poll interval.
            self.assertLess(elapsed, 2.0)


class WaitTerminalTest(unittest.TestCase):
    """SCN-017 Then step 6: the run reaching a terminal state during the
    wait returns exit 0/1 with output identical to a non-`--wait`
    dispatch observing the same journal."""

    def test_wait_exits_0_when_fully_scripted_run_completes_on_first_pass(self) -> None:
        config = {
            "run_id": "scn017-terminal",
            "attempts": {
                "work-1": [
                    {"outcome": "completed", "candidate": {"label": "C1"}, "assurance": {"verdict": "accepted"}}
                ]
            },
        }

        with tempfile.TemporaryDirectory() as wait_tmp:
            wait_dir = Path(wait_tmp)
            wait_config = wait_dir / "config.json"
            wait_config.write_text(json.dumps(config), encoding="utf-8")
            wait_result = _run_cli(
                wait_dir,
                "dispatch",
                "scn017 terminal",
                "--config",
                str(wait_config),
                "--wait",
                "--timeout",
                "5",
                "--poll-interval",
                "0.05",
            )

        with tempfile.TemporaryDirectory() as plain_tmp:
            plain_dir = Path(plain_tmp)
            plain_config = plain_dir / "config.json"
            plain_config.write_text(json.dumps(config), encoding="utf-8")
            plain_result = _run_cli(plain_dir, "dispatch", "scn017 terminal", "--config", str(plain_config))

        self.assertEqual(wait_result.returncode, 0, msg=wait_result.stdout + wait_result.stderr)
        self.assertEqual(plain_result.returncode, 0, msg=plain_result.stdout + plain_result.stderr)
        self.assertIn("state=ACCEPTED", wait_result.stdout)
        # Identical output to the non-wait dispatch of the same config
        # (Then 6) -- run id/journal path differ only by tmp dir, so
        # compare the work/next lines rather than the whole blob.
        wait_lines = [line for line in wait_result.stdout.splitlines() if line.startswith("work ")]
        plain_lines = [line for line in plain_result.stdout.splitlines() if line.startswith("work ")]
        self.assertEqual(wait_lines, plain_lines)


class WaitTimeoutTest(unittest.TestCase):
    """SCN-017 Then step 8: --timeout elapses with the fingerprint
    unchanged -- distinct wait-timeout exit code 4, journal untouched by
    the waiting itself (record-for-record identical to a single ordinary
    pending dispatch)."""

    def test_wait_timeout_exits_4_and_journal_matches_single_pending_dispatch(self) -> None:
        config = {"run_id": "scn017-timeout", "max_attempts": 3}

        with tempfile.TemporaryDirectory() as wait_tmp:
            wait_dir = Path(wait_tmp)
            wait_config = wait_dir / "config.json"
            wait_config.write_text(json.dumps(config), encoding="utf-8")
            # SCN-017's Given (see WaitWakesOnMovementTest's comment):
            # establish the pending-EXECUTING resting state with an
            # ordinary dispatch BEFORE the --wait invocation, so --wait's
            # own baseline is that already-settled fingerprint, not an
            # empty one that would move (and return 3) on first pass.
            setup = _run_cli(wait_dir, "dispatch", "scn017 timeout", "--config", str(wait_config))
            self.assertEqual(setup.returncode, 3, msg=setup.stdout + setup.stderr)
            wait_result = _run_cli(
                wait_dir,
                "dispatch",
                "scn017 timeout",
                "--config",
                str(wait_config),
                "--wait",
                "--timeout",
                "0.3",
                "--poll-interval",
                "0.05",
            )
            wait_history = _journal_records(wait_dir, "scn017-timeout")

        with tempfile.TemporaryDirectory() as plain_tmp:
            plain_dir = Path(plain_tmp)
            plain_config = plain_dir / "config.json"
            plain_config.write_text(json.dumps(config), encoding="utf-8")
            # The equivalent single ordinary (non-wait) pending dispatch
            # -- same starting config, one pass, no --wait involved.
            plain_result = _run_cli(plain_dir, "dispatch", "scn017 timeout", "--config", str(plain_config))
            plain_history = _journal_records(plain_dir, "scn017-timeout")

        # Then 8: distinct wait-timeout code, colliding with none of 0/1/2/3.
        self.assertEqual(wait_result.returncode, 4, msg=wait_result.stdout + wait_result.stderr)
        self.assertEqual(plain_result.returncode, 3, msg=plain_result.stdout + plain_result.stderr)
        self.assertNotIn(wait_result.returncode, (0, 1, 2, 3))
        self.assertIn("wait timeout", wait_result.stdout)
        self.assertIn("0.3", wait_result.stdout)

        # Then 8: "journals nothing beyond what its ordinary passes
        # journaled" -- an arbitrary number of empty internal passes (at
        # ~0.05s apart over 0.3s, several ran) on top of the one setup
        # pass produced a journal identical, record for record, to the
        # single ordinary pass alone.
        self.assertEqual(len(wait_history), len(plain_history))
        for wait_record, plain_record in zip(wait_history, plain_history):
            self.assertEqual(wait_record, plain_record)


class TimeoutRequiresWaitTest(unittest.TestCase):
    """SCN-017 Then step 9: --timeout without --wait is ERR-VALIDATION."""

    def test_timeout_without_wait_is_err_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config_path = tmp_dir / "config.json"
            config_path.write_text(json.dumps({}), encoding="utf-8")
            result = _run_cli(
                tmp_dir, "dispatch", "scn017 no-wait-timeout", "--config", str(config_path), "--timeout", "5"
            )
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-VALIDATION")
            self.assertTrue(error.get("next"))

    def test_abandon_work_with_wait_is_err_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config_path = tmp_dir / "config.json"
            config_path.write_text(json.dumps({}), encoding="utf-8")
            result = _run_cli(
                tmp_dir,
                "dispatch",
                "scn017 abandon-wait",
                "--config",
                str(config_path),
                "--run-id",
                "scn017-abandon-wait",
                "--wait",
                "--abandon-work",
                "work-1",
                "--abandon-reason",
                "x",
            )
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-VALIDATION")
            self.assertTrue(error.get("next"))


class WaitJournalIdentityTest(unittest.TestCase):
    """SCN-017 Then step 13: N internal passes across a chain of --wait
    invocations produce a journal record-for-record identical to the
    equivalent chain of manual (non-wait) re-dispatches -- waiting is
    invisible to the journal's shape."""

    RUN_ID = "scn017-identity"

    def _write_configs(self, config_path: Path) -> tuple[dict, dict, dict]:
        pending = {"run_id": self.RUN_ID, "max_attempts": 3}
        settled = {
            "run_id": self.RUN_ID,
            "max_attempts": 3,
            "attempts": {"work-1": [{"outcome": "completed", "candidate": {"label": "C1"}}]},
        }
        accepted = {
            "run_id": self.RUN_ID,
            "max_attempts": 3,
            "attempts": {
                "work-1": [
                    {"outcome": "completed", "candidate": {"label": "C1"}, "assurance": {"verdict": "accepted"}}
                ]
            },
        }
        return pending, settled, accepted

    def test_wait_chain_journal_matches_manual_chain(self) -> None:
        with tempfile.TemporaryDirectory() as manual_tmp, tempfile.TemporaryDirectory() as wait_tmp:
            manual_dir = Path(manual_tmp)
            wait_dir = Path(wait_tmp)
            manual_config = manual_dir / "config.json"
            wait_config = wait_dir / "config.json"
            pending, settled, accepted = self._write_configs(manual_config)

            # -- Manual chain: three ordinary (non-wait) dispatches,
            # exactly SCN-007's CliPendingModeTest pattern.
            manual_config.write_text(json.dumps(pending), encoding="utf-8")
            manual1 = _run_cli(manual_dir, "dispatch", "scn017 chain", "--config", str(manual_config))
            self.assertEqual(manual1.returncode, 3, msg=manual1.stdout + manual1.stderr)

            manual_config.write_text(json.dumps(settled), encoding="utf-8")
            manual2 = _run_cli(manual_dir, "dispatch", "scn017 chain", "--config", str(manual_config))
            self.assertEqual(manual2.returncode, 3, msg=manual2.stdout + manual2.stderr)

            manual_config.write_text(json.dumps(accepted), encoding="utf-8")
            manual3 = _run_cli(manual_dir, "dispatch", "scn017 chain", "--config", str(manual_config))
            self.assertEqual(manual3.returncode, 0, msg=manual3.stdout + manual3.stderr)

            # -- Wait chain: same run id/intent/config content and
            # sequence, but every invocation carries --wait. Each config
            # edit lands before its --wait call, so (per Purpose
            # paragraph 4) that call's own first internal pass already
            # observes the news and returns immediately -- still a real
            # exercise of the --wait code path (_dispatch_wait), and the
            # --wait/--timeout/--poll-interval flags themselves must never
            # leak into journaled data.
            wait_config.write_text(json.dumps(pending), encoding="utf-8")
            wait1 = _run_cli(
                wait_dir,
                "dispatch",
                "scn017 chain",
                "--config",
                str(wait_config),
                "--wait",
                "--timeout",
                "5",
                "--poll-interval",
                "0.05",
            )
            self.assertEqual(wait1.returncode, 3, msg=wait1.stdout + wait1.stderr)

            wait_config.write_text(json.dumps(settled), encoding="utf-8")
            wait2 = _run_cli(
                wait_dir,
                "dispatch",
                "scn017 chain",
                "--config",
                str(wait_config),
                "--wait",
                "--timeout",
                "5",
                "--poll-interval",
                "0.05",
            )
            self.assertEqual(wait2.returncode, 3, msg=wait2.stdout + wait2.stderr)

            wait_config.write_text(json.dumps(accepted), encoding="utf-8")
            wait3 = _run_cli(
                wait_dir,
                "dispatch",
                "scn017 chain",
                "--config",
                str(wait_config),
                "--wait",
                "--timeout",
                "5",
                "--poll-interval",
                "0.05",
            )
            self.assertEqual(wait3.returncode, 0, msg=wait3.stdout + wait3.stderr)

            manual_history = _journal_records(manual_dir, self.RUN_ID)
            wait_history = _journal_records(wait_dir, self.RUN_ID)

            self.assertEqual(len(manual_history), len(wait_history))
            for manual_record, wait_record in zip(manual_history, wait_history):
                self.assertEqual(manual_record, wait_record)


if __name__ == "__main__":
    unittest.main()
