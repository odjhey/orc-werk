"""`RunLock`: stdlib-only, `fcntl.flock`-based advisory exclusive lock
primitive implementing `CONTRACT-STORAGE-CONCURRENCY` §2/§4/§10/§11.

## Why this lives directly under `orc_werk.adapters`, not
## `orc_werk.adapters.jsonl`

`CONTRACT-STORAGE-CONCURRENCY` A1 rules that ONE lock per run directory
covers that run's `journal.jsonl` AND `config.json` together, as a single
group. The journal lives in `orc_werk.adapters.jsonl`; `config.json`'s
read-modify-write lives in `orc_werk.cli.config` (a CLI-layer module, not
an adapter). Nesting this primitive inside the `jsonl` package would make
`orc_werk.cli.config` reach into a sibling adapter's internals for a
generic filesystem primitive that has nothing JSONL-specific about it (it
knows nothing about journals, records, or JSON at all). Putting it at the
top of `orc_werk.adapters` makes it a shared primitive both call sites
import symmetrically, matching how `orc_werk.adapters.jsonl.layout`
already centralizes the one shared path-resolution choke point both
`JSONLJournal` and `orc_werk.cli.config`/`orc_werk.cli.main` depend on.

## Design summary

- One OS advisory exclusive lock (`fcntl.flock(LOCK_EX)`) per lock file.
  The lock file MAY remain permanently on disk (§2) -- this module never
  deletes it, and callers MUST NOT either; existence of the file is never
  meaningful (a lock file with no OS lock held on it is indistinguishable
  from one that was never touched).
- Kernel-managed: closing the file descriptor releases the lock, including
  on an uncaught SIGKILL (§11's "MUST NOT require manual stale-lock
  cleanup" guarantee -- `SCN-019` item 3 exercises this directly).
- Canonicalized path identity (§10): the lock file path is `.resolve()`d
  once, in the constructor, before ever being opened -- two aliases for the
  same run directory (a relative vs. absolute `--journal` flag, a
  symlinked ancestor, ...) resolve to the same canonical lock file.
- Bounded timeout with retry/backoff (§11): `acquire()` retries a
  non-blocking `flock` attempt with a capped exponential backoff until
  `timeout_s` elapses, then raises canonical `ERR-BUSY`
  (`orc_werk.core.errors.busy_error`) naming the lock path and timeout --
  never silently falling back to an unlocked write.
- `acquire_sorted` (§4): the multi-lock ordering helper for the rare
  operation that legitimately needs more than one lock -- canonicalize,
  dedupe, sort lexicographically, acquire in that order, release in
  reverse. Per A1's note, no ordinary single-run Orc Werk operation
  actually needs this today (exactly one lock, the run-group lock); it
  exists so `SCN-019` item 7 has a real multi-lock path to exercise and so
  any future cross-run/cross-workspace operation has a correct primitive
  ready rather than inventing its own ordering ad hoc.

Stdlib only (`fcntl`, `os`, `time`, `pathlib`) -- `fcntl` is POSIX-only, an
accepted scope limit consistent with `CONTRACT-STORAGE-CONCURRENCY` §1's
own scope ("network/NFS/SMB filesystems are NOT supported"; Windows is
similarly out of scope for this milestone's local-filesystem CLI target).
"""

from __future__ import annotations

import errno
import fcntl
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Iterable, Iterator, List, Optional

from orc_werk.core.errors import busy_error

# Bounded timeout (§11) -- generous enough that an ordinary short RMW/append
# critical section (no network/agent calls, per §3) never spuriously times
# out under normal contention, small enough that a genuinely stuck holder
# fails fast rather than hanging a CLI invocation indefinitely. Callers
# needing a different bound (tests exercising item 6's timeout path in
# sub-second wall time, in particular) pass their own `timeout_s`.
DEFAULT_TIMEOUT_S = 10.0

# Capped exponential backoff between non-blocking acquisition attempts
# (§11 "retry/backoff") -- starts fast (uncontended acquisition is the
# common case and should not pay a fixed poll delay) and caps low (a long
# poll interval would itself risk missing the deadline by a wide margin).
_INITIAL_POLL_S = 0.005
_MAX_POLL_S = 0.25


class RunLock:
    """A single OS advisory exclusive lock on one lock file.

    Context-manager API (`with RunLock(path):`); `acquire()`/`release()`
    are also public for callers that need to hold the lock across more
    than one `with` block's worth of code (e.g. `acquire_sorted` below).
    """

    def __init__(
        self,
        path: os.PathLike[str] | str,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        poll_interval_s: float = _INITIAL_POLL_S,
    ) -> None:
        # §10: canonicalize now, once, so two aliases for the same run
        # directory can never produce unrelated locks regardless of what
        # form the caller's own path resolution happened to leave `path` in.
        self._path = Path(path).resolve()
        self._timeout_s = timeout_s
        self._initial_poll_s = poll_interval_s
        self._fh: Optional[IO[bytes]] = None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def held(self) -> bool:
        return self._fh is not None

    def acquire(self) -> None:
        if self._fh is not None:
            return  # already held by this instance -- re-entrant no-op
        # The lock file itself MAY remain permanently on disk (§2) -- open
        # in append mode (never truncate; create if absent) so a lock file
        # that already exists from a prior run is never rewritten or
        # emptied merely by acquiring it again.
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self._path, "a+b")
        deadline = time.monotonic() + self._timeout_s
        poll = self._initial_poll_s
        try:
            while True:
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self._fh = fh
                    return
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN):
                        raise
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise busy_error(
                            f"could not acquire storage lock within {self._timeout_s}s: {self._path}",
                            path=str(self._path),
                            timeout_s=self._timeout_s,
                        ) from exc
                    time.sleep(min(poll, remaining))
                    poll = min(poll * 2, _MAX_POLL_S)
        except BaseException:
            fh.close()
            raise

    def release(self) -> None:
        if self._fh is None:
            return
        fh = self._fh
        self._fh = None
        try:
            # Kernel-managed (§11): released by closing the fd. Never
            # deleted (§2) -- the file itself is left in place, permanently.
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()

    def __enter__(self) -> "RunLock":
        self.acquire()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()


@contextmanager
def acquire_sorted(
    paths: Iterable[os.PathLike[str] | str],
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    poll_interval_s: float = _INITIAL_POLL_S,
) -> Iterator[List[RunLock]]:
    """§4's multi-lock protocol: canonicalize every path, dedupe, sort
    lexicographically, acquire in that order, release in reverse order on
    exit (success or exception alike). Yields the acquired locks in
    acquisition order.

    Every caller that ever needs more than one lock MUST go through this
    (never acquire multiple locks in ad hoc business-operation order) --
    the same ordering is the only thing that makes concurrent multi-lock
    operations with overlapping resource sets deadlock-free."""
    canonical = sorted({Path(p).resolve() for p in paths}, key=str)
    locks = [RunLock(p, timeout_s=timeout_s, poll_interval_s=poll_interval_s) for p in canonical]
    acquired: List[RunLock] = []
    try:
        for lock in locks:
            lock.acquire()
            acquired.append(lock)
        yield acquired
    finally:
        for lock in reversed(acquired):
            lock.release()


__all__ = ["DEFAULT_TIMEOUT_S", "RunLock", "acquire_sorted"]
