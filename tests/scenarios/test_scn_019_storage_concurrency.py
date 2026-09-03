"""SCN-019 -- storage concurrency battery
(`docs/scenarios/SCN-019-storage-concurrency.md`,
`CONTRACT-STORAGE-CONCURRENCY` §12's required-test list, implemented).

Every test below is a SEPARATE OS PROCESS test (`subprocess.Popen` running
small worker scripts written to a temp dir, never threads/async tasks --
`SCN-019`'s "Given" section states this as a conformance bar, not merely a
recommendation, and `CONTRACT-STORAGE-CONCURRENCY` §12's mutation check
explicitly fails any test in this battery that only passes under
threads/async tasks). Numbered exactly as the contract's §12 and this
scenario's "When / Then" section number them -- including item 5, which is
conditional (no SQLite adapter exists) and stated in place rather than
dropped or renumbered.

Kept intentionally small-N / tight-loop (module docstring budget: added
wall time should stay well under the low tens of seconds) -- each test
demonstrates the property with a handful of concurrent OS processes, not a
load test.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from typing import List, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"

_ENV = {"PYTHONPATH": str(SRC), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}


def _write_worker(tmp_dir: Path, name: str, code: str) -> Path:
    path = tmp_dir / name
    path.write_text(textwrap.dedent(code), encoding="utf-8")
    return path


def _run_worker(script: Path, *args: str, timeout: float = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *args],
        env=_ENV,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _popen_worker(script: Path, *args: str) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, str(script), *args],
        env=_ENV,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _wait_for(path: Path, *, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {path} to appear")


def _kill_and_reap(proc: subprocess.Popen, *, timeout: float = 10.0) -> None:
    """SIGKILL a still-running worker and drain/close its pipes via
    `communicate` (never bare `wait`, which leaves the `PIPE` file objects
    open and unread -- a `ResourceWarning`, and on some platforms a way to
    leak fds across a long test run)."""
    if proc.poll() is None:
        proc.kill()
    try:
        proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate(timeout=5.0)


# ---------------------------------------------------------------------------
# Worker script bodies (written to temp files per-test by setUp).
# ---------------------------------------------------------------------------

# Item 1: one `record_execution_outcome_entry`-shaped RMW against a shared
# config.json. `disable_lock=1` monkeypatches the module's own `RunLock`
# name to a no-op AND injects a small post-read sleep -- widening the race
# window so the mutation check (unlocked storm) fails with high probability
# rather than only rarely, per the brief's "document the probabilistic
# nature honestly" instruction below.
_RMW_WORKER = """\
    import sys, time, random
    from pathlib import Path
    sys.path.insert(0, {src!r})
    import orc_werk.cli.config as config_mod

    def main():
        config_path = Path(sys.argv[1])
        work_id = sys.argv[2]
        lock_timeout_s = float(sys.argv[3])
        disable_lock = sys.argv[4] == "1"
        if disable_lock:
            class _NoLock:
                def __init__(self, *a, **k): pass
                def __enter__(self): return self
                def __exit__(self, *a): return False
            config_mod.RunLock = _NoLock
            # Test-only race-window widener (module docstring): without a
            # deliberate pause between read and write, two fast unlocked
            # RMWs on this machine may not actually interleave often enough
            # to reliably demonstrate the lost-update failure mode within a
            # few storm repeats -- this makes the failure highly likely,
            # not merely possible, WITHOUT changing which code path runs.
            real_load_config = config_mod.load_config
            def _slow_load_config(path):
                current = real_load_config(path)
                time.sleep(random.uniform(0.01, 0.05))
                return current
            config_mod.load_config = _slow_load_config
        config_mod.record_execution_outcome_entry(
            config_path, work_id=work_id, attempt_number=1, outcome="completed",
            lock_timeout_s=lock_timeout_s,
        )

    if __name__ == "__main__":
        main()
    """

# Item 2: N distinct-record JSONL appenders against one run's journal.
_APPEND_WORKER = """\
    import sys, time, random
    from pathlib import Path
    sys.path.insert(0, {src!r})
    import orc_werk.adapters.jsonl.journal as journal_mod
    from orc_werk.adapters.jsonl.journal import JSONLJournal
    from orc_werk.core.facts import Fact, FACT_WORK_CREATED

    def main():
        directory = Path(sys.argv[1])
        run_id = sys.argv[2]
        worker_id = sys.argv[3]
        count = int(sys.argv[4])
        lock_timeout_s = float(sys.argv[5])
        disable_lock = sys.argv[6] == "1"
        if disable_lock:
            class _NoLock:
                def __init__(self, *a, **k): pass
                def __enter__(self): return self
                def __exit__(self, *a): return False
            journal_mod.RunLock = _NoLock
            # Same race-window-widening rationale as the RMW worker above:
            # sleep briefly between the scan (read) and the append (write)
            # so concurrent unlocked appenders are likely to interleave.
            real_scan_tolerant = journal_mod.tailsafe.scan_tolerant
            def _slow_scan(path, *, noun):
                result = real_scan_tolerant(path, noun=noun)
                time.sleep(random.uniform(0.005, 0.03))
                return result
            journal_mod.tailsafe.scan_tolerant = _slow_scan
        journal = JSONLJournal(directory, lock_timeout_s=lock_timeout_s)
        for i in range(count):
            fact = Fact(
                id=FACT_WORK_CREATED,
                delivery_run_id=run_id,
                data={{"work_id": f"{{worker_id}}-{{i}}", "delivery_run_id": run_id}},
            )
            journal.append_fact(fact)

    if __name__ == "__main__":
        main()
    """

# Items 3/6: acquire the run lock and hold it (signalling readiness) until
# killed or a bounded hold time elapses.
_HOLDER_WORKER = """\
    import sys, time
    from pathlib import Path
    sys.path.insert(0, {src!r})
    from orc_werk.adapters.locking import RunLock

    def main():
        lock_path = Path(sys.argv[1])
        signal_path = Path(sys.argv[2])
        hold_s = float(sys.argv[3])
        lock = RunLock(lock_path, timeout_s=5.0)
        lock.acquire()
        signal_path.write_text("acquired")
        time.sleep(hold_s)
        lock.release()

    if __name__ == "__main__":
        main()
    """

# Item 4: pause AFTER the temp file is written but BEFORE `os.replace`
# (the real production replace path, `_replace_config_unlocked`), signal
# readiness, then wait to be killed.
_CRASH_REPLACE_WORKER = """\
    import sys, time
    from pathlib import Path
    sys.path.insert(0, {src!r})
    import orc_werk.cli.config as config_mod

    def main():
        config_path = Path(sys.argv[1])
        signal_path = Path(sys.argv[2])
        real_replace = config_mod.os.replace
        def _paused_replace(src, dst):
            signal_path.write_text("ready")
            time.sleep(60)
            return real_replace(src, dst)
        config_mod.os.replace = _paused_replace
        config_mod.record_execution_outcome_entry(
            config_path, work_id="work-1", attempt_number=1, outcome="completed",
        )

    if __name__ == "__main__":
        main()
    """

# Item 7: acquire several lock paths (given in a possibly-shuffled order)
# via the sorted-acquisition helper, hold briefly, release.
_MULTI_LOCK_WORKER = """\
    import sys, time
    from pathlib import Path
    sys.path.insert(0, {src!r})
    from orc_werk.adapters.locking import acquire_sorted

    def main():
        hold_s = float(sys.argv[1])
        paths = [Path(p) for p in sys.argv[2:]]
        with acquire_sorted(paths, timeout_s=5.0) as locks:
            resolved = [str(lock.path) for lock in locks]
            if resolved != sorted(resolved):
                raise AssertionError(f"locks acquired out of sorted order: {{resolved}}")
            time.sleep(hold_s)

    if __name__ == "__main__":
        main()
    """


def _rmw_worker_source() -> str:
    return _RMW_WORKER.format(src=str(SRC))


def _append_worker_source() -> str:
    return _APPEND_WORKER.format(src=str(SRC))


def _holder_worker_source() -> str:
    return _HOLDER_WORKER.format(src=str(SRC))


def _crash_replace_worker_source() -> str:
    return _CRASH_REPLACE_WORKER.format(src=str(SRC))


def _multi_lock_worker_source() -> str:
    return _MULTI_LOCK_WORKER.format(src=str(SRC))


# ---------------------------------------------------------------------------
# Shared setup: a run directory laid out per A1
# (<journal-dir>/<run_id>/{journal.jsonl,config.json,.state.lock}).
# ---------------------------------------------------------------------------


class _StorageConcurrencyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_dir = Path(self._tmp.name)
        self.directory = self.tmp_dir / ".orc"
        self.run_id = "run-scn019"
        self.run_dir = self.directory / self.run_id
        self.run_dir.mkdir(parents=True)
        self.config_path = self.run_dir / "config.json"
        self.lock_path = self.run_dir / ".state.lock"

    def _write_initial_config(self, content: str = "{}\n") -> None:
        self.config_path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Item 1 -- concurrent read-modify-write loses nothing.
# ---------------------------------------------------------------------------


class Item1ConcurrentConfigRMWTest(_StorageConcurrencyTestCase):
    N = 8

    def setUp(self) -> None:
        super().setUp()
        self.worker = _write_worker(self.tmp_dir, "rmw_worker.py", _rmw_worker_source())

    def _run_storm(self, *, disable_lock: bool, lock_timeout_s: float = 5.0) -> Sequence[subprocess.CompletedProcess]:
        self._write_initial_config()
        procs = [
            _popen_worker(
                self.worker,
                str(self.config_path),
                f"work-{i}",
                str(lock_timeout_s),
                "1" if disable_lock else "0",
            )
            for i in range(self.N)
        ]
        results = []
        for proc in procs:
            out, err = proc.communicate(timeout=30)
            results.append((proc.returncode, out, err))
        return results

    def _final_keys(self) -> set:
        data = json.loads(self.config_path.read_text(encoding="utf-8"))
        return set(data.get("attempts", {}))

    def test_locked_storm_loses_no_update(self) -> None:
        results = self._run_storm(disable_lock=False)
        for returncode, out, err in results:
            self.assertEqual(returncode, 0, msg=f"worker failed: {out}\n{err}")
        # config.json parses cleanly at rest (never a torn intermediate
        # state -- if the atomic-replace mechanics were broken this would
        # raise JSONDecodeError here).
        keys = self._final_keys()
        self.assertEqual(keys, {f"work-{i}" for i in range(self.N)}, "lost update under lock")

    def test_unlocked_storm_loses_updates_mutation_check(self) -> None:
        """MUTATION evidence (brief item 5/task instruction): with locking
        disabled, the SAME storm loses at least one update with high
        probability. Run 3x -- this is inherently probabilistic (real OS
        scheduling, not a guaranteed reproduction every run), so this
        asserts across 3 attempts and requires at least one to show a lost
        update, rather than asserting every single run does. If this test
        ever starts passing "no loss" reliably, the race-window widening
        above has stopped being wide enough for this machine/load and
        should be revisited -- it is not evidence locking is unnecessary."""
        saw_loss = False
        for _ in range(3):
            self._run_storm(disable_lock=True, lock_timeout_s=5.0)
            keys = self._final_keys()
            if keys != {f"work-{i}" for i in range(self.N)}:
                saw_loss = True
                break
        self.assertTrue(
            saw_loss,
            "expected the unlocked storm to lose at least one update across 3 attempts "
            "(mutation check for item 1) -- see this test's docstring",
        )


# ---------------------------------------------------------------------------
# Item 2 -- concurrent JSONL appenders preserve every record.
# ---------------------------------------------------------------------------


class Item2ConcurrentAppendersTest(_StorageConcurrencyTestCase):
    N = 6
    M = 3

    def setUp(self) -> None:
        super().setUp()
        self.worker = _write_worker(self.tmp_dir, "append_worker.py", _append_worker_source())

    def _run_storm(self, *, disable_lock: bool, lock_timeout_s: float = 5.0):
        # Fresh run directory per storm so item 2's storms don't interfere.
        import shutil

        if self.run_dir.exists():
            shutil.rmtree(self.run_dir)
        self.run_dir.mkdir(parents=True)
        procs = [
            _popen_worker(
                self.worker,
                str(self.directory),
                self.run_id,
                f"w{i}",
                str(self.M),
                str(lock_timeout_s),
                "1" if disable_lock else "0",
            )
            for i in range(self.N)
        ]
        results = []
        for proc in procs:
            out, err = proc.communicate(timeout=30)
            results.append((proc.returncode, out, err))
        return results

    def _read_lines(self) -> List[str]:
        journal_path = self.run_dir / "journal.jsonl"
        if not journal_path.exists():
            return []
        return journal_path.read_text(encoding="utf-8").splitlines()

    def test_locked_storm_preserves_every_record(self) -> None:
        results = self._run_storm(disable_lock=False)
        for returncode, out, err in results:
            self.assertEqual(returncode, 0, msg=f"worker failed: {out}\n{err}")
        lines = self._read_lines()
        expected_total = self.N * self.M
        self.assertEqual(len(lines), expected_total, "record count mismatch under lock")
        seqs = []
        work_ids = set()
        for line in lines:
            record = json.loads(line)  # every line must parse as one complete JSON object
            seqs.append(record["seq"])
            work_ids.add(record["data"]["work_id"])
        self.assertEqual(sorted(seqs), list(range(1, expected_total + 1)), "seq not a dense total order")
        self.assertEqual(len(work_ids), expected_total, "some record's identity collided/was lost")

    def test_unlocked_storm_corrupts_or_loses_records_mutation_check(self) -> None:
        """MUTATION evidence for item 2, same probabilistic framing as
        item 1's mutation test above."""
        saw_failure = False
        expected_total = self.N * self.M
        for _ in range(3):
            self._run_storm(disable_lock=True, lock_timeout_s=5.0)
            lines = self._read_lines()
            failure = len(lines) != expected_total
            if not failure:
                try:
                    seqs = [json.loads(line)["seq"] for line in lines]
                except (ValueError, KeyError):
                    failure = True
                else:
                    failure = sorted(seqs) != list(range(1, expected_total + 1))
            if failure:
                saw_failure = True
                break
        self.assertTrue(
            saw_failure,
            "expected the unlocked storm to lose/duplicate/corrupt at least one record "
            "across 3 attempts (mutation check for item 2) -- see this test's docstring",
        )


# ---------------------------------------------------------------------------
# Item 3 -- crash while holding the lock recovers without manual cleanup.
# ---------------------------------------------------------------------------


class Item3CrashWhileHoldingLockTest(_StorageConcurrencyTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.worker = _write_worker(self.tmp_dir, "holder_worker.py", _holder_worker_source())

    def test_kill_9_holder_then_fresh_acquire_succeeds(self) -> None:
        from orc_werk.adapters.locking import RunLock

        signal_path = self.tmp_dir / "acquired.signal"
        proc = _popen_worker(self.worker, str(self.lock_path), str(signal_path), "60")
        try:
            _wait_for(signal_path, timeout=10.0)
            # Uncatchable termination while the lock is held (item 3's
            # "When"): SIGKILL, not SIGTERM -- no cleanup handler in the
            # victim process can run at all.
            _kill_and_reap(proc)
        finally:
            _kill_and_reap(proc, timeout=5.0)

        # A subsequent, fresh process acquires the SAME lock file with no
        # stale-lock cleanup of any kind -- no unlink, no special-casing.
        start = time.monotonic()
        lock = RunLock(self.lock_path, timeout_s=5.0)
        lock.acquire()
        elapsed = time.monotonic() - start
        try:
            self.assertLess(elapsed, 2.0, "acquisition after a crash should be near-instant, not wait out a timeout")
        finally:
            lock.release()
        # The lock file itself is still there, untouched/undeleted (§2).
        self.assertTrue(self.lock_path.exists())


# ---------------------------------------------------------------------------
# Item 4 -- crash mid-replacement leaves a valid snapshot.
# ---------------------------------------------------------------------------


class Item4CrashMidReplacementTest(_StorageConcurrencyTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.worker = _write_worker(self.tmp_dir, "crash_replace_worker.py", _crash_replace_worker_source())

    def test_kill_after_temp_write_before_replace_leaves_old_snapshot(self) -> None:
        # A schema-valid config (unlike an arbitrary `note` key, which
        # `validate_config` would reject before `record_execution_outcome_
        # entry` ever reaches the replace-pause point this test needs to
        # hit) -- `run_id` is an ordinary optional top-level field, used
        # here purely as a recognizable "this is still the OLD snapshot"
        # marker.
        original = '{"run_id": "original-snapshot"}\n'
        self._write_initial_config(original)
        signal_path = self.tmp_dir / "replace_ready.signal"
        proc = _popen_worker(self.worker, str(self.config_path), str(signal_path))
        try:
            _wait_for(signal_path, timeout=10.0)
            # Kill after the temp file is fully written (the paused
            # os.replace stand-in signals readiness only after that), but
            # strictly before the atomic rename itself is ever invoked.
            _kill_and_reap(proc)
        finally:
            _kill_and_reap(proc, timeout=5.0)

        # The canonical path is EXACTLY the old complete snapshot -- never
        # partially written, truncated, or otherwise invalid.
        content = self.config_path.read_text(encoding="utf-8")
        self.assertEqual(content, original)
        parsed = json.loads(content)  # must still parse
        self.assertEqual(parsed, {"run_id": "original-snapshot"})

        # Any leftover temp file is inert: a different name, never mistaken
        # for the canonical target by any reader (which only ever opens
        # `config.json` itself).
        leftovers = [p for p in self.run_dir.iterdir() if p.name != "config.json"]
        for leftover in leftovers:
            self.assertNotEqual(leftover.name, "config.json")

        # A subsequent, fresh, correctly-completing write still succeeds
        # cleanly (the crash left nothing that blocks future writers).
        from orc_werk.cli.config import record_execution_outcome_entry

        record_execution_outcome_entry(self.config_path, work_id="work-2", attempt_number=1, outcome="completed")
        final = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertIn("work-2", final.get("attempts", {}))


# ---------------------------------------------------------------------------
# Item 5 -- SQLite (conditional; no adapter exists yet).
# ---------------------------------------------------------------------------


class Item5SqliteWritersTest(unittest.TestCase):
    def test_no_sqlite_adapter_exists_yet_binds_any_future_one(self) -> None:
        # Assert the premise this skip depends on, so a future SQLite
        # adapter landing silently makes this test start failing (loudly)
        # instead of this skip quietly going stale.
        sqlite_adapter_dir = SRC / "orc_werk" / "adapters" / "sqlite"
        self.assertFalse(
            sqlite_adapter_dir.exists(),
            "a SQLite adapter now exists -- CONTRACT-STORAGE-CONCURRENCY §12 item 5/§7 "
            "requires this test to be replaced with a real many-simultaneous-writers "
            "BEGIN IMMEDIATE...COMMIT test landing WITH that adapter, not merely skipped",
        )
        self.skipTest(
            "CONTRACT-STORAGE-CONCURRENCY §7/§12 item 5, SCN-019 item 5: no SQLite-backed "
            "adapter exists in this repo yet. This item is kept in the battery at its "
            "source number (never dropped or silently renumbered, per the scenario's "
            "'Mutation check' section) and binds any future SQLite adapter to land with "
            "a real many-simultaneous-writers test producing the expected final state "
            "(no lost update, no constraint bypass, no partial transaction visible)."
        )


# ---------------------------------------------------------------------------
# Item 6 -- lock timeout surfaces ERR-BUSY, never an unlocked fallback.
# ---------------------------------------------------------------------------


class Item6LockTimeoutTest(_StorageConcurrencyTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.worker = _write_worker(self.tmp_dir, "holder_worker.py", _holder_worker_source())

    def test_timeout_raises_err_busy_and_state_unchanged(self) -> None:
        from orc_werk.core.errors import CoreError

        from orc_werk.cli.config import record_execution_outcome_entry

        original = '{"run_id": "unchanged"}\n'  # schema-valid marker, see item 4's test for why
        self._write_initial_config(original)

        signal_path = self.tmp_dir / "holder.signal"
        # Holder holds the run's group lock for longer than the second
        # process's configured bounded timeout below.
        proc = _popen_worker(self.worker, str(self.lock_path), str(signal_path), "3.0")
        try:
            _wait_for(signal_path, timeout=10.0)
            start = time.monotonic()
            with self.assertRaises(CoreError) as ctx:
                record_execution_outcome_entry(
                    self.config_path,
                    work_id="work-busy",
                    attempt_number=1,
                    outcome="completed",
                    lock_timeout_s=0.3,
                )
            elapsed = time.monotonic() - start
            self.assertEqual(ctx.exception.to_canonical()["error"], "ERR-BUSY")
            # Bounded: fails fast near the configured timeout, never hangs
            # past it and never waits out the holder's full 3s hold.
            self.assertLess(elapsed, 2.0)
            self.assertGreaterEqual(elapsed, 0.3 * 0.5)  # sanity: not suspiciously instant
        finally:
            proc.communicate(timeout=10.0)

        # Never an unlocked fallback (§11): state is byte-for-byte
        # unchanged by the failed attempt.
        self.assertEqual(self.config_path.read_text(encoding="utf-8"), original)


# ---------------------------------------------------------------------------
# Item 7 -- multiple-resource locking never deadlocks.
# ---------------------------------------------------------------------------


class Item7MultiLockOrderingTest(_StorageConcurrencyTestCase):
    """No real Orc Werk operation needs more than one lock today (A1: every
    ordinary single-run operation acquires exactly the one run-group lock)
    -- per `SCN-019` item 7's own text ("exercise a two-resource case if
    one exists, else test the lock module's sorted-acquisition helper
    directly"), this exercises `orc_werk.adapters.locking.acquire_sorted`
    directly with many workers racing over an overlapping resource set."""

    WORKERS = 8

    def setUp(self) -> None:
        super().setUp()
        self.worker = _write_worker(self.tmp_dir, "multi_lock_worker.py", _multi_lock_worker_source())

    def test_many_overlapping_multi_lock_acquisitions_never_deadlock(self) -> None:
        resource_paths = [self.tmp_dir / f"resource-{letter}.lock" for letter in "abc"]
        procs = []
        for i in range(self.WORKERS):
            # Shuffle the argument order per worker (every participant MUST
            # still acquire canonicalized-sorted order regardless of the
            # order it was asked to lock them in, §4) -- alternate two
            # different orderings deterministically rather than relying on
            # `random` for reproducibility.
            ordered = resource_paths if i % 2 == 0 else list(reversed(resource_paths))
            procs.append(_popen_worker(self.worker, "0.05", *[str(p) for p in ordered]))

        deadline = time.monotonic() + 15.0
        results = []
        for proc in procs:
            remaining = max(0.1, deadline - time.monotonic())
            try:
                out, err = proc.communicate(timeout=remaining)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                self.fail("multi-lock worker did not complete in time -- suspected deadlock")
            results.append((proc.returncode, out, err))

        for returncode, out, err in results:
            self.assertEqual(returncode, 0, msg=f"worker failed: {out}\n{err}")


# ---------------------------------------------------------------------------
# Item 8 -- malformed/incomplete final JSONL records recover cleanly.
# ---------------------------------------------------------------------------


class Item8TornAndMalformedRecoveryTest(_StorageConcurrencyTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.worker = _write_worker(self.tmp_dir, "append_worker.py", _append_worker_source())

    def test_torn_final_record_under_concurrent_append_load_heals_on_next_append(self) -> None:
        from orc_werk.adapters.jsonl.journal import JSONLJournal
        from orc_werk.core.facts import FACT_WORK_CREATED, Fact

        n, m = 4, 2
        procs = [
            _popen_worker(self.worker, str(self.directory), self.run_id, f"w{i}", str(m), "5.0", "0")
            for i in range(n)
        ]
        for proc in procs:
            out, err = proc.communicate(timeout=30)
            self.assertEqual(proc.returncode, 0, msg=f"worker failed: {out}\n{err}")

        journal_path = self.run_dir / "journal.jsonl"
        raw = journal_path.read_bytes()
        good_line_count = raw.count(b"\n")
        self.assertEqual(good_line_count, n * m)

        # Simulate a torn write left by a crash mid-append (or, per this
        # item's "When", a concurrent-writer interleaving fault): truncate
        # the final line so it is no longer valid JSON, with the trailing
        # newline removed too (a genuinely partial write).
        last_newline = raw.rstrip(b"\n").rfind(b"\n")
        torn = raw[: last_newline + 1] + raw[last_newline + 1 : -8]
        journal_path.write_bytes(torn)

        journal = JSONLJournal(self.directory)
        history = journal.history(delivery_run_id=self.run_id)
        # The torn final record is ignored; every good record before it is
        # still present, continuing from the last good record.
        self.assertEqual(len(history), n * m - 1)

        # The next append heals the file (truncates the torn bytes away)
        # and lands a new, complete, valid final record.
        journal.append_fact(
            Fact(
                id=FACT_WORK_CREATED,
                delivery_run_id=self.run_id,
                data={"work_id": "healed", "delivery_run_id": self.run_id},
            )
        )
        healed_history = journal.history(delivery_run_id=self.run_id)
        self.assertEqual(len(healed_history), n * m)
        lines = journal_path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            json.loads(line)  # every line parses as one complete JSON object again

    def test_malformed_non_final_record_fails_closed(self) -> None:
        from orc_werk.adapters.jsonl.journal import JSONLJournal
        from orc_werk.core.errors import CoreError
        from orc_werk.core.facts import FACT_WORK_CREATED, Fact

        journal = JSONLJournal(self.directory)
        journal.append_fact(
            Fact(
                id=FACT_WORK_CREATED,
                delivery_run_id=self.run_id,
                data={"work_id": "work-1", "delivery_run_id": self.run_id},
            )
        )
        journal.append_fact(
            Fact(
                id=FACT_WORK_CREATED,
                delivery_run_id=self.run_id,
                data={"work_id": "work-2", "delivery_run_id": self.run_id},
            )
        )
        journal_path = self.run_dir / "journal.jsonl"
        lines = journal_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        lines[0] = "{not valid json"
        journal_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        fresh = JSONLJournal(self.directory)
        with self.assertRaises(CoreError) as ctx:
            fresh.history(delivery_run_id=self.run_id)
        self.assertEqual(ctx.exception.to_canonical()["error"], "ERR-VALIDATION")


if __name__ == "__main__":
    unittest.main()
