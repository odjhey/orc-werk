"""SCN-018 -- observer hooks: config-declared push notifications fired on
journaled facts (`docs/scenarios/SCN-018-observer-hooks.md`, issue #193).

CLI-level scenario test, mirroring `test_scn_017_wait.py`'s subprocess
`_run_cli` harness (real `orc` CLI, JSONL journal). Every dispatch here uses
a fully-scripted config (`execution`/`candidate`/`assurance` all default
`"scripted"`) so a single pass settles execution AND assurance in one go --
no real git/command adapters needed, keeping the suite fast.

- `ObserverEnvelopeTest` -- Then steps 1-2, 7: the full journaled fact
  envelope (kind/id/data/seq) arrives as JSON on the observer's stdin.
- `ObserverReplaySafetyTest` -- Then steps 13-15: an immediate re-dispatch
  of an already-settled run fires nothing (at-most-once, no re-fire on
  replay).
- `ObserverSeqOrderUnitTest` -- Then step 6: `fire_observers` spawns in
  the given `new_records`' own order (already seq order), never reordered
  by trigger key -- a pure-Python unit test of the firing function with
  `subprocess.Popen` mocked out, independent of OS-scheduler timing.
- `ObserverContainmentTest` -- Containment section: a `command[0]`
  resolving outside cwd is `ERR-VALIDATION` at config-load time, before any
  journal write (no `.orc` directory is ever created).
- `ObserverHungObserverTest` -- step 12: a hung observer is killed --
  process group and all -- by its own delegated supervision once
  `timeout_seconds` elapses, while dispatch itself already returned.
- `ObserverFailingExitTest` -- step 10: an observer that exits 1 leaves
  dispatch's own exit code/stdout identical to an otherwise-identical
  dispatch with no `observers` key at all.
- `ObserverMissingScriptTest` -- step 11: a missing/non-executable script
  is a single stderr warning; the run is otherwise unaffected.

Verifies `SCN-018` (steps 1-15), `SCN-015` (containment reuse), `SCN-017`
(the `--wait`-interaction ruling documented in `_dispatch_pass`, exercised
indirectly here since firing is pass-scoped regardless of `--wait`).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from orc_werk.cli.observers import fire_observers
from orc_werk.core.facts import FACT_ASSURE_SETTLED, FACT_EXEC_SETTLED

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


def _run_cli(cwd: Path, *args: str, timeout: float = 15) -> subprocess.CompletedProcess:
    env = {"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"}
    return subprocess.run(
        [sys.executable, "-m", "orc_werk.cli", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _poll_until(predicate, *, timeout: float = 1.5, interval: float = 0.03) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


_SETTLED_CONFIG = {
    "attempts": {
        "work-1": [
            {"outcome": "completed", "candidate": {"label": "A"}, "assurance": {"verdict": "accepted"}}
        ]
    }
}


class ObserverEnvelopeTest(unittest.TestCase):
    """Then steps 1-2, 7: full fact envelope, JSON on stdin."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        capture = self.root / "capture.py"
        capture.write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "data = sys.stdin.buffer.read()\n"
            "open(sys.argv[1], 'wb').write(data)\n"
        )
        capture.chmod(0o755)

    def test_full_envelope_on_stdin_for_settle_and_verdict(self) -> None:
        config = {
            **_SETTLED_CONFIG,
            "observers": {
                "on_settle": {"command": ["./capture.py", "settle.json"]},
                "on_verdict": {"command": ["./capture.py", "verdict.json"]},
            },
        }
        (self.root / "config.json").write_text(json.dumps(config))
        result = _run_cli(
            self.root, "dispatch", "envelope smoke", "--config", "config.json",
            "--journal", ".orc", "--run-id", "envelope1",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        settle_path = self.root / "settle.json"
        verdict_path = self.root / "verdict.json"
        self.assertTrue(_poll_until(lambda: settle_path.exists() and verdict_path.exists()))

        settle = json.loads(settle_path.read_text())
        self.assertEqual(settle["kind"], "fact")
        self.assertEqual(settle["id"], "FACT-EXEC-SETTLED")
        self.assertIsInstance(settle["seq"], int)
        self.assertEqual(settle["data"]["work_id"], "work-1")
        self.assertEqual(settle["data"]["outcome"], "completed")

        verdict = json.loads(verdict_path.read_text())
        self.assertEqual(verdict["kind"], "fact")
        self.assertEqual(verdict["id"], "FACT-ASSURE-SETTLED")
        self.assertIsInstance(verdict["seq"], int)
        self.assertEqual(verdict["data"]["work_id"], "work-1")
        self.assertEqual(verdict["data"]["verdict"], "accepted")
        self.assertGreater(verdict["seq"], settle["seq"])


class ObserverReplaySafetyTest(unittest.TestCase):
    """Then steps 13-15: at-most-once; a redispatch of a settled run fires
    nothing, because replayed history is never a newly-appended fact."""

    def test_redispatch_of_settled_run_fires_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            counter = root / "capture.sh"
            counter.write_text('#!/bin/sh\nprintf "x" >> "%s/count.txt"\n' % root)
            counter.chmod(0o755)
            config = {**_SETTLED_CONFIG, "observers": {"on_settle": {"command": ["./capture.sh"]}}}
            (root / "config.json").write_text(json.dumps(config))

            first = _run_cli(root, "dispatch", "replay smoke", "--config", "config.json",
                              "--journal", ".orc", "--run-id", "replay1")
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            count_path = root / "count.txt"
            self.assertTrue(_poll_until(lambda: count_path.exists() and count_path.read_text() == "x"))

            second = _run_cli(root, "dispatch", "--run-id", "replay1", "--config", "config.json",
                               "--journal", ".orc")
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            time.sleep(0.3)  # bounded window to catch an incorrect re-fire, not an expected async op
            self.assertEqual(count_path.read_text(), "x", "redispatch of a settled run must fire nothing")


class ObserverSeqOrderUnitTest(unittest.TestCase):
    """Then step 6: observers fire in the triggering facts' own seq order,
    regardless of trigger-key iteration order -- a pure unit test of
    `fire_observers` with `subprocess.Popen` mocked so ordering is asserted
    on the Python-level call sequence, not OS-scheduler completion timing
    (SCN-018 step 6 explicitly makes no promise about the latter)."""

    def test_fires_in_new_records_seq_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("settle.sh", "verdict.sh"):
                script = root / name
                script.write_text("#!/bin/sh\n")
                script.chmod(0o755)

            observers_cfg = {
                "on_settle": {"command": ["./settle.sh"]},
                "on_verdict": {"command": ["./verdict.sh"]},
            }
            new_records = [
                {"kind": "fact", "id": FACT_EXEC_SETTLED, "seq": 5, "data": {}},
                {"kind": "fact", "id": FACT_ASSURE_SETTLED, "seq": 6, "data": {}},
            ]

            class _FakeStdin:
                def __init__(self) -> None:
                    self.written = b""

                def write(self, data: bytes) -> None:
                    self.written += data

                def close(self) -> None:
                    pass

            class _FakeProc:
                def __init__(self, argv: list[str]) -> None:
                    self.argv = argv
                    self.stdin = _FakeStdin()

            calls: list[_FakeProc] = []

            def fake_popen(argv, **kwargs):
                proc = _FakeProc(argv)
                calls.append(proc)
                return proc

            with mock.patch("orc_werk.cli.observers.subprocess.Popen", side_effect=fake_popen):
                fire_observers(observers_cfg, new_records=new_records, cwd=root)

            self.assertEqual(len(calls), 2)
            self.assertTrue(calls[0].argv[-1].endswith("settle.sh"), calls[0].argv)
            self.assertTrue(calls[1].argv[-1].endswith("verdict.sh"), calls[1].argv)
            self.assertEqual(json.loads(calls[0].stdin.written)["seq"], 5)
            self.assertEqual(json.loads(calls[1].stdin.written)["seq"], 6)


class ObserverContainmentTest(unittest.TestCase):
    """Containment section: an escaping command[0] is ERR-VALIDATION at
    config-load time, before any journal write."""

    def test_escaping_command_rejected_before_journal_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inside = root / "inside"
            inside.mkdir()
            (root / "outside.sh").write_text("#!/bin/sh\nexit 0\n")
            (root / "outside.sh").chmod(0o755)
            config = {
                **_SETTLED_CONFIG,
                "observers": {"on_settle": {"command": ["../outside.sh"]}},
            }
            (inside / "config.json").write_text(json.dumps(config))

            result = _run_cli(inside, "dispatch", "containment", "--config", "config.json",
                               "--journal", ".orc", "--run-id", "contain1")
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("ERR-VALIDATION", result.stdout + result.stderr)
            self.assertFalse((inside / ".orc").exists(), "config rejection must precede any journal write")


class ObserverHungObserverTest(unittest.TestCase):
    """Step 12: bounded lifetime by delegated supervision -- a hung
    observer's whole (own, separate) process group is killed and REAPED by
    the surviving supervisor once `timeout_seconds` elapses, without
    dispatch itself ever waiting for it.

    Kill-topology probes (PR #225 attempt-2 verify finding): the observer
    runs in its own session/process group, separate from the supervisor's,
    so the post-timeout FINAL state is deterministic: both probes below
    must reach ESRCH (gone) within the deadline. EPERM from `killpg` is
    tolerated only as a TRANSIENT in-progress signal: on darwin,
    `killpg(pgid, 0)` against a group whose sole member is a zombie
    (SIGKILL delivered, supervisor's reap still pending) returns EPERM --
    an empirically confirmed macOS kernel artifact of probing a zombie
    group, not a reused/mixed-state pgid. PERSISTENT EPERM past the
    deadline IS the failure (a supervisor that killed but never reaped),
    and the poll's failure message names the stuck state explicitly. The
    separate no-zombie assertion works because a zombie still answers
    `os.kill(pid, 0)`: only a fully reaped observer raises ESRCH."""

    def test_hung_observer_killed_by_its_own_supervision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hang = root / "hang.py"
            hang.write_text(
                "#!/usr/bin/env python3\n"
                "import os, sys, time, json\n"
                "sys.stdin.read()\n"
                "open('pidinfo.json', 'w').write(json.dumps({'pid': os.getpid(), 'pgid': os.getpgid(0)}))\n"
                "time.sleep(60)\n"
            )
            hang.chmod(0o755)
            timeout_seconds = 0.5
            config = {
                **_SETTLED_CONFIG,
                "observers": {"on_settle": {"command": ["./hang.py"], "timeout_seconds": timeout_seconds}},
            }
            (root / "config.json").write_text(json.dumps(config))

            started = time.monotonic()
            result = _run_cli(root, "dispatch", "hang smoke", "--config", "config.json",
                               "--journal", ".orc", "--run-id", "hang1")
            wall = time.monotonic() - started
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertLess(wall, 15.0, "dispatch must not wait for the observer's own hang")

            pidinfo_path = root / "pidinfo.json"
            self.assertTrue(_poll_until(lambda: pidinfo_path.exists(), timeout=8.0))
            info = json.loads(pidinfo_path.read_text())
            # New kill topology: the observer is its own session leader, so
            # its pgid is its own pid -- never the supervisor's group.
            self.assertEqual(info["pid"], info["pgid"],
                              "observer must run as its own session/process-group leader")

            last_group_state = ["unprobed"]

            def _group_gone() -> bool:
                try:
                    os.killpg(info["pgid"], 0)
                    last_group_state[0] = "alive"
                    return False  # group still alive; keep polling
                except ProcessLookupError:
                    last_group_state[0] = "gone (ESRCH)"
                    return True  # ESRCH: gone -- success
                except PermissionError:
                    # darwin zombie-probe artifact (class docstring):
                    # SIGKILL delivered, reap pending. Transiently legal;
                    # persistently, it is the killed-but-never-reaped
                    # failure and the deadline below reports it as such.
                    last_group_state[0] = "zombie awaiting reap (EPERM)"
                    return False

            # Deterministic bound: gone within timeout_seconds + epsilon
            # (epsilon covers supervisor scheduling + kill + reap, generous
            # for a loaded CI machine but still a hard deadline).
            self.assertTrue(
                _poll_until(_group_gone, timeout=timeout_seconds + 6.0),
                "observer's whole process group must be gone after timeout_seconds; "
                f"stuck at: {last_group_state[0]}",
            )

            def _fully_reaped() -> bool:
                try:
                    os.kill(info["pid"], 0)
                    return False  # still exists -- possibly a zombie
                except ProcessLookupError:
                    return True  # ESRCH: reaped, no zombie
                except PermissionError:
                    self.fail("EPERM probing the observer pid: pid reused by another user's process")

            self.assertTrue(
                _poll_until(_fully_reaped, timeout=4.0),
                "observer must be reaped by its supervisor -- no zombie may remain",
            )


class ObserverFailingExitTest(unittest.TestCase):
    """Step 10: an observer's exit status is opaque -- a failing (exit 1)
    observer leaves dispatch's own exit code/stdout identical to the same
    dispatch with no observers configured at all."""

    def test_failing_observer_does_not_affect_run(self) -> None:
        with tempfile.TemporaryDirectory() as with_root, tempfile.TemporaryDirectory() as without_root:
            with_root, without_root = Path(with_root), Path(without_root)
            failing = with_root / "fail.sh"
            failing.write_text("#!/bin/sh\nexit 1\n")
            failing.chmod(0o755)

            with_cfg = {**_SETTLED_CONFIG, "observers": {"on_settle": {"command": ["./fail.sh"]}}}
            without_cfg = dict(_SETTLED_CONFIG)
            (with_root / "config.json").write_text(json.dumps(with_cfg))
            (without_root / "config.json").write_text(json.dumps(without_cfg))

            with_result = _run_cli(with_root, "dispatch", "twin", "--config", "config.json",
                                    "--journal", ".orc", "--run-id", "twin")
            without_result = _run_cli(without_root, "dispatch", "twin", "--config", "config.json",
                                       "--journal", ".orc", "--run-id", "twin")

            self.assertEqual(with_result.returncode, without_result.returncode)

            def _strip_journal_line(text: str) -> str:
                return "\n".join(line for line in text.splitlines() if not line.startswith("journal:"))

            self.assertEqual(_strip_journal_line(with_result.stdout), _strip_journal_line(without_result.stdout))
            self.assertEqual(with_result.stderr, "")


class ObserverMissingScriptTest(unittest.TestCase):
    """Step 11: a missing/non-executable script is a single stderr warning;
    the run is otherwise unaffected."""

    def test_missing_script_warns_once_run_unaffected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {**_SETTLED_CONFIG, "observers": {"on_settle": {"command": ["./does-not-exist.sh"]}}}
            (root / "config.json").write_text(json.dumps(config))

            result = _run_cli(root, "dispatch", "missing smoke", "--config", "config.json",
                               "--journal", ".orc", "--run-id", "miss1")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            warning_lines = [line for line in result.stderr.splitlines() if line.startswith("observer:")]
            self.assertEqual(len(warning_lines), 1, result.stderr)
            self.assertIn("missing or not executable", warning_lines[0])
            self.assertIn("state=ACCEPTED", result.stdout)


if __name__ == "__main__":
    unittest.main()
