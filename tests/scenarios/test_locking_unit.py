"""`orc_werk.adapters.locking` local/unit-level branches
(`CONTRACT-STORAGE-CONCURRENCY` §2/§4/§10/§11).

`tests/scenarios/test_scn_019_storage_concurrency.py` is the SEPARATE-OS-
PROCESS battery for this module's cross-process behavior (§12's required
list, `SCN-019`). This sibling file covers the branches that are properly
LOCAL error handling rather than cross-process behavior -- most of them
reachable with a real trigger in a single process (two independent
`RunLock` instances opening the *same* lock file get two distinct open
file descriptions, and BSD `flock()` conflicts across open file
descriptions even within one process, so a genuine contended-timeout is
achievable without a subprocess) -- and the two branches for which a real
trigger is impractical without faking a kernel-level failure
(an unexpected, non-`EACCES`/`EAGAIN` `OSError` from `flock`, and an
`flock(LOCK_UN)` failure during release) are covered by monkeypatching
`fcntl.flock` directly, per this run's brief.

Also covers `acquire_sorted` (§4) at the unit level: the coverage
evaluation this run answers found it looking uncovered even though
`SCN-019` item 7 exercises it -- because that exercise happens inside a
`subprocess.Popen` worker, invisible to a coverage.py run over the parent
process (the same "subprocess coverage accounting" gap the brief documents
for `cli/main.py`/`cli/jsonview.py`, just for this module too). These
tests call `acquire_sorted` directly, in-process.
"""

from __future__ import annotations

import errno
import os
import time
import unittest
from pathlib import Path
from unittest import mock

from orc_werk.adapters.locking import RunLock, acquire_sorted
from orc_werk.core.errors import CoreError


class RunLockPropertiesTest(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_dir = Path(self._tmp.name)

    def test_path_property_returns_the_resolved_canonicalized_path(self) -> None:
        # §10: a relative alias for the same file resolves to the same
        # canonical `.path` a caller could compare/log/report.
        relative = self.tmp_dir / "sub" / ".." / "run.lock"
        lock = RunLock(relative)
        self.assertEqual(lock.path, (self.tmp_dir / "run.lock").resolve())
        self.assertTrue(lock.path.is_absolute())

    def test_held_property_reflects_the_acquire_release_lifecycle(self) -> None:
        lock = RunLock(self.tmp_dir / "run.lock")
        self.assertFalse(lock.held)
        lock.acquire()
        try:
            self.assertTrue(lock.held)
        finally:
            lock.release()
        self.assertFalse(lock.held)

    def test_reentrant_acquire_on_the_same_instance_is_a_noop(self) -> None:
        lock_path = self.tmp_dir / "run.lock"
        lock = RunLock(lock_path)
        lock.acquire()
        self.addCleanup(lock.release)
        first_fh = lock._fh  # noqa: SLF001 -- whitebox: prove no reopen happened
        lock.acquire()  # re-entrant: must return early (line 115), not reopen
        self.assertIs(lock._fh, first_fh)  # noqa: SLF001
        self.assertTrue(lock.held)

        # Real proof the lock is still genuinely held exactly once (not
        # doubly acquired/leaked): a second, independent instance on the
        # SAME path must still time out promptly.
        waiter = RunLock(lock_path, timeout_s=0.1)
        with self.assertRaises(CoreError) as ctx:
            waiter.acquire()
        self.assertEqual(ctx.exception.to_canonical()["error"], "ERR-BUSY")


class RunLockAcquisitionTimeoutTest(unittest.TestCase):
    """Real (no subprocess, no monkeypatch) contended-timeout trigger:
    two `RunLock` instances opening the same file each get a distinct
    open file description, and `flock()` conflicts across those even
    within a single process."""

    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.lock_path = Path(self._tmp.name) / "nested" / "run.lock"

    def test_timeout_raises_err_busy_with_the_exact_canonical_shape(self) -> None:
        holder = RunLock(self.lock_path, timeout_s=5.0)
        holder.acquire()
        self.addCleanup(holder.release)

        waiter = RunLock(self.lock_path, timeout_s=0.2)
        start = time.monotonic()
        with self.assertRaises(CoreError) as ctx:
            waiter.acquire()
        elapsed = time.monotonic() - start

        canonical = ctx.exception.to_canonical()
        self.assertEqual(canonical["error"], "ERR-BUSY")
        self.assertEqual(canonical["details"]["path"], str(self.lock_path.resolve()))
        self.assertEqual(canonical["details"]["timeout_s"], 0.2)
        self.assertIn(str(self.lock_path.resolve()), canonical["message"])
        self.assertIn("0.2", canonical["message"])
        # Bounded: fails close to the configured timeout, never hangs.
        self.assertLess(elapsed, 2.0)
        # Never left in a half-acquired state after the failure.
        self.assertFalse(waiter.held)

    def test_timeout_never_leaves_an_unlocked_fallback_the_original_holder_still_holds_it(self) -> None:
        holder = RunLock(self.lock_path, timeout_s=5.0)
        holder.acquire()
        self.addCleanup(holder.release)
        waiter = RunLock(self.lock_path, timeout_s=0.1)
        with self.assertRaises(CoreError):
            waiter.acquire()
        # The original holder's lock is completely undisturbed by the
        # failed contender -- release/reacquire still round-trips cleanly.
        holder.release()
        holder.acquire()
        self.assertTrue(holder.held)


class RunLockUnexpectedOsErrorTest(unittest.TestCase):
    """The one `acquire()` branch with no practical real trigger (a
    non-`EACCES`/`EAGAIN` `OSError` out of `flock`, e.g. `EBADF`/`EIO`
    from a kernel/driver failure): monkeypatched per the brief."""

    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.lock_path = Path(self._tmp.name) / "run.lock"

    def test_unexpected_errno_propagates_unwrapped_and_closes_the_fd(self) -> None:
        # Capture the exact fd `flock` was called with, rather than
        # shadowing the `open` builtin (a module-global-injection trick
        # that proved order-dependent-fragile under CPython's `LOAD_GLOBAL`
        # specialization once `RunLock.acquire()` has already been called
        # many times elsewhere in a full-suite run -- see PR body
        # "Ambiguities" for the full story). Verifying closure via
        # `os.fstat` raising `EBADF` is a direct, real OS-level signal
        # with no such fragility.
        captured_fds: list[int] = []

        def _failing_flock(fd, *_args, **_kwargs):
            captured_fds.append(fd)
            raise OSError(errno.EIO, "simulated I/O error")

        lock = RunLock(self.lock_path, timeout_s=5.0)
        with mock.patch("orc_werk.adapters.locking.fcntl.flock", side_effect=_failing_flock):
            with self.assertRaises(OSError) as ctx:
                lock.acquire()

        # Never silently reinterpreted as ERR-BUSY/canonical -- an
        # unexpected errno is a real, unmasked failure.
        self.assertNotIsInstance(ctx.exception, CoreError)
        self.assertEqual(ctx.exception.errno, errno.EIO)
        self.assertEqual(len(captured_fds), 1)
        # The fd is closed on the way out (never leaked): a closed fd
        # raises EBADF from `os.fstat`, checked immediately -- before any
        # other file operation could recycle that fd number.
        with self.assertRaises(OSError) as fd_check:
            os.fstat(captured_fds[0])
        self.assertEqual(fd_check.exception.errno, errno.EBADF)
        self.assertFalse(lock.held)

        # A fresh, real acquisition afterwards still succeeds cleanly --
        # the simulated failure left nothing stuck.
        lock.acquire()
        try:
            self.assertTrue(lock.held)
        finally:
            lock.release()


class RunLockReleaseTest(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.lock_path = Path(self._tmp.name) / "run.lock"

    def test_release_without_a_prior_acquire_is_a_noop(self) -> None:
        lock = RunLock(self.lock_path)
        lock.release()  # must not raise
        lock.release()  # idempotent
        self.assertFalse(lock.held)

    def test_release_closes_the_fd_even_when_flock_unlock_fails(self) -> None:
        lock = RunLock(self.lock_path)
        lock.acquire()
        fh = lock._fh  # noqa: SLF001 -- whitebox: assert the fd's fate directly

        with mock.patch(
            "orc_werk.adapters.locking.fcntl.flock",
            side_effect=OSError(errno.EBADF, "simulated unlock failure"),
        ):
            with self.assertRaises(OSError) as ctx:
                lock.release()
        self.assertEqual(ctx.exception.errno, errno.EBADF)

        # The `finally: fh.close()` branch still ran despite the raised
        # unlock error -- the fd is not leaked even on a failed release.
        self.assertTrue(fh.closed)
        # The instance itself was already marked not-held before the
        # unlock attempt (release() clears `_fh` up front).
        self.assertFalse(lock.held)


class RunLockContextManagerTest(unittest.TestCase):
    """The `with RunLock(...)` protocol itself (`__enter__`/`__exit__`,
    locking.py lines 158-163) -- the verify seat's finding on this lane's
    first attempt: every other test in this file drives
    `acquire()`/`release()` directly, so the two protocol methods were
    never executed by THIS file's tests."""

    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.lock_path = Path(self._tmp.name) / "run.lock"

    def test_with_block_acquires_yields_self_and_releases_on_clean_exit(self) -> None:
        lock = RunLock(self.lock_path)
        self.assertFalse(lock.held)
        with lock as entered:
            # `__enter__` returns the RunLock itself, genuinely held.
            self.assertIs(entered, lock)
            self.assertTrue(lock.held)
            # Really held at the OS level, not just flagged: an
            # independent instance on the same path must time out.
            contender = RunLock(self.lock_path, timeout_s=0.1)
            with self.assertRaises(CoreError) as ctx:
                contender.acquire()
            self.assertEqual(ctx.exception.to_canonical()["error"], "ERR-BUSY")
        # `__exit__` released: not held, and a fresh instance acquires
        # immediately (no timeout wait).
        self.assertFalse(lock.held)
        start = time.monotonic()
        reacquirer = RunLock(self.lock_path, timeout_s=5.0)
        reacquirer.acquire()
        try:
            self.assertLess(time.monotonic() - start, 1.0)
        finally:
            reacquirer.release()

    def test_with_block_releases_on_exception_too(self) -> None:
        lock = RunLock(self.lock_path)

        class _BodyError(Exception):
            pass

        with self.assertRaises(_BodyError):
            with lock:
                self.assertTrue(lock.held)
                raise _BodyError("body failure must still release the lock")

        # `__exit__` ran despite the exception: released, and immediately
        # reacquirable by an independent instance.
        self.assertFalse(lock.held)
        contender = RunLock(self.lock_path, timeout_s=0.5)
        contender.acquire()
        try:
            self.assertTrue(contender.held)
        finally:
            contender.release()


class AcquireSortedTest(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_dir = Path(self._tmp.name)

    def test_dedupes_sorts_and_yields_in_canonical_acquisition_order(self) -> None:
        a = self.tmp_dir / "a.lock"
        b = self.tmp_dir / "b.lock"
        c = self.tmp_dir / "c.lock"
        # Shuffled order, plus a duplicate alias for `a` (a relative form
        # that resolves to the same canonical path) -- both the ordering
        # and the dedup must hold.
        with acquire_sorted([c, a, b, self.tmp_dir / "." / "a.lock"]) as locks:
            resolved = [str(lock.path) for lock in locks]
            self.assertEqual(resolved, sorted([str(a.resolve()), str(b.resolve()), str(c.resolve())]))
            self.assertEqual(len(locks), 3, "duplicate alias for the same canonical path must not double-acquire")
            for lock in locks:
                self.assertTrue(lock.held)
        # All released again on clean exit.
        for lock in locks:
            self.assertFalse(lock.held)

    def test_releases_in_reverse_of_acquisition_order(self) -> None:
        a = self.tmp_dir / "a.lock"
        b = self.tmp_dir / "b.lock"
        release_order: list[str] = []
        real_release = RunLock.release

        def _tracking_release(self: RunLock) -> None:
            if self.held:
                release_order.append(str(self.path))
            real_release(self)

        with mock.patch.object(RunLock, "release", _tracking_release):
            with acquire_sorted([b, a]) as locks:
                acquired_order = [str(lock.path) for lock in locks]

        self.assertEqual(acquired_order, [str(a.resolve()), str(b.resolve())])
        self.assertEqual(release_order, list(reversed(acquired_order)))

    def test_partial_acquisition_failure_releases_only_the_already_acquired_locks_in_reverse(self) -> None:
        a = self.tmp_dir / "a.lock"
        b = self.tmp_dir / "b.lock"
        c = self.tmp_dir / "c.lock"
        # Canonical sorted order is a, b, c. Fail the SECOND acquire (b) so
        # the third (c) is never even attempted, and the first (a) must
        # still be released on the way out via the `finally` clause.
        real_acquire = RunLock.acquire
        acquire_calls: list[str] = []

        def _failing_second_acquire(self: RunLock) -> None:
            acquire_calls.append(str(self.path))
            if self.path == b.resolve():
                raise OSError(errno.EACCES, "simulated acquisition failure")
            real_acquire(self)

        release_calls: list[str] = []
        real_release = RunLock.release

        def _tracking_release(self: RunLock) -> None:
            if self.held:
                release_calls.append(str(self.path))
            real_release(self)

        with mock.patch.object(RunLock, "acquire", _failing_second_acquire), \
                mock.patch.object(RunLock, "release", _tracking_release):
            with self.assertRaises(OSError) as ctx:
                with acquire_sorted([c, a, b]):
                    self.fail("body must not run: acquisition failed before yield")

        self.assertEqual(ctx.exception.errno, errno.EACCES)
        # Only a and b were attempted (in canonical order) -- c never was.
        self.assertEqual(acquire_calls, [str(a.resolve()), str(b.resolve())])
        # Only the successfully-acquired lock (a) was released.
        self.assertEqual(release_calls, [str(a.resolve())])


if __name__ == "__main__":
    unittest.main()
