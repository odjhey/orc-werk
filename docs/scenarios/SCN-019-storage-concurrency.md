---
id: SCN-019
type: scenario
status: current
authority: normative
description: Concurrent-storage safety as executable specification — no lost updates, no corrupted appends, crash-safe recovery, and a canonical busy error instead of an unlocked fallback (`CONTRACT-STORAGE-CONCURRENCY`).
---

# SCN-019 — Storage concurrency

## Purpose

`CONTRACT-STORAGE-CONCURRENCY` rules the locking, atomic-replacement, and
append-safety protocol every Orc Werk CLI storage path must follow once
implemented. This scenario is that contract's §12 required test battery
stated as an executable specification, and is the conformance bar the
implementation PR (PR 2, following this docs-only PR) must satisfy before
any lock-acquiring code lands. It exists because the live gap it closes is
real, not hypothetical: two seats recording into the same multi-work run's
`config.json` concurrently can silently lose one seat's recorded outcome
today (`CONTRACT-STORAGE-CONCURRENCY`'s "Current gaps at adoption" list).

Unlike the other golden scenarios, this one is not a delivery-state-machine
walkthrough — `src/orc_werk/core` has no filesystem concerns at all
(`ARCH-REPOSITORY-STRUCTURE`) and is untouched by anything here. This
scenario exercises the CLI/adapter storage layer directly:
`orc_werk.adapters.jsonl` (the journal) and `orc_werk.cli.config`/
`orc_werk.cli.main` (the config read-modify-write and effective-config
persistence paths).

## Given

- A run directory laid out per `CONTRACT-STORAGE-CONCURRENCY` A1:
  `<journal-dir>/<run_id>/journal.jsonl`, `<journal-dir>/<run_id>/config.json`,
  and `<journal-dir>/<run_id>/.state.lock` covering both as one group.
- Multiple independent OS processes (not threads or async tasks — §12's
  "SHOULD run in separate OS processes" requirement, stated here as a
  conformance bar, not merely a recommendation) capable of invoking the
  same read-modify-write, append, or replacement operation concurrently
  against that run.
- A bounded lock-acquisition timeout configured for the storage layer.

## When / Then, by required test

Each numbered item below is one required automated test
(`CONTRACT-STORAGE-CONCURRENCY` §12, items 1–4 and 6–8; item 5, SQLite
writers, is not applicable — no shipped adapter uses SQLite, §7).

### 1. Concurrent read-modify-write loses nothing

**When** N processes each run a `record_execution_outcome_entry`/
`record_assurance_entry`-shaped read-modify-write against the same run's
`config.json` concurrently, each merging a distinct attempt-entry key.
**Then** every process's mutation is present in the final `config.json` —
none is silently overwritten by a later writer's read-before-my-write race
— and `config.json` parses as valid JSON at every point an external
reader might open it (never a torn intermediate state).

### 2. Concurrent JSONL appenders preserve every record

**When** N processes each append one or more distinct, complete journal
records to the same run's `journal.jsonl` concurrently.
**Then** every appended record is present, in some deterministic total
order recorded as `seq` (`PORT-JOURNAL-ENVELOPE`), every line in the final
file parses as one complete JSON object, and no record is partially
interleaved with another (never two records' bytes merged onto one line,
never one record's bytes split across two lines).

### 3. Crash while holding the lock recovers without manual cleanup

**When** a process acquires the run's `.state.lock`, then terminates
(SIGKILL, uncatchable) before releasing it.
**Then** a subsequent process from a fresh invocation successfully
acquires the same lock and proceeds — no stale-lock file blocks it, no
operator or script needs to delete anything by hand (`CONTRACT-STORAGE-CONCURRENCY`
§11's "MUST NOT require manual stale-lock cleanup" clause, guaranteed by
kernel-managed (`flock`/`fcntl`) locking releasing automatically when the
crashed process's file descriptor closes on process death).

### 4. Crash mid-replacement leaves a valid snapshot

**When** a process is terminated mid-way through the atomic-replacement
sequence for `config.json` (after the temp file is written but before, or
during, `os.replace`) or, separately, mid-way through `_persist_effective_config`'s
future lock-and-atomic-replace form.
**Then** the target file, read by any subsequent process, is either the
complete old snapshot or the complete new snapshot — never a partially
written, truncated, or otherwise invalid file. A leftover temp file (if the
crash lands before `os.replace`) is inert and never mistaken for the
target by any reader.

### 5. Lock timeout surfaces `ERR-BUSY`, never an unlocked fallback

**When** a process holds the run's lock for longer than another process's
configured bounded timeout, and the second process attempts a
lock-requiring operation during that window.
**Then** the second process fails fast with the canonical structured
`ERR-BUSY` (`CONTRACT-ERRORS`) — never silently proceeding without the
lock, never corrupting state, never hanging past the bound.

### 6. Multiple-resource locking never deadlocks

**When** an operation legitimately requires more than one lock (an
out-of-scope case for ordinary single-run operations under A1, but
exercised here as a forward-looking conformance case per
`CONTRACT-STORAGE-CONCURRENCY` §4).
**Then** every participant acquires canonicalized, lexicographically
sorted lock paths in that sorted order and releases them in reverse order;
running many such multi-lock operations concurrently, with overlapping
resource sets across participants, never deadlocks.

### 7. Malformed/incomplete final record recovers cleanly

**When** a run's `journal.jsonl` (or, in the future, any WAL-shaped log
this contract governs) ends in a malformed or incomplete final line, with
at least one valid record preceding it.
**Then** a reader treats the final line as a torn write, ignores it, and
continues from the last good record — the existing `PORT-JOURNAL` torn-tail
rule, exercised here specifically under concurrent-writer conditions
rather than single-writer crash conditions.

## Mutation check

Any of the following makes this scenario fail: a lost update under
concurrent read-modify-write (item 1); an interleaved, truncated, or
duplicated record under concurrent appenders (item 2); a stale lock that
blocks a subsequent process indefinitely, or requires manual cleanup,
after the holder crashes (item 3); a config or journal file observably
torn (neither the complete old nor complete new snapshot) after a
mid-replacement crash (item 4); a lock-timeout path that falls back to an
unlocked write instead of returning `ERR-BUSY` (item 5); a multi-lock
operation that deadlocks or acquires locks out of the canonical sorted
order (item 6); a malformed non-final record silently skipped instead of
failing closed with `ERR-VALIDATION` (item 7, `PORT-JOURNAL`'s existing
rule); or any test in this battery passing only under threads/async tasks
while failing under real separate OS processes.

## Verifies

- `CONTRACT-STORAGE-CONCURRENCY` — every numbered item above maps directly
  to that contract's §12 required-test list and exercises its §2, §5, §6,
  §10, and §11 rules plus the A1 lock-identity amendment.
- `PORT-JOURNAL` — the durable-journal torn-tail recovery rule (item 7)
  and the `seq` ordering identity (item 2).
- `CONTRACT-ERRORS` — `ERR-BUSY` (item 5).
- `INV-020` — idempotent, deterministic replay is unaffected by concurrent
  storage access: re-dispatch after any of the above recovers cleanly
  because idempotency keys derive from durable canonical state, never
  process identity or timing.
- `CONTRACT-DURABILITY` — this scenario exercises concurrency safety only;
  it does not raise or lower Orc Werk's declared process-crash durability
  level (`CONTRACT-STORAGE-CONCURRENCY` §9).

## Not yet implemented

As of this scenario's registration, no lock-acquiring code exists in
`src/` (`CONTRACT-STORAGE-CONCURRENCY`'s "Current gaps at adoption" list).
This scenario specifies the conformance bar the implementation PR must
satisfy; it does not itself land a passing automated test in this PR.
